from pathlib import Path
from contextlib import ExitStack
from queue import Queue
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic, sleep, time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import paramiko
from PySide6.QtCore import QCoreApplication

from arm.collect import Collectors, Worker, problem
from arm.config import Settings, Target
from arm.history_db import HistoryDb
from arm.model import Connection, LOCAL, NETWORK, TOTAL, Sample, Status, readings
from arm.providers.gpu import WddmGpu
from arm.providers.ssh import LinuxParser, LinuxSsh, UntrustedHost, update_host_key
from arm.providers.windows import Cpu, Disk, Memory, Network
from ssh_fixture import COMMAND, FRAME, Fixture, Secret


def reading(sample, metric, device=TOTAL):
    return next(r for r in sample.readings if r.metric == metric and r.device == device)


class Providers(unittest.TestCase):
    def test_windows_live_collector_shapes_and_first_sample(self):
        providers = [kind(Settings()) for kind in (Cpu, Memory, Disk, Network, WddmGpu)]
        try:
            first = [p.sample() for p in providers]
            self.assertIsNone(reading(first[0], "cpu.util").value)
            self.assertIsNone(reading(first[2], "disk.total").value)
            sleep(.85)
            second = [p.sample() for p in providers]
            self.assertTrue(reading(second[0], "cpu.util").valid)
            self.assertGreater(reading(second[0], "system.uptime").value,
                               reading(first[0], "system.uptime").value)
            self.assertTrue(reading(second[1], "ram.util").valid)
            for sample in second:
                self.assertTrue(all(r.timestamp == sample.timestamp for r in sample.readings))
        finally:
            for provider in providers:
                provider.close()

    def test_linux_rates_resets_and_interface_scope(self):
        parser = LinuxParser(Target(interval=1))
        first, os_label = parser.parse(FRAME.format(boot=1, busy=100), 10, 10)
        second, _ = parser.parse(FRAME.format(boot=1, busy=200), 11, 11)
        self.assertEqual(os_label, "Linux fixture")
        self.assertIsNone(reading(first, "cpu.util").value)
        self.assertEqual(reading(first, "system.uptime").value, 12345.67)
        self.assertEqual(reading(second, "cpu.util").value, 100)
        self.assertEqual(reading(second, "disk.read").value, 51200)
        self.assertEqual(reading(second, "net.total").value, 200)
        self.assertEqual(reading(second, "net.total", "vpn0").value, 200)
        self.assertEqual(reading(second, "gpu.vram_pct").value, 25)
        reset, _ = parser.parse(FRAME.format(boot=2, busy=400), 12, 12)
        self.assertIsNone(reading(reset, "disk.read").value)
        invalid, _ = parser.parse(FRAME.format(boot=2, busy=500).replace("12345.67", "-1"), 13, 13)
        self.assertIsNone(reading(invalid, "system.uptime").value)

    def test_directional_deltas_skip_reboot_reset_and_interface_replacement(self):
        def frame(boot, rx, tx, index):
            lines = FRAME.format(boot=boot, busy=300).splitlines()
            return "\n".join(f"net\teth0\t1\tup\t10000\t{rx} 0 0 0 0 0 0 0 {tx} 0 0 0 0 0 0 0\t{index}"
                             if line.startswith("net\teth0\t") else line for line in lines)

        parser = LinuxParser(Target(interval=1))
        for stamp, counters, expected in (
            (1, (1, 100, 200, 2), (None, None)),
            (2, (1, 130, 275, 2), (30, 75)),
            (3, (1, 20, 280, 2), (None, 5)),
            (4, (1, 19000, 81000, 5), (None, None)),
            (5, (1, 19010, 81005, 5), (10, 5)),
            (6, (2, 40000, 82000, 5), (None, None)),
        ):
            sample, _ = parser.parse(frame(*counters), stamp, stamp)
            self.assertEqual(tuple(reading(sample, metric, "eth0").value for metric in NETWORK), expected)

    def test_windows_directional_deltas_rebaseline_replaced_interface(self):
        sampler = Network(Settings(local_interval=1, interfaces=["Ethernet"]))
        samples = [{"Ethernet": SimpleNamespace(bytes_recv=rx, bytes_sent=tx)}
                   for rx, tx in ((100, 200), (150, 215), (90000, 100000), (90010, 100040))]
        adapters = [{"Ethernet": (True, 1_000_000, 1_000_000, guid)} for guid in (b"a", b"a", b"b", b"b")]
        with patch("arm.providers.windows.psutil.net_io_counters", side_effect=samples), \
                patch("arm.providers.windows.psutil.net_if_stats", return_value={"Ethernet": SimpleNamespace(isup=True)}), \
                patch("arm.providers.windows.interface_info", side_effect=adapters), \
                patch("arm.providers.windows.monotonic", side_effect=(1, 2, 3, 4)):
            for expected in ((None, None), (50, 15), (None, None), (10, 40)):
                packet = sampler.sample()
                for device in (TOTAL, "Ethernet"):
                    self.assertEqual(tuple(reading(packet, metric, device).value for metric in NETWORK), expected)

    def test_collectors_sample_independently_while_another_machine_is_stalled(self):
        app = QCoreApplication.instance() or QCoreApplication([])
        gate = Event()
        with TemporaryDirectory(prefix="arm-ssh-test-") as root, ExitStack() as stack:
            slow = stack.enter_context(Fixture(gate=gate))
            fast = stack.enter_context(Fixture())
            path = Path(root) / "known_hosts"
            targets = []
            for server, interval in ((slow, 1), (fast, .5)):
                targets.append(Target(host="127.0.0.1", port=server.port, username="tester",
                                      timeout=8, interval=interval))
                update_host_key(path, f"[127.0.0.1]:{server.port}", server.key)
            collectors = Collectors(Settings(targets=targets), Secret(), path)
            try:
                with patch("arm.collect.LOCAL_PROVIDERS", ()):
                    collectors.start()
                deadline = monotonic() + 5
                while monotonic() < deadline and (fast.samples < 3 or not slow.samples):
                    app.processEvents()
                    sleep(.025)
                app.processEvents()
                self.assertGreaterEqual(fast.samples, 3)
                self.assertGreaterEqual(slow.samples, 1)
                self.assertNotIn(targets[0].identifier, collectors.last)
                self.assertIn(targets[1].identifier, collectors.last)
                self.assertEqual([collectors.intervals[t.identifier] for t in targets], [1, .5])
            finally:
                collectors.close()
                gate.set()

    def test_loopback_password_verification_persistence_and_changed_key(self):
        with TemporaryDirectory(prefix="arm-ssh-test-") as root, Fixture() as server:
            known = Path(root) / "known_hosts"
            profile = Target(host="127.0.0.1", port=server.port, username="tester", timeout=3)
            sampler = LinuxSsh(profile, Secret(), known)
            with self.assertRaises(UntrustedHost) as blocked:
                try:
                    sampler.sample()
                finally:
                    sampler.close()
            host_key = blocked.exception.host_key
            self.assertTrue(host_key.fingerprint.startswith("SHA256:"))
            wrong = paramiko.RSAKey.generate(2048)
            update_host_key(known, host_key.label, wrong)
            sampler = LinuxSsh(profile, Secret(), known)
            try:
                with self.assertRaises(paramiko.BadHostKeyException) as changed:
                    sampler.sample()
                self.assertFalse(problem(changed.exception)[1])
            finally:
                sampler.close()
            update_host_key(known, host_key.label)
            update_host_key(known, host_key.label, host_key.key)
            sampler = LinuxSsh(profile, Secret("wrong"), known)
            try:
                with self.assertRaises(paramiko.AuthenticationException):
                    sampler.sample()
            finally:
                sampler.close()
            sampler = LinuxSsh(profile, Secret(), known)
            try:
                self.assertFalse(reading(sampler.sample(), "cpu.util").valid)
                self.assertTrue(reading(sampler.sample(), "cpu.util").valid)
                self.assertEqual(server.samples, 2)
                self.assertEqual(server.commands, [COMMAND])
            finally:
                sampler.close()

    def test_loopback_private_key(self):
        private = paramiko.RSAKey.generate(2048)
        with TemporaryDirectory(prefix="arm-key-test-") as root, Fixture(public=private) as server:
            root = Path(root)
            profile = Target(host="127.0.0.1", port=server.port, username="tester", timeout=3,
                             auth="Private key", key_file=str(root / "test_key"))
            private.write_private_key_file(profile.key_file, password="ephemeral")
            known = root / "known_hosts"
            update_host_key(known, f"[127.0.0.1]:{server.port}", server.key)
            sampler = LinuxSsh(profile, Secret("ephemeral"), known)
            try:
                self.assertTrue(reading(sampler.sample(), "ram.util").valid)
            finally:
                sampler.close()

    def test_worker_reconnect_and_close(self):
        with TemporaryDirectory(prefix="arm-retry-test-") as root, Fixture(drop_first=True) as server:
            profile = Target(host="127.0.0.1", port=server.port, username="tester", timeout=3, interval=.5)
            known = Path(root) / "known_hosts"
            update_host_key(known, f"[127.0.0.1]:{server.port}", server.key)
            events = Queue()
            worker = Worker((profile.identifier, "test"), lambda: LinuxSsh(profile, Secret(), known),
                            .5, lambda _, message, *_tail: events.put(message), remote=True)
            worker.start()
            try:
                results = [events.get(timeout=8) for _ in range(4)]
                states = [item.state for item in results if isinstance(item, Status)]
                self.assertEqual(states, [Connection.CONNECTING, Connection.RETRYING, Connection.CONNECTING])
                self.assertTrue(isinstance(results[-1], Sample))
                self.assertGreaterEqual(server.connections, 2)
            finally:
                worker.stop()
                worker.join(5)
            self.assertFalse(worker.is_alive())

    def test_sqlite_flush_read_clear_and_stop(self):
        with TemporaryDirectory(prefix="arm-db-test-") as root:
            stamp = time()
            replies, errors = Queue(), Queue()
            key = (LOCAL, TOTAL, "cpu.util")
            legacy = (LOCAL, TOTAL, "net.total")
            directions = [(LOCAL, TOTAL, metric) for metric in NETWORK]
            path = Path(root) / "history.sqlite"
            first = HistoryDb(path, 1, 16, lambda *result: replies.put(result), errors.put)
            first.record(readings(LOCAL, stamp, TOTAL, {"cpu.util": (31, "%"), "net.total": (800, "B/s")}))
            first.close()
            next_db = HistoryDb(path, 1, 16, lambda *result: replies.put(result), errors.put)
            try:
                next_db.request(1, [key, legacy, *directions], stamp - 1)
                records = replies.get(timeout=5)[1]
                self.assertEqual(records[key][0].value, 31)
                self.assertEqual(records[legacy][0].value, 800)
                self.assertTrue(all(not records[direction] for direction in directions))
                next_db.send("clear", 2)
                self.assertEqual(replies.get(timeout=5), (2, {}))
                next_db.request(3, [key], stamp - 1)
                self.assertEqual(replies.get(timeout=5)[1][key], [])
            finally:
                next_db.close()
            self.assertTrue(errors.empty())
            self.assertFalse(next_db.thread.is_alive())
