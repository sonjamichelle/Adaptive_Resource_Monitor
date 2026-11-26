"""Collector lifecycle and the Qt delivery boundary."""
from collections import defaultdict
from dataclasses import replace
import logging
import threading
from time import monotonic, time

import paramiko
from PySide6.QtCore import QObject, Signal

from .model import Availability, Connection, History, LOCAL, Reading, Status, TOTAL
from .providers.gpu import WddmGpu
from .providers.ssh import LinuxSsh, UntrustedHost
from .providers.windows import Cpu, Disk, Memory, Network, os_name

LOG = logging.getLogger(__name__)
LOCAL_PROVIDERS = (Cpu, Memory, Disk, Network, WddmGpu)


def problem(exc):
    if isinstance(exc, paramiko.BadHostKeyException):
        return "SSH host key changed. Verify the replacement before updating trust.", False
    if isinstance(exc, paramiko.AuthenticationException):
        return "SSH authentication failed. Check the selected credentials.", False
    if isinstance(exc, FileNotFoundError):
        return "A required local file is unavailable.", False
    if isinstance(exc, TimeoutError):
        detail = str(exc) if str(exc) in {
            "SSH hostname lookup timed out", "SSH handshake or channel setup timed out",
            "SSH telemetry response timed out",
        } else "Connection or telemetry timed out."
        return detail, True
    if isinstance(exc, (OSError, EOFError, paramiko.SSHException)):
        return f"SSH connection interrupted ({type(exc).__name__}).", True
    return f"Collection failed ({type(exc).__name__}).", True


class Worker(threading.Thread):
    def __init__(self, key, factory, interval, emit, *, remote=False, retry=True, once=False):
        super().__init__(name=f"ARM {key[1]}", daemon=False)
        self.key = key
        self.machine = key[0]
        self.factory, self.interval, self.emit = factory, interval, emit
        self.remote, self.retry, self.once = remote, retry, once
        self.stopping = threading.Event()
        self.provider = None

    def stop(self):
        self.stopping.set()
        current = self.provider
        if current is not None:
            current.cancel()

    def status(self, state, detail="", trust=None):
        self.emit(self, Status(self.machine, state, detail, trust), "", 0)

    def run(self):
        failures = 0
        next_due = monotonic()
        while not self.stopping.is_set():
            try:
                if self.provider is None:
                    if self.remote:
                        self.status(Connection.CONNECTING)
                    LOG.info("Initializing provider %s for %s", self.key[1], self.machine)
                    self.provider = self.factory()
                if self.stopping.is_set():
                    break
                started = monotonic()
                sample = self.provider.sample()
                duration = monotonic() - started
                if self.remote and failures:
                    LOG.info("SSH telemetry recovered for %s", self.machine)
                failures = 0
                self.emit(self, sample, getattr(self.provider, "os", ""), duration)
                if self.once:
                    break
                next_due += self.interval
                if next_due <= monotonic():
                    next_due = max(started + self.interval, monotonic() + self.interval / 2)
                self.stopping.wait(max(0, next_due - monotonic()))
            except UntrustedHost as exc:
                self.status(Connection.TRUST, "Verify the SSH host key fingerprint.", exc.host_key)
                LOG.info("SSH key approval needed for %s", self.machine)
                break
            except Exception as exc:
                if self.stopping.is_set():
                    break
                failures += 1
                detail, retryable = problem(exc) if self.remote else (
                    f"{self.key[1]} failed ({type(exc).__name__})", True)
                will_retry = self.retry and retryable and not self.once
                state = Connection.RETRYING if will_retry else Connection.ERROR
                level = logging.WARNING if failures == 1 else logging.DEBUG
                LOG.log(level, "%s for %s. %s%s", self.key[1], self.machine, detail,
                        " Retrying." if will_retry else "")
                self.status(state, detail)
                self.close_provider()
                if not will_retry:
                    break
                self.stopping.wait(min(60, 2 ** min(failures, 6)))
                next_due = monotonic()
        self.close_provider()

    def close_provider(self):
        if self.provider is not None:
            try:
                self.provider.close()
            except Exception as exc:
                LOG.warning("Worker cleanup failed for %s (%s)", self.key[1], type(exc).__name__)
            finally:
                self.provider = None


