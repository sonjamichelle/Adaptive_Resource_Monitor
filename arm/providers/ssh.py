import base64
import csv
import hashlib
import io
from math import isfinite
from pathlib import Path
import socket
import shlex
import threading
from collections import defaultdict
from dataclasses import dataclass
import logging
from time import perf_counter as monotonic, time

import paramiko

from . import Provider
from .gpu import gpu_metrics
from .windows import cpu_group, disk_metrics, net_metrics
from ..model import Device, Sample, TOTAL, aggregate, rate, readings, usage

LOG = logging.getLogger(__name__)
SCRIPT = Path(__file__).with_name("linux_probe.sh")
HOST_LOCK = threading.Lock()
MAX_FRAME = 1024 * 1024
VENDORS = {"0x1002": "AMD", "0x8086": "Intel", "0x10de": "NVIDIA"}


def probe_command():
    # Passing the fixed program in -c leaves channel stdin dedicated to tokens.
    return "bash --noprofile --norc -c " + shlex.quote(SCRIPT.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class HostKey:
    label: str
    key: object

    @property
    def fingerprint(self):
        sha = hashlib.sha256(self.key.asbytes()).digest()
        return "SHA256:" + base64.b64encode(sha).decode("ascii").rstrip("=")


class UntrustedHost(paramiko.SSHException):
    def __init__(self, label, key):
        super().__init__("New SSH host key")
        self.host_key = HostKey(label, key)


class RecordUnknownKey(paramiko.MissingHostKeyPolicy):
    def missing_host_key(self, client, hostname, key):
        raise UntrustedHost(hostname, key)


def known_hosts(path):
    keys = paramiko.HostKeys()
    if path.is_file():
        keys.load(str(path))
    return keys


def update_host_key(path, label, key=None):
    with HOST_LOCK:
        keys = known_hosts(path)
        if key is None:
            if label in keys:
                del keys[label]
        else:
            if label in keys and not keys.check(label, key):
                raise ValueError("A different key is already stored for this host")
            keys.add(label, key.get_name(), key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        try:
            keys.save(str(temporary))
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


class LinuxSsh(Provider):
    identifier = "Linux SSH"

    def __init__(self, target, secrets, hosts):
        self.target = target
        self.secrets = secrets
        self.hosts = hosts
        self.transport = None
        self.channel = None
        self.sock = None
        self.pending = bytearray()
        self.cancelled = threading.Event()
        self.collector = LinuxParser(target)
        self.os = "Linux"
        self.command = probe_command()

    def _resolve(self):
        target = self.target
        resolved = []
        done = threading.Event()

        def resolve():
            try:
                resolved.extend(socket.getaddrinfo(target.host, target.port, type=socket.SOCK_STREAM))
            except OSError:
                pass
            finally:
                done.set()

        threading.Thread(target=resolve, daemon=True, name="ARM SSH DNS").start()
        deadline = monotonic() + target.timeout
        while not self.cancelled.is_set() and not done.wait(.1):
            if monotonic() >= deadline:
                raise TimeoutError("SSH hostname lookup timed out")
        if not resolved or self.cancelled.is_set():
            raise OSError("SSH hostname could not be resolved")
        return resolved

    def connect(self):
        expired = threading.Event()

        def timeout():
            expired.set()
            self.close_socket()

        watchdog = threading.Timer(self.target.timeout, timeout)
        watchdog.daemon = True
        watchdog.start()
        try:
            self._connect(expired)
        except Exception:
            if expired.is_set():
                raise TimeoutError("SSH handshake or channel setup timed out") from None
            raise
        finally:
            watchdog.cancel()
        if expired.is_set():
            raise TimeoutError("SSH handshake or channel setup timed out")

    def _connect(self, expired):
        target = self.target
        deadline = monotonic() + target.timeout
        for family, mode, proto, _, addr in self._resolve():
            if expired.is_set() or self.cancelled.is_set() or monotonic() >= deadline:
                break
            sock = socket.socket(family, mode, proto)
            self.sock = sock
            try:
                sock.settimeout(max(.1, deadline - monotonic()))
                sock.connect(addr)
                if self.cancelled.is_set():
                    raise OSError("SSH connection cancelled")
                break
            except OSError:
                sock.close()
                self.sock = None
        if self.sock is None or self.cancelled.is_set():
            raise OSError("SSH connection unavailable")
        client = paramiko.SSHClient()
        self.transport = client
        if self.hosts.is_file():
            with HOST_LOCK:
                client.load_host_keys(str(self.hosts))
        client.set_missing_host_key_policy(RecordUnknownKey())
        secret = self.secrets.read(target.credential)
        if target.auth == "Password" and secret is None:
            raise paramiko.AuthenticationException("No saved password")
        if target.auth == "Private key" and not target.key_file:
            raise paramiko.AuthenticationException("No private key selected")
        client.connect(target.host, port=target.port, username=target.username,
                       password=secret if target.auth == "Password" else None,
                       passphrase=secret if target.auth == "Private key" else None,
                       key_filename=target.key_file if target.auth == "Private key" else None,
                       timeout=target.timeout, banner_timeout=target.timeout, auth_timeout=target.timeout,
                       channel_timeout=target.timeout, allow_agent=False, look_for_keys=False, sock=self.sock)
        transport = client.get_transport()
        transport.set_keepalive(15)
        self.channel = transport.open_session(timeout=target.timeout)
        self.channel.settimeout(.25)
        self.channel.set_combine_stderr(True)
        self.channel.exec_command(self.command)

    def sample(self):
        if self.channel is None:
            self.connect()
        self.channel.sendall(b".\n")
        deadline = monotonic() + self.target.timeout
        while monotonic() < deadline and not self.cancelled.is_set():
            start = self.pending.find(b"@arm-begin\n")
            if start >= 0:
                end = self.pending.find(b"@arm-end\n", start)
                if end >= 0:
                    frame = bytes(self.pending[start + 11:end])
                    del self.pending[:end + 9]
                    stamp = time()
                    packet, self.os = self.collector.parse(frame.decode("utf-8", "replace"), stamp, monotonic())
                    return packet
            try:
                chunk = self.channel.recv(32768)
            except socket.timeout:
                continue
            if not chunk:
                raise EOFError("SSH telemetry channel closed")
            self.pending.extend(chunk)
            if len(self.pending) > MAX_FRAME:
                raise ValueError("SSH telemetry response exceeds limit")
        raise TimeoutError("SSH telemetry response timed out")

    def cancel(self):
        self.cancelled.set()
        self.close_socket()

    def close_socket(self):
        sock = self.sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()

    def close(self):
        self.cancel()
        if self.transport is not None:
            self.transport.close()


def num(value, factor=1):
    try:
        n = float(value) * factor
        return n if isfinite(n) else None
    except (TypeError, ValueError):
        return None


def integers(row, count):
    result = row.split()
    if len(result) >= count and all(v.isdecimal() for v in result):
        return tuple(map(int, result))
    return ()


class LinuxParser:
    def __init__(self, target):
        self.target = target
        self.previous = {}
        self.last = 0
        self.boot = ""

    def parse(self, frame, stamp, tick):
        sections = defaultdict(list)
        for line in frame.splitlines():
            key, *values = line.split("\t")
            sections[key].append(values)
        boot = sections["boot"][0][0] if sections["boot"] and sections["boot"][0] else ""
        if boot != self.boot:
            self.previous.clear()
        elapsed = tick - self.last
        self.boot, self.last = boot, tick
        machine = self.target.identifier
        items, devices = [], []
        next_counters = {}

        def add(kind, identifier, name, values):
            devices.append(Device(kind, identifier, name))
            items.extend(readings(machine, stamp, identifier, values))

        def counters(key, current):
            previous = self.previous.get(key, [None] * len(current))
            next_counters[key] = current
            return [rate(old, now, elapsed, self.target.interval) for old, now in zip(previous, current)]

        cpu_values = {}
        for name, row in (row for row in sections["cpu"] if len(row) == 2):
            raw = integers(row, 5)
            if raw:
                total = sum(raw[:8])
                busy = total - raw[3] - raw[4]
                d_busy, d_total = counters(name, (busy, total))
                cpu_values[name] = (d_busy, d_total)
                if name != "cpu":
                    add("cpu", name, f"Logical processor {name[3:]}", {"cpu.util": (usage(d_busy, d_total), "%")})
        core_map = defaultdict(list)
        for proc, package, core in (row for row in sections["core"] if len(row) == 3):
            package, core = package.strip(), core.strip()
            if core:
                core_map[(package, core)].append("cpu" + proc.strip())
        for (package, core), processors in core_map.items():
            add("cpu", f"core:{package}:{core}", f"Package {package or '0'} core {core}",
                {"cpu.util": (cpu_group(cpu_values, processors), "%")})
        model, frequency = (sections["cpuinfo"][0] + ["", ""])[:2] if sections["cpuinfo"] else ("", "")
        if model.strip():
            devices.append(Device("cpu-info", "identity", model.strip()))
        sensors = [row for row in sections["cpusensor"] if len(row) == 2]
        temperatures = [val for temp, _ in sensors if (val := num(temp, .001)) is not None]
        powers = [val for _, power in sensors if (val := num(power, .000001)) is not None]
        items.extend(readings(machine, stamp, TOTAL, {
            "cpu.util": (usage(*cpu_values.get("cpu", (None, None))), "%"),
            "cpu.physical": (len(core_map) or None, "count"),
            "cpu.logical": (sum(key != "cpu" for key in cpu_values) if cpu_values else None, "count"),
            "cpu.frequency": (num(frequency), "MHz"), "cpu.temperature": (max(temperatures, default=None), "°C"),
            "cpu.power": (sum(powers) if powers else None, "W"),
        }))
        mem = {key: num(value, 1024) for key, value in sections["ram"] if value} if all(
            len(row) == 2 for row in sections["ram"]) else {}
        total, available = mem.get("MemTotal"), mem.get("MemAvailable")
        used = difference(total, available)
        items.extend(readings(machine, stamp, TOTAL, {
            "ram.total": (total, "B"), "ram.available": (available, "B"), "ram.used": (used, "B"),
            "ram.util": (usage(used, total), "%"),
            "ram.pagefile_total": (mem.get("SwapTotal"), "B"),
            "ram.pagefile_used": (difference(mem.get("SwapTotal"), mem.get("SwapFree")), "B"),
            "ram.committed": (mem.get("Committed_AS"), "B"), "ram.commit_limit": (mem.get("CommitLimit"), "B"),
        }))

        filtered = {"disk": [], "net": [], "gpu": []}

        def selected(kind, identifier, name, values, included):
            add(kind, identifier, name, values)
            if included:
                filtered[kind].append(values)

        for key, row in (row for row in sections["disk"] if len(row) == 2):
            v = integers(row, 11)
            if v:
                read, write, reads, writes, active = counters("disk:" + key, (v[2]*512, v[6]*512, v[0], v[4], v[9]))
                selected("disk", key, key, disk_metrics(read, write, reads, writes,
                                                        min(100, active / 10) if active is not None else None),
                         not self.target.disks or key in self.target.disks)
        for key, physical, state, speed, row, *identity in (row for row in sections["net"] if len(row) in (5, 6)):
            v = integers(row, 16)
            if v:
                receive, transmit = counters(("net", key, state, *identity), (v[0], v[8]))
                link = num(speed)
                up = state == "up" if state in ("up", "down", "lowerlayerdown", "dormant") else None
                link = link if link and link > 0 and up else None
                selected("net", key, key, net_metrics(receive, transmit, up, link, link),
                         key in self.target.interfaces if self.target.interfaces else physical == "1")
        for key, vendor, ident, util, used, total, temp, clock, memclk, power in (
                row for row in sections["drm"] if len(row) == 10):
            parts = power.split(",", 1)
            metrics = gpu_metrics({"util": num(util), "vram_used": num(used), "vram_total": num(total),
                                   "temperature": num(temp, .001), "clock": num(clock), "memory_clock": num(memclk),
                                   "power": num(parts[0], .000001), "power_limit": num(parts[-1], .000001)})
            name = f"{VENDORS.get(vendor, vendor)} {ident} ({key})"
            selected("gpu", key, name, metrics, not self.target.gpus or key in self.target.gpus)
        for row in csv.reader(io.StringIO("\n".join("\t".join(row) for row in sections["nvidia"])), skipinitialspace=True):
            if len(row) != 13:
                continue
            key, name, util, used, total, temp, clock, memclk, power, limit, fan, enc, dec = row
            metrics = gpu_metrics({"util": num(util), "vram_used": num(used, 2**20),
                                   "vram_total": num(total, 2**20), "temperature": num(temp), "clock": num(clock),
                                   "memory_clock": num(memclk), "power": num(power), "power_limit": num(limit),
                                   "fan": num(fan), "encode": num(enc), "decode": num(dec)})
            selected("gpu", key, name, metrics, not self.target.gpus or key in self.target.gpus)
        self.previous = next_counters
        for kind, values in filtered.items():
            items.extend(aggregate(machine, stamp, kind, values))
        if not cpu_values or not mem:
            raise ValueError("Linux telemetry response lacks required system information")
        return Sample(machine, "Linux SSH", stamp, tuple(items), tuple(devices)), (
            sections["os"][0][0] if sections["os"] and sections["os"][0] else "Linux")


def difference(total, available):
    return max(0, total - available) if total is not None and available is not None else None
