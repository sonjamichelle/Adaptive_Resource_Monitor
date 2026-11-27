"""Run ARM against a private copy of authorized settings on a Windows desktop."""
import argparse
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
from time import monotonic, time
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from windows_gui import choose_display, start_isolated, verify_desktop


def evaluate(root, captures, restart, result):
    import psutil
    from PySide6.QtCore import QEventLoop, QPoint, QTimer
    from PySide6.QtWidgets import QApplication
    from arm.application import Application
    from arm.branding import set_windows_identity
    from arm.config import ConfigStore
    from arm.graphs import resource_series, tray_icon
    from arm.model import ALL, LOCAL, NETWORK, RESOURCES, TOTAL, Connection

    assert set_windows_identity() == 0
    app = QApplication([])
    assert app.platformName() == "windows"
    app.setQuitOnLastWindowClosed(False)
    session = Application(app, root)
    proc = psutil.Process()

    def wait(seconds, condition=None):
        if condition and condition():
            return
        loop = QEventLoop()
        timer = QTimer()
        timer.setInterval(100)
        if condition:
            timer.timeout.connect(lambda: loop.quit() if condition() else None)
            timer.start()
        QTimer.singleShot(round(seconds * 1000), loop.quit)
        loop.exec()
        timer.stop()
        if condition and not condition():
            state = {session.dashboard.name(m): str(session.dashboard.state(m))
                     for m in session.dashboard.monitored()}
            raise AssertionError(f"Readings not ready: {state}")

    def choose(value):
        choose_display(session, value)

    def measure(name, seconds=12):
        before, start = proc.cpu_times(), monotonic()
        wait(seconds)
        after, duration = proc.cpu_times(), monotonic() - start
        percent = (after.user + after.system - before.user - before.system) / duration * 100
        result.setdefault("overhead", {})[name] = {
            "seconds": round(duration, 2), "cpu_one_thread_pct": round(percent, 3),
            "cpu_workstation_pct": round(percent / psutil.cpu_count(), 3),
            "working_set_mib": round(proc.memory_info().rss / 2**20, 2),
        }

    def capture(widget, filename):
        app.processEvents()
        if captures:
            assert widget.grab().save(str(captures / (filename + ".png")))

    try:
        primary = session.scopes()[0]
        machines = session.dashboard.monitored()
        assert len(machines) == 4
        if restart:
            assert session.dashboard.machine_display.select_new and session.settings.hover_range == 300
            session.hover.show(primary)
            assert session.popup.displayed == tuple(machines) and session.popup.span == 300
            assert not session.popup.pinned
        wait(30, lambda: all(session.dashboard.state(m) == Connection.ONLINE for m in machines))
        history = session.collectors.history
        key = lambda m, metric: history.since(m, TOTAL, metric, time() - 60)
        wait(17, lambda: all(sum(r.valid for r in key(m, "ram.util")) >= 3 for m in machines))
        result["machines"] = {
            session.dashboard.name(m): {
                "interval": session.dashboard.interval(m),
                "ram_observations": len(key(m, "ram.util")),
                "network_rx_observations": len(key(m, "net.receive")),
                "network_tx_observations": len(key(m, "net.transmit")),
            } for m in machines
        }
        assert len({session.collectors.workers[m, "Linux SSH"].ident for m in machines if m != LOCAL}) == 3
        if restart:
            assert len(session.popup.sections) == 4
            capture(session.popup, "06-restored-selection")
            result["restored_selection"] = "All Systems, 5 minutes, unpinned"
            return

        measure("tray, four connected machines")
        session.hover.show(primary)
        choose(LOCAL)
        session.popup.refresh()
        assert session.popup.single.isVisible()
        assert all(card.isVisible() for card in session.popup.cards.values())
        assert [(session.popup.grid.getItemPosition(i)[0], session.popup.grid.getItemPosition(i)[1])
                for i in range(6)] == [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (2, 1)]
        capture(session.popup, "01-individual-hover")

        menu = session.menus[primary]
        icon_count = len(session.icons)
        menu.machines.master.click()
        assert menu.machines.master.isChecked() and len(session.icons) == icon_count
        with patch("arm.application.tray_icon", wraps=tray_icon) as draw:
            session.render()
            assert {call.args[1] for call in draw.call_args_list} == set(session.icons)
        section_keys = set(session.popup.sections)
        assert section_keys == set(machines)
        for machine, section in session.popup.sections.items():
            assert session.dashboard.name(machine) in section.title.text()
            assert "Connected" in section.title.text() and set(section.cards) == set(RESOURCES)
            cpu_plot = section.cards["cpu"].plot.data[0][0][0]
            cpu_samples = key(machine, "cpu.util")
            valid = {r.timestamp for r in cpu_samples if r.valid}
            assert set(t for t, v in cpu_plot if v is not None) <= valid
        assert app.primaryScreen().availableGeometry().contains(session.popup.frameGeometry())
        capture(session.popup, "02-all-systems-hover")
        assert session.popup.simultaneous.verticalScrollBar().maximum() == 0
        geometry = session.popup.geometry()
        session.popup.resize(680, 280)
        app.processEvents()
        assert session.popup.simultaneous.verticalScrollBar().maximum() > 0
        assert session.popup.simultaneous.horizontalScrollBar().maximum() > 0
        session.popup.setGeometry(geometry)
        measure("All Systems hover, four connected machines")

        session.popup.hide()
        session.open_expanded()
        assert session.expanded.displayed == tuple(machines) and set(session.expanded.sections) == set(machines)
        capture(session.expanded, "04-all-systems-expanded")
        assert session.expanded.simultaneous.horizontalScrollBar().maximum() == 0
        assert session.expanded.simultaneous.verticalScrollBar().maximum() == 0
        section = session.expanded.sections[LOCAL]
        section.table.show()
        session.expanded.refresh()
        assert section.table.rowCount() > 20
        section.table.hide()
        measure("All Systems expanded, four connected machines")
        session.expanded.showMinimized()
        session.expanded.showNormal()
        assert session.expanded.displayed == tuple(machines)
        session.expanded.close()

        session.hover.show(primary)
        def directional_sources():
            return [machine for machine in machines if all(
                any(r.valid and r.value > 0 for r in key(machine, metric))
                and len({r.value for r in key(machine, metric) if r.valid}) > 1
                for metric in NETWORK)]

        wait(20, directional_sources)
        available = directional_sources()
        loaded = [machine for machine in available if all((r := history.latest(machine, TOTAL, metric))
                  and r.valid and r.value > 0 for metric in NETWORK)]
        source = (loaded or available)[-1]
        choose(source)
        session.popup.refresh()
        net = session.popup.cards["net"]
        assert [color for _, color in net.plot.data[0]] == [color for _, color in resource_series("net", session.settings)]
        assert all(any(value is not None and value > 0 for _, value in points)
                   for points, _ in net.plot.data[0])
        result["directional_activity_machine"] = session.dashboard.name(source)
        result["directional_activity"] = {
            metric: {"nonzero_samples": sum(r.valid and r.value > 0 for r in key(source, metric)),
                     "distinct_rates": len({r.value for r in key(source, metric) if r.valid})}
            for metric in NETWORK
        }
        capture(session.popup, "05-network-in-out")

        chosen = machines[1]
        choose(chosen)
        session.collectors.disconnect(chosen)
        assert session.popup.displayed == (chosen,) and "Disconnected" in session.popup.header.text()
        assert session.store.load_display(session.settings).selected == (chosen,)
        session.collectors.reconnect(chosen)
        wait(25, lambda: session.dashboard.state(chosen) == Connection.ONLINE)
        assert session.popup.displayed == (chosen,)
        choose(ALL)
        session.popup.interval.setCurrentIndex(session.popup.interval.findData(300))
        session.set_pin(True)
        session.set_pin(False)
        outside = QPoint(-20000, -20000)
        # Exercise the production dismissal handler. Explorer has no icon
        # rectangle on the private desktop.
        with patch("arm.tray.QCursor", SimpleNamespace(pos=lambda: outside)), \
                patch.object(session.hover.cursor, "raw", return_value=outside), \
                patch("arm.tray.monotonic", side_effect=[100, 120]):
            session.hover.state.left = None
            session.hover.tick()
            session.hover.tick()
        assert session.popup.isHidden()
        session.hover.show(primary)
        assert session.popup.displayed == tuple(machines) and session.popup.span == 300
        assert session.expanded.displayed == tuple(machines)
        saved = ConfigStore(root / "settings.json").load()
        assert session.store.load_display(saved).select_new and saved.hover_range == 300
        result["retained_dismissal_pin_disconnect"] = True
    finally:
        session.close()


