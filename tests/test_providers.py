from pathlib import Path
from queue import Queue
from tempfile import TemporaryDirectory
from time import sleep, time
import unittest

import paramiko

from arm.collect import Worker, problem
from arm.config import Settings, Target
from arm.history_db import HistoryDb
from arm.model import Connection, LOCAL, TOTAL, Sample, Status, readings
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
        self.assertEqual(reading(second, "cpu.util").value, 100)
        self.assertEqual(reading(second, "disk.read").value, 51200)
        self.assertEqual(reading(second, "net.total").value, 200)
        self.assertEqual(reading(second, "net.total", "vpn0").value, 200)
        self.assertEqual(reading(second, "gpu.vram_pct").value, 25)
        reset, _ = parser.parse(FRAME.format(boot=2, busy=400), 12, 12)
        self.assertIsNone(reading(reset, "disk.read").value)

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
            path = Path(root) / "history.sqlite"
            first = HistoryDb(path, 1, 16, lambda *result: replies.put(result), errors.put)
            first.record(readings(LOCAL, stamp, TOTAL, {"cpu.util": (31, "%")}))
            first.close()
            next_db = HistoryDb(path, 1, 16, lambda *result: replies.put(result), errors.put)
            try:
                next_db.request(1, [key], stamp - 1)
                self.assertEqual(replies.get(timeout=5)[1][key][0].value, 31)
                next_db.send("clear", 2)
                self.assertEqual(replies.get(timeout=5), (2, {}))
                next_db.request(3, [key], stamp - 1)
                self.assertEqual(replies.get(timeout=5)[1][key], [])
            finally:
                next_db.close()
            self.assertTrue(errors.empty())
            self.assertFalse(next_db.thread.is_alive())
