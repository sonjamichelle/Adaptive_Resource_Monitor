import json
from dataclasses import replace
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from arm.config import ConfigStore, MachineDisplay, Settings, Target, monitor_choices
from arm.credentials import CredentialStore
from arm.graphs import Dashboard, composite_samples
from arm.model import (ALL, LOCAL, NETWORK, TOTAL, Availability, Connection, History, Status,
                       aggregate, current_reading, graph_scale, rate, readings)
from arm.providers.gpu import engine_usage, gpu_metrics
from arm.tray import HoverState, place_popup
from PySide6.QtCore import QRect, QSize


class MachineDisplayTests(unittest.TestCase):
    def setUp(self):
        self.cfg = Settings(hover_machine=ALL, tray_machine="c", targets=[
            Target(identifier=identifier, name=identifier) for identifier in ("a", "b", "c", "d")
        ])
        self.display = MachineDisplay.from_legacy(self.cfg)

    def test_legacy_monitor_preferences(self):
        self.assertEqual(self.display.visible(self.cfg), (LOCAL, "a", "b", "c", "d"))
        self.assertTrue(self.display.select_new)
        for setting in ({"hover_machine": "b"}, {"default_machine": "b", "hover_machine": ""}):
            cfg = replace(self.cfg, **setting)
            display = MachineDisplay.from_legacy(cfg)
            self.assertEqual(display.visible(cfg), ("b",))
            self.assertFalse(display.select_new)
        self.assertEqual(self.display.with_selection(self.cfg, set()).visible(self.cfg), ())

    def test_order_moves_in_both_directions_and_keeps_hidden_slots(self):
        display = self.display.with_selection(self.cfg, {LOCAL, "b", "d"})
        first = display.move(self.cfg, display.visible(self.cfg), "d", 0)
        self.assertEqual(first.order, ("d", "a", LOCAL, "c", "b"))
        self.assertEqual(first.visible(self.cfg), ("d", LOCAL, "b"))
        up = first.move(self.cfg, first.visible(self.cfg), "b", 1)
        self.assertEqual(up.order, ("d", "a", "b", "c", LOCAL))
        last = up.move(self.cfg, up.visible(self.cfg), "d", 2)
        self.assertEqual(last.order, ("b", "a", LOCAL, "c", "d"))
        self.assertEqual(last.with_selection(self.cfg, set(last.order)).visible(self.cfg), last.order)
        self.assertEqual(self.cfg.tray_machine, "c")

    def test_profile_lifecycle_preserves_display_intent(self):
        checked = self.display.with_selection(self.cfg, {"b", "d"})
        changed = replace(self.cfg, targets=[
            Target(identifier="b", name="Renamed", enabled=False), self.cfg.targets[3],
            Target(identifier="new", name="New"),
        ])
        self.assertEqual(checked.with_targets(changed).order, (LOCAL, "b", "d", "new"))
        self.assertEqual(checked.with_targets(changed).selected, ("b", "d"))
        self.assertEqual(checked.with_targets(changed).visible(changed), ("d",))
        self.assertEqual(self.display.with_targets(changed).visible(changed), (LOCAL, "d", "new"))
        enabled = replace(changed, targets=[replace(changed.targets[0], enabled=True), *changed.targets[1:]])
        self.assertEqual(checked.with_targets(changed).with_targets(enabled).visible(enabled), ("b", "d"))

    def test_atomic_commit_and_rollback_compatibility(self):
        with tempfile.TemporaryDirectory(prefix="arm-display-test-") as temp:
            store = ConfigStore(Path(temp) / "settings.json")
            store.save(self.cfg)
            order = ("d", "a", "b", LOCAL, "c")
            saved = self.display.with_selection(self.cfg, {"b", "d"}, order)
            store.save_display(saved)
            initial = store.display_path.read_bytes()
            fresh = ConfigStore(store.path)
            self.assertEqual(fresh.load_display(fresh.load()), saved)
            with patch("arm.config.replace_durable", side_effect=OSError("replacement failed")):
                with self.assertRaisesRegex(OSError, "replacement failed"):
                    store.save_display(self.display)
            self.assertEqual(store.display_path.read_bytes(), initial)
            self.assertEqual(list(Path(temp).glob("*.tmp")), [])
            # A rolled-back executable can rewrite its existing settings file.
            store.save(replace(self.cfg, hover_machine=LOCAL, hover_range=300))
            self.assertEqual(fresh.load_display(fresh.load()), saved)
            self.assertEqual(fresh.load().hover_range, 300)


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

    def test_composite_picks_the_strongest_resource_sample(self):
        series = {"ram": [(15, 80), (29, None)], "cpu": [(15, 10), (29, 90)]}
        self.assertEqual(composite_samples(series, 30, 30, 3, 25),
                         [(15, 80, "ram"), (29, 90, "cpu")])

    def test_network_directions_share_scale_within_each_machine(self):
        target = Target(name="Remote")
        settings = Settings(targets=[target])
        coll = SimpleNamespace(settings=settings, history=History(),
                               statuses={m: Status(m, Connection.ONLINE) for m in (LOCAL, target.identifier)},
                               provider_status={}, intervals={})
        view = Dashboard(coll)
        for machine, rx, tx in ((LOCAL, 6144, 1024), (target.identifier, 2048, 4096)):
            coll.history.add(readings(machine, 28, TOTAL, {"net.total": (2**30, "B/s")}))
            coll.history.add(readings(machine, 29, TOTAL,
                                      {"net.receive": (rx, "B/s"), "net.transmit": (tx, "B/s")}))
        for machine, expected in ((LOCAL, (75, 12.5)), (target.identifier, (50, 100))):
            directions, scale, _ = view.series(machine, "net", tuple(NETWORK), TOTAL, 30, 30)
            self.assertEqual(tuple(directions[key][0][0][1] for key in NETWORK), expected)
            self.assertEqual(scale, 4096 if machine == target.identifier else 8192)
            self.assertTrue(all(directions[key][1].machine == machine for key in NETWORK))
        settings.net_scale = 16384
        self.assertEqual(view.series(target.identifier, "net", tuple(NETWORK), TOTAL, 30, 30)[1], 16384)

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
            cfg.hover_range = 300
            cfg.hover_machine = cfg.targets[0].identifier
            cfg.network_colors["net.receive"] = "#008801"
            store.save(cfg)
            self.assertEqual(store.load(), cfg)
            cfg.tray_machine = cfg.targets[0].identifier
            cfg.separate_tray_icons = True
            for selection in (ALL, LOCAL, cfg.targets[0].identifier):
                cfg.hover_machine = selection
                store.save(cfg)
                self.assertEqual(store.load(), cfg)
            cfg.hover_machine = "removed-host"
            store.save(cfg)
            self.assertEqual(store.load().hover_machine, "")
            self.assertNotIn('"password":', path.read_text(encoding="utf-8").lower())

    def test_legacy_machine_preferences_migrate(self):
        source = {
            "default_machine": "@peak", "hover_machine": "@peak", "hover_range": 300,
            "tray_mode": "Selected remote", "tray_remote": "remote-1", "mode": "Composite",
            "persistent": True, "network_colors": {"net.receive": "#008801"},
            "targets": [{"identifier": "remote-1", "name": "Test host", "credential": "test-reference"}],
        }
        with tempfile.TemporaryDirectory(prefix="arm-config-test-") as root:
            path = Path(root) / "settings.json"
            path.write_text(json.dumps(source), encoding="utf-8")
            store = ConfigStore(path)
            cfg = store.load()
            self.assertEqual((cfg.default_machine, cfg.hover_machine, cfg.hover_range), (ALL, ALL, 300))
            self.assertEqual((cfg.tray_machine, cfg.separate_tray_icons, cfg.mode), ("remote-1", False, "Composite"))
            self.assertEqual(monitor_choices(cfg), {LOCAL, ALL, "remote-1"})
            self.assertEqual(cfg.targets[0].credential, "test-reference")
            self.assertEqual(cfg.network_colors["net.receive"], "#008801")
            self.assertTrue(cfg.persistent)
            store.save(cfg)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue({"tray_mode", "tray_remote"}.isdisjoint(saved))
            self.assertEqual(store.load(), cfg)
        for legacy_tray, monitor, separate in (("Consolidated", ALL, False), ("Separate", "", True)):
            cfg = Settings.from_dict({"tray_mode": legacy_tray})
            self.assertEqual((cfg.tray_machine, cfg.hover_machine, cfg.separate_tray_icons),
                             (LOCAL, monitor, separate))
        for invalid_source in (ALL, "@peak", "removed-host", []):
            self.assertEqual(Settings.from_dict({"tray_machine": invalid_source}).tray_machine, LOCAL)

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
