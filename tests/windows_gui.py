"""Native Qt tests on a private Windows desktop without switching desktops."""
import argparse
import ctypes as ct
from ctypes import wintypes as w
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
from time import monotonic, sleep
from uuid import uuid4
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

USER = ct.WinDLL("user32", use_last_error=True)
KERNEL = ct.WinDLL("kernel32", use_last_error=True)


def bind(dll, name, result, *args):
    fn = getattr(dll, name)
    fn.restype, fn.argtypes = result, args
    return fn


class Startup(ct.Structure):
    _fields_ = [("cb", w.DWORD), ("reserved", w.LPWSTR), ("desktop", w.LPWSTR),
                ("title", w.LPWSTR)] + [(key, w.DWORD) for key in (
                    "x", "y", "width", "height", "cols", "rows", "fill", "flags")] + [
        ("show", w.WORD), ("reserved2_size", w.WORD), ("reserved2", ct.c_void_p),
        ("stdin", w.HANDLE), ("stdout", w.HANDLE), ("stderr", w.HANDLE),
    ]


class ProcessInfo(ct.Structure):
    _fields_ = [("process", w.HANDLE), ("thread", w.HANDLE), ("pid", w.DWORD), ("tid", w.DWORD)]


def start_isolated(argv, desktop_name, timeout=210):
    create_desktop = bind(USER, "CreateDesktopW", w.HANDLE,
                          w.LPCWSTR, w.LPCWSTR, ct.c_void_p, w.DWORD, w.DWORD, ct.c_void_p)
    close_desktop = bind(USER, "CloseDesktop", w.BOOL, w.HANDLE)
    desktop = create_desktop(desktop_name, None, None, 0, 0x01ff, None)
    if not desktop:
        raise ct.WinError(ct.get_last_error())
    close = bind(KERNEL, "CloseHandle", w.BOOL, w.HANDLE)
    create = bind(KERNEL, "CreateProcessW", w.BOOL, w.LPCWSTR, w.LPWSTR, ct.c_void_p,
                  ct.c_void_p, w.BOOL, w.DWORD, ct.c_void_p, w.LPCWSTR,
                  ct.POINTER(Startup), ct.POINTER(ProcessInfo))
    wait = bind(KERNEL, "WaitForSingleObject", w.DWORD, w.HANDLE, w.DWORD)
    status = bind(KERNEL, "GetExitCodeProcess", w.BOOL, w.HANDLE, ct.POINTER(w.DWORD))
    terminate = bind(KERNEL, "TerminateProcess", w.BOOL, w.HANDLE, w.UINT)
    launch = Startup()
    launch.cb, launch.desktop = ct.sizeof(Startup), f"WinSta0\\{desktop_name}"
    process = ProcessInfo()
    try:
        command = ct.create_unicode_buffer(subprocess.list2cmdline(argv))
        if not create(str(argv[0]), command, None, None, False, 0x08000000, None, str(ROOT),
                      ct.byref(launch), ct.byref(process)):
            raise ct.WinError(ct.get_last_error())
        try:
            if wait(process.process, timeout * 1000):
                terminate(process.process, 30)
                wait(process.process, 10_000)
                raise TimeoutError("Isolated Windows GUI test exceeded its time allowance")
            exit_code = w.DWORD()
            if not status(process.process, ct.byref(exit_code)):
                raise ct.WinError(ct.get_last_error())
            return exit_code.value
        finally:
            close(process.thread)
            close(process.process)
    finally:
        close_desktop(desktop)


def verify_desktop(expected):
    current_tid = bind(KERNEL, "GetCurrentThreadId", w.DWORD)()
    desk = bind(USER, "GetThreadDesktop", w.HANDLE, w.DWORD)(current_tid)
    get = bind(USER, "GetUserObjectInformationW", w.BOOL,
               w.HANDLE, ct.c_int, ct.c_void_p, w.DWORD, ct.POINTER(w.DWORD))
    buf, required = ct.create_unicode_buffer(256), w.DWORD()
    if not get(desk, 2, buf, ct.sizeof(buf), ct.byref(required)) or buf.value != expected:
        raise RuntimeError("Application test is not on the requested private desktop")
    return buf.value


def window_process(hwnd):
    pid = w.DWORD()
    thread = bind(USER, "GetWindowThreadProcessId", w.DWORD, w.HWND, ct.POINTER(w.DWORD))(hwnd, ct.byref(pid))
    return thread, pid.value


