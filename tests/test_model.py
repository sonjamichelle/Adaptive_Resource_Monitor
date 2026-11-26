import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest

from arm.config import ConfigStore, Settings, Target
from arm.credentials import CredentialStore
from arm.graphs import Dashboard, across_series
from arm.model import (ALL, LOCAL, TOTAL, Availability, Connection, History, Status,
                       aggregate, current_reading, graph_scale, rate, readings)
from arm.providers.gpu import engine_usage, gpu_metrics
from arm.tray import HoverState, place_popup
from PySide6.QtCore import QRect, QSize


class ModelTests(unittest.TestCase):
    def test_rate_baseline_reset_delayed_and_zero(self):
        self.assertIsNone(rate(None, 33, 1, 1))
        self.assertIsNone(rate(100, 99, 1, 1))
        self.assertIsNone(rate(9, 10, 10, 1))
        self.assertEqual(rate(9, 9, 1, 1), 0)
        self.assertEqual(rate(100, 200, .5, 1), 200)

    def test_history_and_scaling(self):
        history = History(10, 3)
        for i in range(1, 6):
            history.add(readings(LOCAL, i, TOTAL, {"disk.total": (i * 1000, "B/s")}))
        series = history.since(LOCAL, TOTAL, "disk.total", 0)
        self.assertEqual([r.timestamp for r in series], [3, 4, 5])
        self.assertEqual(graph_scale(series), 8192)
        self.assertEqual(graph_scale(series, 21000), 21000)
        self.assertEqual(current_reading(series[-1], Connection.OFFLINE, 1, 6).availability, Availability.STALE)
        self.assertEqual(len(history.since(LOCAL, TOTAL, "disk.total", 4.5)), 1)

    def test_gpu_capacity_pairs_peak_and_engines(self):
        gpus = [gpu_metrics({"util": 100, "vram_used": 3, "vram_total": 10}),
                gpu_metrics({"util": 0, "vram_used": 7, "vram_total": 20}),
                gpu_metrics({"util": 16, "vram_total": 100})]
        result = {r.metric: r.value for r in aggregate(LOCAL, 1, "gpu", gpus)}
        self.assertEqual(result["gpu.util"], 100)
        self.assertEqual(result["gpu.vram_total"], 30)
        self.assertAlmostEqual(result["gpu.vram_pct"], 100 / 3)
        self.assertEqual(result["gpu.vram_free"], 20)
        values = engine_usage({
            "pid_2_luid_0x00000000_0x00000001_phys_0_eng_2_engtype_3D": 40,
            "pid_3_luid_0x00000000_0x00000001_phys_0_eng_2_engtype_3D": 35,
            "pid_3_luid_0x00000000_0x00000001_phys_0_eng_4_engtype_Compute": 20,
        })
        self.assertEqual(next(iter(values.values()))["util"], 75)
        self.assertEqual(next(iter(values.values()))["compute"], 20)

    def test_multi_machine_ignores_disconnect_and_names_peak(self):
        target = Target(name="Remote")
        coll = SimpleNamespace(settings=Settings(targets=[target]), history=History(),
                               statuses={LOCAL: Status(LOCAL, Connection.ONLINE),
                                         target.identifier: Status(target.identifier, Connection.ONLINE)},
                               provider_status={}, intervals={})
        view = Dashboard(coll)
        for m, peak in ((LOCAL, 12), (target.identifier, 100)):
            coll.history.add(readings(m, 29, TOTAL, {"cpu.util": (peak, "%")}))
        _, _, _, value, chosen, _ = view.get(ALL, "cpu", "cpu.util", TOTAL, 30, 30, 40)
        self.assertEqual((value.value, chosen), (100, target.identifier))
        coll.statuses[target.identifier] = Status(target.identifier, Connection.OFFLINE)
        _, _, _, value, chosen, _ = view.get(ALL, "cpu", "cpu.util", TOTAL, 30, 30, 40)
        self.assertEqual((value.value, chosen), (12, LOCAL))
        self.assertEqual(across_series({"ram": [(29, None)], "cpu": [(29, 90)]}, 30, 30, 3, 25)[0],
                         (29, 90, "cpu"))

    def test_hover_and_taskbar_edges(self):
        state = HoverState()
        self.assertIsNone(state.update(1, LOCAL, False, False, False, .3, .5))
        self.assertEqual(state.update(1.5, LOCAL, False, False, False, .3, .5), "show")
        self.assertIsNone(state.update(2, None, False, True, False, .3, .5))
        self.assertIsNone(state.update(2.1, None, True, True, False, .3, .5))
        self.assertIsNone(state.update(3, None, False, True, False, .3, .5))
        self.assertEqual(state.update(3.6, None, False, True, False, .3, .5), "hide")
        self.assertIsNone(state.update(7, None, False, True, True, .3, .5))
        available = QRect(-1200, 40, 1200, 740)
        for rect in (QRect(-20, 784, 18, 18), QRect(-80, 5, 16, 16), QRect(-1220, 10, 16, 16)):
            self.assertTrue(available.contains(place_popup(available, rect, QSize(500, 330))))

    def test_settings_backward_compat_and_reference(self):
        with tempfile.TemporaryDirectory(prefix="arm-config-test-") as root:
            path = Path(root) / "settings.json"
            path.write_text('{"popup_width": 9999,"hover_range":[]}', encoding="utf-8")
            store = ConfigStore(path)
            self.assertEqual(store.load().popup_width, 1800)
            cfg = Settings(mode="Stacked", targets=[Target(credential="test-reference")])
            store.save(cfg)
            self.assertEqual(store.load(), cfg)
            cfg.mode = "Application Icon"
            store.save(cfg)
            self.assertEqual(store.load(), cfg)
            self.assertNotIn('"password":', path.read_text(encoding="utf-8").lower())

    def test_real_credential_namespace_and_roundtrip(self):
        vault = CredentialStore()
        ref = vault.save("ARM unit test", "Test-only µ password")
        try:
            self.assertEqual(vault.read(ref), "Test-only µ password")
            with self.assertRaises(ValueError):
                vault.read("UnrelatedCredential")
        finally:
            vault.delete(ref)
        self.assertIsNone(vault.read(ref))