class Collectors(QObject):
    delivered = Signal(object, object, str, float)
    changed = Signal()
    test_finished = Signal(object)

    def __init__(self, settings, credentials, hosts, storage=None):
        super().__init__()
        self.settings = settings
        self.credentials, self.hosts, self.storage = credentials, hosts, storage
        self.workers = {}
        self.retired = []
        self.keys = {}
        self.tests = {}
        self.manual = {}
        self.history = History()
        self.statuses = {LOCAL: Status(LOCAL, Connection.CONNECTING)}
        self.devices = defaultdict(dict)
        self.device_groups = defaultdict(dict)
        self.intervals = {LOCAL: settings.local_interval}
        self.systems = {LOCAL: os_name()}
        self.provider_status = {}
        self.last = {}
        self.timings = {}
        self.delivered.connect(self.receive)

    def start(self):
        self.apply(self.settings)

    def apply(self, settings):
        self.settings = settings
        self.retired = [worker for worker in self.retired if worker.is_alive()]
        wanted = {}
        for provider in LOCAL_PROVIDERS:
            key = (LOCAL, provider.identifier)
            filters = {"GPU": settings.gpus, "Storage": settings.disks, "Network": settings.interfaces}
            signature = (settings.local_interval, tuple(filters.get(key[1], ())))
            wanted[key] = (signature, lambda provider=provider: provider(settings), settings.local_interval, False, True)
        self.intervals[LOCAL] = settings.local_interval
        ids = {target.identifier for target in settings.targets}
        for machine in list(self.statuses):
            if machine not in ids and machine != LOCAL:
                self.statuses.pop(machine)
                self.devices.pop(machine, None)
                self.device_groups.pop(machine, None)
                self.intervals.pop(machine, None)
                self.manual.pop(machine, None)
                self.last.pop(machine, None)
                self.systems.pop(machine, None)
                self.history.remove_machine(machine)
                self.timings.pop((machine, "Linux SSH"), None)
        for target in settings.targets:
            machine = target.identifier
            self.intervals[machine] = target.interval
            if target.os_type == "Windows":
                self.statuses[machine] = Status(machine, Connection.UNSUPPORTED, "Remote Windows telemetry is planned")
            elif not target.enabled:
                self.gap_if_connected(machine)
                self.statuses[machine] = Status(machine, Connection.DISABLED)
            elif self.manual.get(machine) is False:
                self.gap_if_connected(machine)
                self.statuses[machine] = Status(machine, Connection.OFFLINE)
            else:
                signature = repr(target)
                wanted[(machine, "Linux SSH")] = (signature, self.factory(target),
                                                   target.interval, True, target.reconnect)
        for key in list(self.workers):
            if key not in wanted or self.keys[key] != wanted[key][0]:
                self.retire(key)
        for key, (signature, factory, interval, remote, retry) in wanted.items():
            if key not in self.workers:
                if remote:
                    self.statuses[key[0]] = Status(key[0], Connection.CONNECTING)
                worker = Worker(key, factory, interval, self.delivered.emit, remote=remote, retry=retry)
                self.keys[key], self.workers[key] = signature, worker
                worker.start()
        self.changed.emit()

    def factory(self, target):
        return lambda: LinuxSsh(target, self.credentials, self.hosts)

    def retire(self, key):
        worker = self.workers.pop(key)
        self.keys.pop(key)
        worker.stop()
        self.retired.append(worker)

    def reconnect(self, machine):
        self.manual[machine] = True
        self.gap_if_connected(machine)
        key = (machine, "Linux SSH")
        if key in self.workers:
            self.retire(key)
        self.apply(self.settings)

    def disconnect(self, machine):
        self.manual[machine] = False
        self.apply(self.settings)

    def test(self, target):
        if target.os_type != "Linux":
            self.test_finished.emit(Status(target.identifier, Connection.UNSUPPORTED))
            return
        self.cancel_test(target.identifier)
        key = (target.identifier, "Test SSH")
        worker = Worker(key, self.factory(replace(target)), target.interval, self.delivered.emit,
                        remote=True, retry=False, once=True)
        self.tests[key] = worker
        worker.start()

    def cancel_test(self, machine):
        worker = self.tests.pop((machine, "Test SSH"), None)
        if worker is not None:
            worker.stop()
            self.retired.append(worker)

    def receive(self, sender, message, os_label, duration):
        key = sender.key
        if self.tests.get(key) is sender:
            if isinstance(message, Status) and message.state == Connection.CONNECTING:
                return
            self.tests.pop(key, None)
            self.retired.append(sender)
            result = message if isinstance(message, Status) else Status(sender.machine, Connection.ONLINE, os_label)
            self.test_finished.emit(result)
            return
        if self.workers.get(key) is not sender:
            return
        machine = sender.machine
        if isinstance(message, Status):
            if machine == LOCAL:
                self.provider_status[key] = message
                self.insert_gap(machine, key[1], message.detail)
            else:
                old = self.statuses.get(machine)
                self.statuses[machine] = message
                if old and old.state == Connection.ONLINE:
                    self.insert_gap(machine, key[1], message.detail)
            self.changed.emit()
            return
        old = self.statuses.get(machine)
        self.provider_status[key] = Status(machine, Connection.ONLINE)
        self.statuses[machine] = self.provider_status[key]
        self.last[machine] = max(self.last.get(machine, 0), message.timestamp)
        if os_label:
            self.systems[machine] = os_label
        self.timings[key] = duration
        self.device_groups[machine][key[1]] = {device.identifier: device for device in message.devices}
        self.devices[machine] = {device.identifier: device for group in self.device_groups[machine].values()
                                 for device in group.values()}
        self.history.add(message.readings)
        if self.storage:
            self.storage.record(message.readings)
        if not old or old.state != Connection.ONLINE:
            self.changed.emit()

    def insert_gap(self, machine, provider, diagnostic):
        now = time()
        kind = {"CPU": "cpu", "GPU": "gpu", "Storage": "disk", "Network": "net",
                "Memory": "ram"}.get(provider)
        availability = Availability.ERROR if machine == LOCAL else Availability.DISCONNECTED
        items = []
        for key, history in self.history.series.items():
            if key[0] == machine and history and (kind is None or key[2].split(".")[0] == kind):
                old = history[-1]
                items.append(Reading(machine, old.device, old.metric, None, old.unit, now,
                                     availability, diagnostic))
        self.history.add(items)
        if self.storage:
            self.storage.record(items)

    def gap_if_connected(self, machine):
        old = self.statuses.get(machine)
        if old and old.state == Connection.ONLINE:
            self.insert_gap(machine, "Linux SSH", "Connection closed")

    def close(self):
        workers = list(self.workers.values()) + list(self.tests.values()) + self.retired
        self.workers.clear()
        self.tests.clear()
        self.retired = []
        for worker in workers:
            worker.stop()
        for worker in workers:
            worker.join()