def run_frozen(exe, profile_root, output):
    from arm.config import ConfigStore, Settings, Target
    from arm.version import NAME, VERSION
    # Separate settings and logs for each run. Existing profiles stay untouched.
    appdir = profile_root / NAME
    env = dict(os.environ, LOCALAPPDATA=str(profile_root))
    for key in ("PYTHONPATH", "QT_QPA_PLATFORM", "QT_SCALE_FACTOR"):
        env.pop(key, None)
    config = ConfigStore(appdir / "settings.json")
    if not config.path.is_file():
        config.save(Settings(minimized=False, mode="Composite", targets=[
            Target(name="Saved test profile", host="127.0.0.1", enabled=False, credential="test-reference")
        ]))
    original = config.path.read_bytes()
    find = bind(USER, "FindWindowW", w.HWND, w.LPCWSTR, w.LPCWSTR)
    visible = bind(USER, "IsWindowVisible", w.BOOL, w.HWND)
    post = bind(USER, "PostMessageW", w.BOOL, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
    post_thread = bind(USER, "PostThreadMessageW", w.BOOL, w.DWORD, w.UINT, w.WPARAM, w.LPARAM)
    send = bind(USER, "SendMessageTimeoutW", ct.c_size_t, w.HWND, w.UINT, w.WPARAM, w.LPARAM,
                w.UINT, w.UINT, ct.POINTER(ct.c_size_t))
    for iteration in range(2):
        with subprocess.Popen([str(exe)], env=env, cwd=exe.parent) as proc:
            try:
                deadline, hwnd = monotonic() + 25, None
                while monotonic() < deadline and proc.poll() is None:
                    found = find(None, NAME)
                    if found:
                        thread, pid = window_process(found)
                        if pid == proc.pid and visible(found):
                            hwnd = found
                            break
                    sleep(.15)
                assert hwnd, f"Frozen application did not open its native window, exit {proc.poll()}"
                sleep(2.5)
                replacement = find(None, NAME)
                if replacement and window_process(replacement)[1] == proc.pid:
                    hwnd = replacement
                assert proc.poll() is None, f"Frozen application exited before close, code {proc.returncode}"
                icon = ct.c_size_t()
                assert send(hwnd, 0x7f, 1, 0, 2, 2000, ct.byref(icon)) and icon.value, "Missing window icon"
                if not post(hwnd, 0x10, 0, 0):
                    raise ct.WinError(ct.get_last_error())
                sleep(.45)
                assert proc.poll() is None and not visible(hwnd), "Window close should leave tray running"
                assert post_thread(thread, 0x12, 0, 0), "Posting WM_QUIT failed"
                assert proc.wait(10) == 0
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait(8)
        assert config.path.read_bytes() == original
        data = (appdir / "arm.log").read_text(encoding="utf-8")
        assert data.count(f"{NAME} {VERSION} starting") == iteration + 1
        assert data.count(f"{NAME} stopped") == iteration + 1
        assert all(word in data for word in ("Initializing provider CPU", "Initializing provider GPU"))
        assert " ERROR " not in data, data
    output["frozen_launches"] = 2
    output["frozen_version"] = VERSION


def verify_executable(path, version):
    import pefile
    from arm.branding import COPYRIGHT, ICON_SIZES, PUBLISHER

    pe = pefile.PE(str(path))
    try:
        assert pe.FILE_HEADER.Machine == 0x8664
        fields = next(node.StringTable[0].entries for block in pe.FileInfo for node in block
                      if hasattr(node, "StringTable"))
        assert fields[b"CompanyName"].decode().strip() == PUBLISHER
        assert fields[b"LegalCopyright"].decode().strip() == COPYRIGHT
        assert fields[b"ProductVersion"].decode().strip() == version
        group = next(entry for entry in pe.DIRECTORY_ENTRY_RESOURCE.entries if entry.id == 14)
        sizes = set()
        for ident in group.directory.entries:
            ref = ident.directory.entries[0].data.struct
            data = pe.get_data(ref.OffsetToData, ref.Size)
            count = struct.unpack_from("<H", data, 4)[0]
            sizes.update((data[6 + 14*i] or 256) for i in range(count))
        assert set(ICON_SIZES) <= sizes, (path.name, sizes)
    finally:
        pe.close()


def capture_native_window(hwnd, path):
    from PySide6.QtGui import QImage

    gdi = ct.WinDLL("gdi32", use_last_error=True)
    rect = w.RECT()
    assert bind(USER, "GetWindowRect", w.BOOL, w.HWND, ct.POINTER(w.RECT))(hwnd, ct.byref(rect))
    width, height = rect.right - rect.left, rect.bottom - rect.top
    dc = bind(gdi, "CreateCompatibleDC", w.HDC, w.HDC)(None)
    assert dc
    info = ct.create_string_buffer(struct.pack("<IiiHHIIiiII", 40, width, -height, 1, 32,
                                               0, 0, 0, 0, 0, 0))
    bits = ct.c_void_p()
    bitmap = bind(gdi, "CreateDIBSection", w.HBITMAP, w.HDC, ct.c_void_p, w.UINT,
                  ct.POINTER(ct.c_void_p), w.HANDLE, w.DWORD)(dc, info, 0, ct.byref(bits), None, 0)
    select = bind(gdi, "SelectObject", w.HANDLE, w.HDC, w.HANDLE)
    original = select(dc, bitmap)
    try:
        printed = bind(USER, "PrintWindow", w.BOOL, w.HWND, w.HDC, w.UINT)(hwnd, dc, 2)
        assert printed, "Windows installer did not paint into the capture"
        pixels = ct.string_at(bits.value, width * height * 4)
        picture = QImage(pixels, width, height, width * 4, QImage.Format.Format_RGB32)
        assert picture.save(str(path))
    finally:
        select(dc, original)
        bind(gdi, "DeleteObject", w.BOOL, w.HANDLE)(bitmap)
        bind(gdi, "DeleteDC", w.BOOL, w.HDC)(dc)


def run_installer_wizard(args, result, captures=None):
    from arm.version import NAME

    find = bind(USER, "FindWindowW", w.HWND, w.LPCWSTR, w.LPCWSTR)
    visible = bind(USER, "IsWindowVisible", w.BOOL, w.HWND)
    with subprocess.Popen([args[0], "/SILENT", *args[2:]]) as process:
        try:
            limit = monotonic() + 18
            while monotonic() < limit and process.poll() is None:
                wizard = find("TWizardForm", None)
                if wizard and visible(wizard):
                    caption = ct.create_unicode_buffer(512)
                    bind(USER, "GetWindowTextW", ct.c_int, w.HWND, w.LPWSTR, ct.c_int)(wizard, caption, 512)
                    if NAME in caption.value:
                        result["native_installer_wizard"] = caption.value
                        if captures:
                            capture_native_window(wizard, captures / "installer-wizard.png")
                        break
                sleep(.07)
        finally:
            code = process.wait(45)
    assert "native_installer_wizard" in result, "Installer wizard did not become visible on the private desktop"
    return code


def validate_packages(release, work, result, upgrade_from=None, captures=None):
    from arm.about import UNINSTALL_KEY
    from arm.branding import BUNDLED_ASSETS, PUBLISHER, SUPPORT_URL, WEBSITE, asset
    from arm.config import ConfigStore, Settings, Target
    from arm.version import NAME, VERSION
    stem = f"AdaptiveResourceMonitor-{VERSION}-windows-x64"
    portable, setup = release / f"{stem}-portable.zip", release / f"{stem}-setup.exe"
    exe = "AdaptiveResourceMonitor.exe"
    digests = {}
    for artifact in (portable, setup):
        with artifact.open("rb") as stream:
            digests[artifact.name] = hashlib.file_digest(stream, "sha256").hexdigest()
    for line in (release / "SHA256SUMS.txt").read_text(encoding="ascii").splitlines():
        digest, name = line.split("  ", 1)
        assert digests[name] == digest
    with ZipFile(portable) as package:
        assert package.testzip() is None
        package.extractall(work / "portable")
    payload = work / "portable" / "AdaptiveResourceMonitor"
    assert (payload / "VERSION.txt").read_text().strip() == VERSION
    assert json.loads((payload / "BUILD.json").read_text())["version"] == VERSION
    assert VERSION in (payload / "CHANGELOG.md").read_text(encoding="utf-8")
    assert (payload / "Third-party notices" / "README.md").is_file()
    for name in BUNDLED_ASSETS:
        assert (payload / "_internal" / "branding" / name).read_bytes() == asset(name).read_bytes()
    verify_executable(setup, VERSION)
    verify_executable(payload / exe, VERSION)
    result["verified_pe_icons_and_company_metadata"] = True
    run_frozen(payload / exe, work / "portable-profile", result)

    import winreg
    key = UNINSTALL_KEY
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, key, 0, winreg.KEY_READ | view):
                    raise RuntimeError("A pre-existing ARM installation prevents a disposable installer test")
            except FileNotFoundError:
                pass
    setup_copy = work / setup.name
    shutil.copyfile(setup, setup_copy)
    installed = work / "installed"
    profile = work / "installed-profile"
    configuration = profile / NAME / "settings.json"
    ConfigStore(configuration).save(Settings(minimized=False, mode="Composite", targets=[
        Target(name="Preserved test target", host="127.0.0.1", enabled=False, credential="arm-test-reference")
    ]))
    saved = configuration.read_bytes()
    history = profile / NAME / "preserve.sqlite"
    history.write_text("test data", encoding="utf-8")
    args = [str(setup_copy), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOICONS",
            "/TASKS=", f"/DIR={installed}", f"/LOG={work / 'install.log'}"]
    try:
        if upgrade_from:
            prior_copy = work / "prior-setup.exe"
            shutil.copyfile(upgrade_from, prior_copy)
            result["prior_install_exit"] = subprocess.run([str(prior_copy), *args[1:]], timeout=45).returncode
            assert result["prior_install_exit"] == 0
            assert (installed / exe).is_file()
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as item:
                result["upgraded_from"] = winreg.QueryValueEx(item, "DisplayVersion")[0]
            assert result["upgraded_from"] != VERSION
        for upgrade in (False, True):
            mode = "reinstall" if upgrade else ("upgrade" if upgrade_from else "install")
            code = (subprocess.run(args, timeout=45).returncode if upgrade
                    else run_installer_wizard(args, result, captures))
            result[f"{mode}_exit"] = code
            assert code == 0 and (installed / exe).is_file()
            assert configuration.read_bytes() == saved
            assert history.read_text(encoding="utf-8") == "test data"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as item:
                for field, value in (("Publisher", PUBLISHER), ("DisplayVersion", VERSION),
                                     ("URLInfoAbout", WEBSITE), ("HelpLink", SUPPORT_URL)):
                    assert winreg.QueryValueEx(item, field)[0] == value
                assert exe in winreg.QueryValueEx(item, "DisplayIcon")[0]
            if not upgrade:
                installed_result = {}
                run_frozen(installed / exe, profile, installed_result)
                result["installed_launches"] = installed_result["frozen_launches"]
                result["verified_installed_metadata"] = True
    finally:
        remove = next(iter(installed.glob("unins*.exe")), None)
        if remove:
            outcome = subprocess.run([str(remove), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                                     timeout=45)
            result["uninstall_exit"] = outcome.returncode
            assert outcome.returncode == 0 and not (installed / exe).exists()
            assert configuration.read_bytes() == saved
            assert history.read_text(encoding="utf-8") == "test data"


def verify_branding(session, results, captures=None):
    from PySide6.QtCore import QObject, QPoint, QTimer, QUrl, Slot
    from PySide6.QtGui import QDesktopServices, QImage
    from PySide6.QtWidgets import QLabel, QPushButton
    from arm.branding import (
        APPLICATION_ICON, APPLICATION_IMAGE, APPLICATION_LOGO, COMPANY_LOGO, ICON_SIZES,
        SUPPORT_URL, WEBSITE, asset,
    )
    from arm.model import ALL, LOCAL
    from arm.version import NAME, VERSION

    def check_alpha(image):
        rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
        alpha = bytes(rgba.constBits())[3::4]
        assert min(alpha) == 0 and max(alpha) == 255
        corners = ((0, 0), (rgba.width() - 1, 0), (0, rgba.height() - 1),
                   (rgba.width() - 1, rgba.height() - 1))
        assert all(rgba.pixelColor(x, y).alpha() <= 1 for x, y in corners)

    ico = asset(APPLICATION_ICON).read_bytes()
    count = struct.unpack_from("<H", ico, 4)[0]
    sizes = {}
    for i in range(count):
        width, height, _, _, _, _, length, offset = struct.unpack_from("<BBBBHHII", ico, 6 + i * 16)
        assert width == height
        frame = QImage.fromData(ico[offset:offset + length])
        assert frame.width() == (width or 256)
        check_alpha(frame)
        sizes[frame.width()] = True
    assert tuple(sorted(sizes)) == ICON_SIZES
    for name in (APPLICATION_IMAGE, APPLICATION_LOGO, COMPANY_LOGO):
        check_alpha(QImage(str(asset(name))))
    results["transparent_ico_frames"] = list(ICON_SIZES)

    menu = session.menus[LOCAL]
    assert menu.version.text() == VERSION and menu.local.isChecked()
    assert not menu.remote.menuAction().isVisible()
    actions = {action.text(): action for action in menu.actions()}
    assert "Check for Updates" not in actions
    actions[f"About {NAME}"].trigger()
    assert session.expanded.tabs.currentWidget() is session.about_page
    assert session.about_page.version.text() == VERSION
    assert VERSION in session.about_page.browser.toPlainText()
    assert not session.expanded.monitor_visible
    assert not session.about_page.app_image.picture.isNull()
    assert not session.about_page.company_image.picture.isNull()
    session.about_page.open_link("THIRD_PARTY.md")
    assert session.about_page.document_group.title() == "Third-party Notices"
    assert "CPython" in session.about_page.browser.toPlainText()
    session.about_page.open_link("README.md")
    assert "dynamic icon" in session.about_page.browser.toPlainText()
    session.about_page.open_link("CHANGELOG.md")

    details = []

    def inspect_details():
        dialog = session.qt.activeModalWidget()
        if dialog:
            details.extend(label.text() for label in dialog.findChildren(QLabel))
            dialog.reject()
    QTimer.singleShot(0, inspect_details)
    view = next(button for button in session.about_page.findChildren(QPushButton) if button.text() == "View Details")
    view.click()
    assert "Installation type" in details and "Source checkout" in details and VERSION in details

    class BrowserTarget(QObject):
        @Slot(QUrl)
        def receive(self, url):
            self.destination = url.toString()

    sink = BrowserTarget()
    QDesktopServices.setUrlHandler("https", sink, "receive")
    try:
        actions["Design Creations Website"].trigger()
        assert sink.destination == WEBSITE
        session.about_page.open_link(SUPPORT_URL)
        assert sink.destination == SUPPORT_URL
    finally:
        QDesktopServices.unsetUrlHandler("https")
    if captures:
        session.apply(replace(session.settings, theme="Dark"))
        session.qt.processEvents()
        pixmap = session.expanded.grab()
        assert round(pixmap.width() / pixmap.devicePixelRatio()) == session.expanded.width()
        scale = round(session.expanded.devicePixelRatioF() * 100)
        assert pixmap.save(str(captures / f"about-{scale}.png"))
        menu.popup(QPoint(20, 20))
        session.qt.processEvents()
        assert menu.grab().save(str(captures / f"tray-menu-{scale}.png"))
        menu.hide()
    actions["Resource History"].trigger()
    assert session.expanded.monitor_visible and session.expanded.span == 3600
    menu.all.trigger()
    assert session.popup.selected_machine == ALL and menu.all.isChecked()
    menu.local.trigger()
    assert session.popup.selected_machine == LOCAL
    session.popup.hide()
    session.expanded.close()
    results["verified_about_and_tray_actions"] = True


def evaluate_app(work, results, short=False, captures=None):
    import psutil
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon
    from arm.application import Application
    from arm.branding import set_windows_identity
    from arm.config import STATIC_TRAY_MODE, ConfigStore, Settings, Target
    from arm.dialogs import ConnectionsDialog, SettingsDialog
    from arm.model import LOCAL, TOTAL, Connection, RESOURCES
    from arm.providers.ssh import update_host_key
    from ssh_fixture import Fixture, SECRET
    from contextlib import ExitStack
    from unittest.mock import patch

    assert set_windows_identity() == 0
    app = QApplication([])
    assert QGuiApplication.platformName() == "windows"
    app.setQuitOnLastWindowClosed(False)
    root = work / "app"
    session = Application(app, root)
    process = psutil.Process()
    results["platform"] = app.platformName()
    results["qt_reports_system_tray"] = QSystemTrayIcon.isSystemTrayAvailable()
    results["scale"] = [screen.devicePixelRatio() for screen in app.screens()]

    def wait_for(condition, seconds=8):
        loop = QEventLoop()
        timer = QTimer()
        timer.setInterval(100)

        def check():
            if condition():
                loop.quit()

        if condition():
            return
        timer.timeout.connect(check)
        timer.start()
        QTimer.singleShot(seconds * 1000, loop.quit)
        loop.exec()
        timer.stop()
        assert condition(), "Expected condition did not arrive"

    def measure(label, seconds=12):
        usage = process.cpu_times()
        started = monotonic()
        loop = QEventLoop()
        QTimer.singleShot(round(seconds * 1000), loop.quit)
        loop.exec()
        ended = process.cpu_times()
        cpu = 100 * (ended.user + ended.system - usage.user - usage.system) / (monotonic() - started)
        results.setdefault("performance", {})[label] = {
            "cpu_percent_one_logical": round(cpu, 3),
            "cpu_percent_machine": round(cpu / (psutil.cpu_count() or 1), 3),
            "rss_mib": round(process.memory_info().rss / 2**20, 2),
            "seconds": seconds,
        }

    try:
        assert session.icons[LOCAL].icon().cacheKey() == session.brand_icon.cacheKey()
        resources = ("cpu.util", "gpu.util", "ram.util", "gpu.vram_pct", "disk.total", "net.total")
        wait_for(lambda: all((r := session.collectors.history.latest(LOCAL, TOTAL, key)) and r.valid
                             for key in resources), 12)
        results["local_resources"] = {key: round(session.collectors.history.latest(LOCAL, TOTAL, key).value, 2)
                                      for key in resources}
        results["gpu_devices"] = [d.name for d in session.collectors.devices[LOCAL].values() if d.kind == "gpu"]
        results["per_gpu"] = {
            device.name: {
                metric: round(item.value, 2)
                for metric in ("gpu.util", "gpu.vram_total", "gpu.vram_used", "gpu.temperature", "gpu.power")
                if (item := session.collectors.history.latest(LOCAL, device.identifier, metric)) and item.valid
            }
            for device in session.collectors.devices[LOCAL].values() if device.kind == "gpu"
        }
        results["physical_disks"] = [d.name for d in session.collectors.devices[LOCAL].values() if d.kind == "disk"]
        if not short:
            measure("tray")
        results["registered_icon_rect"] = bool(session.icons[LOCAL].geometry().isValid())
        session.render()
        assert session.icons[LOCAL].icon().cacheKey() != session.brand_icon.cacheKey()
        verify_branding(session, results, captures)
        menu = session.menus[LOCAL]
        modes = {}
        for mode in ("Stacked", STATIC_TRAY_MODE, "Overlay", "Composite"):
            menu.modes[mode].trigger()
            assert menu.modes[mode].isChecked() and session.settings.mode == mode
            qr = session.icons[LOCAL].icon().pixmap(32, 32).toImage()
            modes[mode] = hashlib.sha256(bytes(qr.bits())).hexdigest()[:12]
            assert (session.icons[LOCAL].icon().cacheKey() == session.brand_icon.cacheKey()) == (mode == STATIC_TRAY_MODE)
        assert len(set(modes.values())) == 4, modes
        results["rendered_modes"] = modes
        assert ConfigStore(root / "settings.json").load().mode == "Composite"
        menu.pin.trigger()
        assert session.popup.isVisible() and session.popup.pinned
        assert sum(card.isVisible() for card in session.popup.cards.values()) == len(RESOURCES)
        wait_for(lambda: session.popup.frameGeometry().isValid())
        if not short:
            measure("pinned_popup")
        session.popup.pin.click()
        assert not session.popup.pinned
        session.popup.hide()
        session.open_expanded(LOCAL)
        assert session.expanded.isVisible() and session.expanded.table.rowCount() > 20
        assert session.expanded.device.count() > 10
        assert app.primaryScreen().availableGeometry().contains(session.popup.frameGeometry())
        if not short:
            measure("expanded")
        session.expanded.close()
        assert not session.expanded.isVisible() and session.icons[LOCAL].isVisible()
        if not short:
            prefs, connections = SettingsDialog(session), ConnectionsDialog(session)
            prefs.show()
            connections.show()
            assert prefs.isVisible() and connections.isVisible()
            assert prefs.tabs.count() == 7 and connections.table.rowCount() == 0
            prefs.close()
            connections.close()
            prefs.deleteLater()
            connections.deleteLater()
        with ExitStack() as stack:
            servers = [stack.enter_context(Fixture()) for _ in range(1 if short else 2)]
            targets = []
            for i, server in enumerate(servers, 1):
                target = Target(name=f"Loopback {i}", host="127.0.0.1", port=server.port,
                                username="tester", interval=2, timeout=6, tray=True)
                update_host_key(session.hosts, f"[127.0.0.1]:{server.port}", server.key)
                session.save_target(target, SECRET, False)
                targets.append(target)
                try:
                    wait_for(lambda: session.dashboard.state(target.identifier) == Connection.ONLINE, 15)
                except AssertionError as exc:
                    raise AssertionError(f"SSH fixture {i}: {server.connections} TCP sessions, "
                                         f"{len(server.commands)} commands, {server.samples} frames, "
                                         f"{session.dashboard.state(target.identifier)}") from exc
                assert "Connected" in menu.remote_entries[target.identifier].text()
                from arm.graphs import tray_icon
                with patch("arm.application.tray_icon", wraps=tray_icon) as draw:
                    menu.remote_entries[target.identifier].trigger()
                    assert draw.call_args.args[1] == target.identifier
                assert session.popup.selected_machine == target.identifier
                menu.local.trigger()
                session.popup.hide()
                if i == 1 and not short:
                    measure("one_loopback_ssh")
            if not short:
                measure("two_loopback_ssh")
            session.apply(replace(session.settings, tray_mode="Separate", persistent=True))
            assert set(session.icons) == {LOCAL, *(target.identifier for target in targets)}
            results["loopback_frame_counts"] = [server.samples for server in servers]
            for target in targets:
                session.collectors.disconnect(target.identifier)
            assert all(session.dashboard.state(t.identifier) == Connection.OFFLINE for t in targets)
            session.apply(replace(session.settings, tray_mode="Local", persistent=False))
            if not short:
                measure("disconnected_remotes")
            session.apply(replace(session.settings, tray_mode="Consolidated"))
            assert len(session.icons) == 1
            for target in list(session.settings.targets):
                session.remove_target(target)
        exit_action = next(action for action in next(iter(session.menus.values())).actions()
                           if action.text().startswith("Exit Adaptive Resource Monitor"))
        QTimer.singleShot(0, exit_action.trigger)
        assert app.exec() == 0
    finally:
        for target in list(session.settings.targets):
            session.remove_target(target)
        session.close()
    assert not session.collectors.workers
    data = (root / "arm.log").read_text(encoding="utf-8")
    assert "Adaptive Resource Monitor stopped" in data and " ERROR " not in data, data


def child(args):
    result = {"desktop": verify_desktop(args.desktop)}
    try:
        if args.package:
            validate_packages(args.package, args.work, result, args.upgrade_from, args.captures)
        else:
            evaluate_app(args.work, result, args.short, args.captures)
    except Exception:
        import traceback
        result["traceback"] = traceback.format_exc()
        log = args.work / "app" / "arm.log"
        if log.is_file():
            result["application_log"] = log.read_text(encoding="utf-8").splitlines()[-35:]
        for name in ("portable-profile", "installed-profile"):
            log = args.work / name / "Adaptive Resource Monitor" / "arm.log"
            if log.is_file():
                result[name] = log.read_text(encoding="utf-8").splitlines()[-35:]
        return 1
    finally:
        (args.work / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0


def parent(args):
    desktop = f"ARM_Validation_{uuid4().hex[:10]}"
    with tempfile.TemporaryDirectory(prefix="arm-desktop-test-") as directory:
        work = Path(directory)
        command = [sys.executable, str(Path(__file__).resolve()), "--desktop", desktop, "--work", str(work)]
        if args.package:
            command.extend(("--package", str(args.package.resolve())))
        if args.upgrade_from:
            command.extend(("--upgrade-from", str(args.upgrade_from.resolve())))
        if args.captures:
            command.extend(("--captures", str(args.captures.resolve(strict=True))))
        if args.short:
            command.append("--short")
        exit_code = start_isolated(command, desktop)
        data = work / "result.json"
        if data.is_file():
            print(data.read_text(encoding="utf-8"))
        elif exit_code == 0:
            raise RuntimeError("Isolated Windows process did not publish test evidence")
        staged = sum(path.stat().st_size for path in work.rglob("*") if path.is_file())
    print(f"Isolated Windows test exit {exit_code}. Removed {staged:,} bytes of temporary QA data.")
    return exit_code


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desktop")
    parser.add_argument("--work", type=Path)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--upgrade-from", type=Path)
    parser.add_argument("--captures", type=Path)
    parser.add_argument("--short", action="store_true")
    args = parser.parse_args()
    if args.desktop:
        raise SystemExit(child(args))
    raise SystemExit(parent(args))