def main(args):
    if args.desktop:
        result = {"desktop": verify_desktop(args.desktop)}
        try:
            evaluate(args.work, args.captures, args.restart, result)
        except Exception:
            import traceback
            result["traceback"] = traceback.format_exc()
            return 1
        finally:
            (args.work / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return 0
    names = ("settings.json", "known_hosts")
    sources = [args.profile_dir / name for name in names]
    hash_inputs = lambda: [sha256(path.read_bytes()).digest() for path in sources]
    initial = hash_inputs()
    with TemporaryDirectory(prefix="arm-desktop-test-") as directory:
        work = Path(directory)
        for source in sources:
            shutil.copyfile(source, work / source.name)
        from arm.config import ConfigStore
        store = ConfigStore(work / "settings.json")
        original = store.load()
        store.save(replace(original, persistent=False, history_file=""))
        for restart in (False, True):
            desktop = f"ARM_Validation_{uuid4().hex[:10]}"
            command = [sys.executable, str(Path(__file__).resolve()), "--desktop", desktop, "--work", str(work)]
            if args.captures:
                command.extend(("--captures", str(args.captures.resolve(strict=True))))
            if restart:
                command.append("--restart")
            code = start_isolated(command, desktop)
            print((work / "result.json").read_text(encoding="utf-8"))
            if code:
                break
        assert store.load().targets == original.targets
        assert hash_inputs() == initial, "Production profile files changed"
        removed = sum(path.stat().st_size for path in work.rglob("*") if path.is_file())
    print(f"Private profile test exit {code}. Removed {removed:,} bytes; original profiles and SSH trust files verified.")
    return code


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-dir", type=Path)
    parser.add_argument("--captures", type=Path)
    parser.add_argument("--desktop")
    parser.add_argument("--work", type=Path)
    parser.add_argument("--restart", action="store_true")
    raise SystemExit(main(parser.parse_args()))
