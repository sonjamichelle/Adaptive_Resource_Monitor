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


def validate_packages(release, work, result, upgrade_from=None, captures=None, portable_only=False):
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
    assert (payload / "LICENSE.md").read_bytes() == (ROOT / "LICENSE.md").read_bytes()
    assert "Redistributions in binary form" in (
        payload / "Third-party notices" / "NVIDIA-NVML-Python-LICENSE.txt").read_text(encoding="utf-8")
    for name in ("LGPL-3.0-only.txt", "GPL-3.0-only.txt"):
        assert (payload / "Third-party notices" / name).read_bytes() == (
            ROOT / "packaging" / "qt-notices" / name).read_bytes()
    assert not list((payload / "_internal").rglob("*[Vv]irtual[Kk]eyboard*"))
    for name in BUNDLED_ASSETS:
        assert (payload / "_internal" / "branding" / name).read_bytes() == asset(name).read_bytes()
    verify_executable(setup, VERSION)
    verify_executable(payload / exe, VERSION)
    result["verified_pe_icons_and_company_metadata"] = True
    run_frozen(payload / exe, work / "portable-profile", result)
    if portable_only:
        return

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
    assert menu.version.text() == VERSION and menu.machines.entries[LOCAL].isChecked()
    assert tuple(menu.machines.entries) == (LOCAL,)
    actions = {action.text(): action for action in menu.actions()}
    assert "Check for Updates" in actions
    actions[f"About {NAME}"].trigger()
    assert session.expanded.tabs.currentWidget() is session.about_page
    assert session.about_page.version.text() == VERSION
    assert VERSION in session.about_page.browser.toPlainText()
    assert not session.expanded.monitor_visible
    assert not session.about_page.app_image.picture.isNull()
    assert not session.about_page.company_image.picture.isNull()
    assert session.about_page.view_license.isEnabled()
    assert any(label.text() == "DC-ANCSA v1.0" for label in session.about_page.findChildren(QLabel))
    seen_geometry = []

    def inspect_license():
        from arm.software_license import LicenseDialog
        dialog = session.qt.activeModalWidget()
        assert isinstance(dialog, LicenseDialog)
        content = dialog.browser.toPlainText()
        assert "Design Creations Attribution-NonCommercial-ShareAlike License" in content
        assert "Additional permissions and reserved rights" in content
        assert dialog.browser.isReadOnly() and dialog.browser.verticalScrollBar().maximum() > 0
        if not seen_geometry:
            dialog.move(80, 90)
            dialog.resize(650, 530)
        else:
            assert dialog.geometry() == seen_geometry[0]
        seen_geometry.append(dialog.geometry())
        dialog.reject()

    for _ in range(2):
        QTimer.singleShot(0, inspect_license)
        session.about_page.view_license.click()
    assert len(seen_geometry) == 2
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
    view = next(button for button in session.about_page.findChildren(QPushButton) if button.text() == "Application Details")
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
    menu.machines.master.click()
    assert session.popup.displayed == () and not menu.machines.master.isChecked()
    menu.machines.entries[LOCAL].click()
    assert session.popup.displayed == (LOCAL,)
    session.popup.hide()
    session.expanded.close()
    results["verified_about_and_tray_actions"] = True


def choose_display(session, machine):
    from arm.model import ALL

    display = session.dashboard.machine_display
    checked = set(display.order) if machine == ALL else {machine}
    session.save_display(display.with_selection(session.settings, checked), session.popup)


def verify_update_notices(session, wait_for, results, captures):
    from PySide6.QtCore import QPoint
    from unittest.mock import patch
    from arm.model import ALL, LOCAL
    from arm.update_client import Check
    from arm.update_release import verify_manifest
    from arm.update_state import Phase
    from test_updates import NEW, PACKAGE, Response, UpdateTests

    def capture(widget, filename):
        session.qt.processEvents()
        if captures:
            assert widget.grab().save(str(captures / filename))

    menu = session.menus[LOCAL]
    hover, expanded = session.popup, session.expanded
    update = session.about_page.updates
    assert not menu.update.isVisible() and hover.update_banner.isHidden()
    initial_size = hover.popup_size()
    notices = []
    update.notify.connect(notices.append)
    rejected = Check(NEW, None, ("Fixture signature rejected",))
    with patch.object(update.client, "check", return_value=rejected):
        update.check_now()
        wait_for(lambda: update.job is None)
    assert not menu.update.isVisible() and not notices

    fixture = UpdateTests()
    try:
        fixture.setUp()
        release = verify_manifest(fixture.sign(fixture.metadata()), fixture.public)
        checked = Check(NEW, release, ())
        with patch.object(update.client, "check", return_value=checked):
            for _ in range(2):
                update.check_now()
                wait_for(lambda: update.job is None)
        available = f"Update Available: {NEW}"
        assert update.phase is Phase.AVAILABLE and notices == [available]
        assert menu.actions()[1] is menu.update and menu.update.text() == available
        session.hover.show(LOCAL)
        assert hover.popup_size().height() > initial_size.height()
        assert hover.update_banner.label.text() == available
        capture(hover, "update-hover.png")
        choose_display(session, ALL)
        session.hover.pin(True, LOCAL)
        assert hover.update_banner.isVisible() and hover.displayed == tuple(session.dashboard.monitored())
        session.hover.pin(False)
        choose_display(session, LOCAL)
        hover.hide()
        session.open_expanded()
        assert expanded.update_banner.isVisible() and expanded.monitor_visible
        capture(expanded, "update-expanded.png")
        menu.popup(QPoint(20, 20))
        capture(menu, "update-tray-menu.png")
        menu.hide()
        menu.update.trigger()
        assert expanded.tabs.currentWidget() == session.about_page and expanded.update_banner.isVisible()
        capture(expanded, "update-about.png")

        with patch.object(update.client, "open", return_value=Response(PACKAGE)):
            update.client.source["public_key"], original_key = fixture.public, update.client.source["public_key"]
            try:
                update.download_now()
                wait_for(lambda: update.job is None)
                assert update.phase is Phase.READY and update.downloaded.is_file()
                update.defer_install()
                assert menu.update.text() == f"Update Ready to Install: {NEW}"
                assert update.restore()[1][1] == update.downloaded
            finally:
                update.client.source["public_key"] = original_key
        update.downloaded.unlink()
        update.downloaded = None
        with patch.object(update.client, "check", return_value=rejected):
            update.check_now()
            wait_for(lambda: update.job is None)
        assert not menu.update.isVisible() and expanded.update_banner.isHidden()
        assert hover.popup_size() == initial_size
        update.accept_outcome((Phase.SUCCESS, "ARM installed and restarted."))
        confirmation = update.root / "confirmation.json"
        before = confirmation.read_bytes()
        assert hover.update_banner.label.text() and expanded.update_banner.label.text()
        assert hover.update_banner.action.text() == "View Changelog"
        session.hover.pin(True, LOCAL)
        expanded.showMinimized()
        session.qt.processEvents()
        hover.update_banner.action.click()
        assert not expanded.isMinimized() and expanded.tabs.currentWidget() is session.about_page
        assert session.about_page.document_group.title() == "Change Log"
        assert hover.update_banner.isHidden() and expanded.update_banner.isHidden()
        assert confirmation.read_bytes() == before
        session.hover.pin(False)
        hover.hide()
        expanded.close()
    finally:
        fixture.doCleanups()
    results["verified_shared_update_notices"] = "Verified, ready, rejected, deferred and duplicate notification states"


def verify_hover_version(session, remote, results, captures):
    from arm.model import ALL, LOCAL
    from arm.version import VERSION

    original = session.settings
    display = session.dashboard.machine_display
    hover = session.popup
    scale = round(hover.devicePixelRatioF() * 100)
    modes = (
        ("individual-unpinned", LOCAL, LOCAL, False),
        ("individual-pinned", remote, remote, True),
        ("all-systems-unpinned", ALL, LOCAL, False),
        ("all-systems-pinned", ALL, remote, True),
    )
    try:
        for theme in ("Light", "Dark"):
            session.apply(replace(original, theme=theme))
            for name, selection, anchor, pinned in modes:
                session.hover.pin(False)
                choose_display(session, selection)
                session.hover.show(anchor)
                session.hover.pin(pinned, anchor)
                session.qt.processEvents()
                label = hover.version_label
                rect = label.geometry()
                assert hover.isVisible() and hover.pinned == pinned
                expected = tuple(session.dashboard.monitored()) if selection == ALL else (selection,)
                assert hover.displayed == expected and session.hover.anchor == anchor
                assert label.isVisible() and label.text() == VERSION
                assert rect.bottom() < hover.machine.geometry().top()
                assert rect.right() == hover.width() - hover.layout().contentsMargins().right() - 1
                assert label.fontMetrics().horizontalAdvance(VERSION) <= rect.width()
                assert hover.rect().contains(rect)
                if captures and theme == ("Light" if scale > 100 else "Dark"):
                    capture_native_window(int(hover.winId()), captures / f"hover-{name}-{scale}.png")
    finally:
        session.hover.pin(False)
        hover.hide()
        session.apply(original)
        session.save_display(display, hover)
    results["hover_version"] = {"version": VERSION, "scale_percent": scale,
                                "themes": ["Light", "Dark"], "views": [row[0] for row in modes]}


def verify_machine_display(session, wait_for, results, captures):
    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
    from PySide6.QtGui import QKeyEvent, QMouseEvent
    from PySide6.QtTest import QTest
    from arm.dialogs import ConnectionsDialog
    from arm.model import ALL, LOCAL, TOTAL, Connection
    from unittest.mock import patch

    app, hover, expanded = session.qt, session.popup, session.expanded
    local, rain, phantom, lamp, phantomnet = session.dashboard.machines()
    tray = session.menus[session.scopes()[0]].machines
    menu = hover.machine.checklist
    history = session.collectors.history
    workers = dict(session.collectors.workers)
    left, released = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton

    def capture(widget, filename):
        app.processEvents()
        if captures:
            QTest.qWait(100)
            capture_native_window(int(widget.winId()), captures / filename)

    def pointer(widget, kind, point):
        button = released if kind == QEvent.Type.MouseMove else left
        buttons = released if kind == QEvent.Type.MouseButtonRelease else left
        event = QMouseEvent(kind, QPointF(widget.mapFromGlobal(point)), QPointF(point), button, buttons,
                            Qt.KeyboardModifier.NoModifier)
        app.sendEvent(widget, event)
        app.processEvents()

    def drag_to(drag, widget, start, end, cancel=False, scroll_to_end=False):
        pointer(widget, QEvent.Type.MouseButtonPress, start)
        pointer(widget, QEvent.Type.MouseMove, end)
        assert drag.active and drag.line.isVisible()
        if scroll_to_end:
            bar = drag.scroll.verticalScrollBar()
            wait_for(lambda: bar.value() == bar.maximum())
        if cancel:
            app.sendEvent(widget, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
        pointer(widget, QEvent.Type.MouseButtonRelease, end)
        assert not drag.active and not drag.line.isVisible()

    def persisted():
        return session.store.load_display(session.store.load())

    choose_display(session, ALL)
    session.hover.show(local)
    menu.popup(hover.machine.mapToGlobal(hover.machine.rect().bottomLeft()))
    app.processEvents()
    assert menu.isVisible() and hover.interaction_active
    assert menu.master.checkState() == Qt.CheckState.Checked
    combos = (
        ("none", set(), "No Systems Selected"),
        ("rain", {rain}, "Rain"),
        ("rain-phantom", {rain, phantom}, "2 Systems Selected"),
        ("lamp-phantomnet", {lamp, phantomnet}, "2 Systems Selected"),
        ("local-rain-phantomnet", {local, rain, phantomnet}, "3 Systems Selected"),
        ("all", {local, rain, phantom, lamp, phantomnet}, "All Systems"),
    )
    for name, wanted, label in combos:
        before = set(hover.displayed)
        if name in ("none", "all"):
            QTest.mouseClick(menu.master, left)
            assert menu.isVisible() and hover.isVisible(), (name, menu.isVisible(), hover.isVisible())
        else:
            for machine in sorted(before ^ wanted):
                QTest.mouseClick(menu.entries[machine], left)
                assert menu.isVisible() and hover.isVisible(), (name, menu.isVisible(), hover.isVisible())
                assert persisted().visible(session.settings) == hover.displayed == expanded.displayed
        checked = Qt.CheckState.Unchecked if not wanted else (
            Qt.CheckState.Checked if len(wanted) == 5 else Qt.CheckState.PartiallyChecked)
        assert set(hover.displayed) == wanted and menu.master.checkState() == tray.master.checkState() == checked
        assert hover.empty.isVisible() == (not wanted)
        assert hover.single.isVisible() == (len(wanted) == 1)
        assert hover.simultaneous.isVisible() == (len(wanted) > 1)
        assert hover.machine.text() == label
        assert hover.machine.width() >= hover.machine.fontMetrics().horizontalAdvance(label) + 24
        if name == "rain":
            observed = history.latest(phantom, TOTAL, "ram.util")
            assert observed is not None
            wait_for(lambda: history.latest(phantom, TOTAL, "ram.util").timestamp > observed.timestamp)
        if name == "rain-phantom":
            assert history.since(phantom, TOTAL, "ram.util", 0)[-2].timestamp <= observed.timestamp
            assert any(value is not None for _, value in hover.sections[phantom].cards["ram"].plot.data[0][0][0])
            capture(menu, "machine-checkbox-dropdown.png")
        capture(hover, f"machine-selection-{name}.png")
    app.sendEvent(menu, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    assert not menu.isVisible()
    menu.popup(hover.machine.mapToGlobal(hover.machine.rect().bottomLeft()))
    app.processEvents()
    pointer(menu, QEvent.Type.MouseButtonPress, menu.mapToGlobal(QPoint(-25, -25)))
    assert not menu.isVisible()
    app.processEvents()

    viewport = hover.simultaneous.viewport()
    local_card = hover.sections[local].cards["ram"].plot
    section_objects = dict(hover.sections)
    viewport_origin = lambda: viewport.mapToGlobal(QPoint(viewport.width() // 2, 3))
    point = lambda w: w.mapToGlobal(w.rect().center())
    bottom = viewport.mapToGlobal(QPoint(viewport.width() // 2, viewport.height() - 3))
    before = persisted()
    drag_to(hover.drag, local_card, point(local_card), bottom, cancel=True)
    assert persisted() == before
    drag_to(hover.drag, local_card, point(local_card), bottom, scroll_to_end=True)
    assert hover.displayed == (rain, phantom, lamp, phantomnet, local)
    assert persisted().order == hover.displayed and hover.sections == section_objects
    assert tuple(tray.entries) == hover.displayed
    session.set_pin(True)
    first_header = hover.sections[rain].title
    last_header = hover.sections[local].title
    drag_to(hover.drag, last_header, point(last_header), viewport_origin())
    assert hover.displayed.index(local) < 4 and hover.pinned
    hover.simultaneous.ensureWidgetVisible(first_header, 0, 0)
    app.processEvents()
    session.set_pin(False)
    session.open_expanded()
    view = expanded.simultaneous.viewport()
    start = expanded.displayed[1]
    top = view.mapToGlobal(QPoint(view.width() // 2, 3))
    drag_to(expanded.drag, expanded.sections[start].title, point(expanded.sections[start].title), top)
    assert expanded.displayed[0] == start and expanded.displayed == hover.displayed
    capture(expanded, "machine-order-expanded.png")
    manager = ConnectionsDialog(session)
    manager.show()
    app.processEvents()
    try:
        remote, first = manager.identifiers[-1], manager.identifiers[0]
        rows = dict(manager.row_rects())
        viewport = manager.table.viewport()
        local_slot = hover.displayed.index(local)
        drag_to(manager.drag, viewport, viewport.mapToGlobal(rows[remote].center()),
                viewport.mapToGlobal(rows[first].topLeft() + QPoint(15, 1)))
        assert manager.identifiers[0] == remote and hover.displayed.index(local) == local_slot
        assert manager.identifiers == tuple(machine for machine in hover.displayed if machine != local)
        capture(manager, "machine-order-remote-targets.png")
    finally:
        manager.close()
        manager.deleteLater()

    tray.entries[phantom].click()
    assert phantom not in hover.displayed and phantom not in expanded.displayed
    assert menu.entries[phantom].checkState() == Qt.CheckState.Unchecked
    tray.entries[phantom].click()
    assert persisted().visible(session.settings) == hover.displayed
    assert session.collectors.history is history and session.collectors.workers == workers
    assert all(session.dashboard.state(machine) == Connection.ONLINE for machine in hover.displayed)
    before = persisted()
    with patch.object(session.store, "save_display", side_effect=OSError("Fixture write failed")), \
            patch("arm.application.QMessageBox.warning") as shown, patch("arm.application.LOG.exception"):
        tray.entries[phantom].click()
        shown.assert_called_once()
        assert tray.entries[phantom].isChecked() and persisted() == before
    expanded.close()
    hover.hide()
    session.hover.show(local)
    assert hover.displayed == before.visible(session.settings)
    hover.simultaneous.verticalScrollBar().setValue(0)
    capture(hover, "machine-order-hover.png")
    hover.hide()
    results["machine_display"] = {
        "checkbox_combinations": [name for name, _, _ in combos],
        "shared_drag_interfaces": ["hover", "expanded", "Remote Targets"],
        "final_order": [session.dashboard.name(machine) for machine in before.order],
        "saved_before_close": True, "cancelled_drag_and_failed_write_retained_order": True,
        "unchanged_collectors_and_hidden_history": True,
    }


def evaluate_app(work, results, short=False, captures=None):
    import psutil
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication, QDialogButtonBox, QSystemTrayIcon
    from arm.application import Application
    from arm.branding import set_windows_identity
    from arm.config import STATIC_TRAY_MODE, ConfigStore, Settings, Target
    from arm.dialogs import ConnectionsDialog
    from arm.model import ALL, LOCAL, NETWORK, TOTAL, Connection, RESOURCES
    from arm.providers.ssh import update_host_key
    from ssh_fixture import Fixture, SECRET
    from contextlib import ExitStack
    from threading import Event
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
        from arm.update_client import Check
        update = session.about_page.updates
        lookup = next(action for action in menu.actions() if action.text() == "Check for Updates")
        entered, release_check = Event(), Event()

        def slow_check(version, kind):
            entered.set()
            assert release_check.wait(10)
            return Check(None, None, ())

        wait_for(lambda: update.job is None)
        with patch.object(update.client, "check", side_effect=slow_check):
            try:
                sample = session.collectors.last[LOCAL]
                lookup.trigger()
                assert session.expanded.tabs.currentWidget() is session.about_page
                wait_for(entered.is_set)
                assert not update.buttons["Check for Updates"].isEnabled()
                wait_for(lambda: session.collectors.last[LOCAL] > sample)
            finally:
                release_check.set()
            wait_for(lambda: update.job is None)
        assert update.fields["Latest published"].text() == "No public releases"
        assert "UTC" in update.fields["Last successful check"].text()
        session.expanded.close()
        verify_update_notices(session, wait_for, results, captures)
        results["asynchronous_update_check_with_live_telemetry"] = True
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
        session.activate_icon(LOCAL, QSystemTrayIcon.ActivationReason.Trigger)
        assert session.popup.isVisible() and not session.popup.pinned
        assert all(action.text() != "Pin Resource Monitor" for action in menu.actions())
        session.popup.pin.click()
        assert session.popup.isVisible() and session.popup.pinned
        session.activate_icon(LOCAL, QSystemTrayIcon.ActivationReason.Trigger)
        assert session.popup.pinned
        assert sum(card.isVisible() for card in session.popup.cards.values()) == len(RESOURCES)
        wait_for(lambda: session.popup.frameGeometry().isValid())
        if not short:
            measure("pinned_popup")
        session.popup.pin.click()
        assert not session.popup.pinned
        session.popup.hide()
        session.open_expanded()
        assert session.expanded.isVisible() and session.expanded.table.rowCount() > 20
        assert session.expanded.device.count() > 10
        assert app.primaryScreen().availableGeometry().contains(session.popup.frameGeometry())
        if not short:
            measure("expanded")
        prefs = session.settings_page
        assert [session.expanded.tabs.tabText(index) for index in range(session.expanded.tabs.count())] == [
            "Resource Monitor", "Settings", "About",
        ]
        session.expanded.tabs.setCurrentWidget(prefs)
        assert prefs.isVisible() and prefs.tabs.count() == 7
        minimized = session.settings.minimized
        control = prefs.controls["minimized"].__self__
        control.setChecked(not minimized)
        session.expanded.tabs.setCurrentWidget(session.expanded.resource_page)
        session.expanded.showMinimized()
        next(action for action in menu.actions() if action.text() == "Settings").trigger()
        assert session.expanded.tabs.currentWidget() is prefs and not session.expanded.isMinimized()
        assert prefs.controls["minimized"]() == (not minimized)
        buttons = prefs.findChild(QDialogButtonBox)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).click()
        assert prefs.controls["minimized"]() == minimized
        prefs.controls["minimized"].__self__.setChecked(not minimized)
        previous_range = session.settings.hover_range
        changed_range = 300 if previous_range != 300 else 60
        session.remember_monitor(changed_range)
        buttons.button(QDialogButtonBox.StandardButton.Save).click()
        saved = session.store.load()
        assert saved.minimized == (not minimized) and saved.hover_range == changed_range
        assert session.expanded.tabs.currentWidget() is prefs
        session.remember_monitor(previous_range)
        results["shared_settings_tab"] = "Main window and tray entry, draft retention, Cancel, and Save"
        session.expanded.close()
        assert not session.expanded.isVisible() and session.icons[LOCAL].isVisible()
        if not short:
            connections = ConnectionsDialog(session)
            connections.show()
            assert connections.isVisible() and connections.table.rowCount() == 0
            connections.close()
            connections.deleteLater()
        with ExitStack() as stack:
            servers = [stack.enter_context(Fixture()) for _ in range(2)]
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
                choose_display(session, target.identifier)
                assert menu.machines.entries[target.identifier].isChecked()
                assert session.popup.displayed == (target.identifier,)
                assert session.scopes() == [LOCAL]
                choose_display(session, LOCAL)
                session.popup.hide()
                if i == 1 and not short:
                    measure("one_loopback_ssh")
            if not short:
                measure("two_loopback_ssh")
            from arm.graphs import tray_icon
            primary, other = (target.identifier for target in targets)
            session.open_settings()
            tray_machine = prefs.controls["tray_machine"].__self__
            assert [tray_machine.itemData(i) for i in range(tray_machine.count())] == [LOCAL, primary, other]
            tray_machine.setCurrentIndex(tray_machine.findData(primary))
            prefs.save()
            session.expanded.close()
            assert session.scopes() == [primary] and session.popup.displayed == (LOCAL,)
            menu = session.menus[primary]
            for choice in (ALL, other, LOCAL):
                choose_display(session, choice)
                expected = tuple(session.dashboard.monitored()) if choice == ALL else (choice,)
                with patch("arm.application.tray_icon", wraps=tray_icon) as draw:
                    session.render()
                    assert [call.args[1] for call in draw.call_args_list] == [primary]
                assert session.popup.displayed == session.expanded.displayed == expected
                assert all(menu.machines.entries[machine].isChecked() for machine in expected)
                if choice == ALL:
                    for view in (session.popup, session.expanded):
                        assert set(view.sections) == {LOCAL, primary, other}
                        assert all(set(section.cards) == set(RESOURCES) for section in view.sections.values())
            menu.machines.master.click()
            history = session.collectors.history
            wait_for(lambda: all(
                (reading := history.latest(machine, TOTAL, direction)) and reading.valid and reading.value > 0
                for machine in (primary, other) for direction in NETWORK
            ))
            session.popup.refresh()
            for machine in (primary, other):
                card = session.popup.sections[machine].cards["net"]
                for direction, (points, _) in zip(NETWORK, card.plot.data[0]):
                    latest = history.latest(machine, TOTAL, direction)
                    assert any(stamp == latest.timestamp and value > 0 for stamp, value in points if value is not None)
                    assert card.direction_labels[direction].text().startswith(NETWORK[direction][0] + ":")
            results["independent_network_directions"] = True
            session.popup.interval.setCurrentIndex(session.popup.interval.findData(300))
            session.popup.hide()
            menu.defaultAction().trigger()
            assert session.expanded.displayed == tuple(session.dashboard.monitored())
            session.expanded.close()
            session.hover.show(primary)
            assert session.popup.displayed == tuple(session.dashboard.monitored()) and session.popup.span == 300
            assert session.store.load_display(session.settings).select_new
            saved = ConfigStore(root / "settings.json").load()
            assert (saved.hover_range, saved.tray_machine) == (300, primary)
            session.popup.hide()
            session.apply(replace(session.settings, separate_tray_icons=True, persistent=True))
            assert set(session.icons) == {LOCAL, *(target.identifier for target in targets)}
            verify_hover_version(session, primary, results, captures)
            with patch("arm.application.tray_icon", wraps=tray_icon) as draw:
                session.render()
                assert {call.args[1] for call in draw.call_args_list} == {LOCAL, primary, other}
                assert draw.call_count == 3
            results["independent_tray_and_monitor"] = "Local plus two SSH targets, six graphs each, three independent icon sources"
            results["loopback_frame_counts"] = [server.samples for server in servers]
            for target, name in zip(targets, ("Rain", "Phantom")):
                session.save_target(replace(target, name=name), "", False)
            for name in ("LAMP", "PhantomNet"):
                server = stack.enter_context(Fixture())
                target = Target(name=name, host="127.0.0.1", port=server.port, username="tester", interval=1)
                update_host_key(session.hosts, f"[127.0.0.1]:{server.port}", server.key)
                session.save_target(target, SECRET, False)
                targets.append(target)
            wait_for(lambda: all(session.dashboard.state(machine) == Connection.ONLINE and
                                 session.collectors.history.latest(machine, TOTAL, "ram.util")
                                 for machine in session.dashboard.monitored()), 15)
            verify_machine_display(session, wait_for, results, captures)
            for target in targets[2:]:
                session.remove_target(next(t for t in session.settings.targets if t.identifier == target.identifier))
            targets = targets[:2]
            for target in targets:
                session.collectors.disconnect(target.identifier)
            assert all(session.dashboard.state(t.identifier) == Connection.OFFLINE for t in targets)
            assert session.popup.displayed == tuple(session.dashboard.monitored())
            session.apply(replace(session.settings, separate_tray_icons=False, persistent=False))
            if not short:
                measure("disconnected_remotes")
            assert set(session.icons) == {primary}
            for target in list(session.settings.targets):
                session.remove_target(target)
            assert set(session.icons) == {LOCAL} and session.popup.displayed == (LOCAL,)
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
    restart_root = work / "restart"
    store = ConfigStore(restart_root / "settings.json")
    stored_targets = [replace(target, enabled=False, credential="test-reference") for target in saved.targets]
    store.save(replace(saved, targets=stored_targets, hover_machine=ALL))
    for legacy in (False, True):
        if legacy:
            source = json.loads(store.path.read_text(encoding="utf-8"))
            source.update(hover_machine="@peak", default_machine="@peak")
            store.path.write_text(json.dumps(source), encoding="utf-8")
        startup = replace(store.load(), update_startup=True, update_interval=4)
        if legacy:
            source["update_startup"] = True
            source["update_interval"] = 4
            store.path.write_text(json.dumps(source), encoding="utf-8")
        else:
            store.save(startup)
        from arm.update_client import ReleaseClient
        with patch.object(ReleaseClient, "check", return_value=Check(None, None, ())) as check:
            reopened = Application(app, restart_root)
            try:
                assert reopened.scopes() == [primary]
                assert reopened.popup.displayed == reopened.expanded.displayed == (LOCAL,)
                assert reopened.dashboard.machine_display.selected == (LOCAL, primary, other)
                assert reopened.popup.span == 300 and not reopened.popup.pinned
                assert reopened.settings.targets == stored_targets
                panel = reopened.about_page.updates
                assert panel.periodic.isActive() and panel.periodic.interval() == 4 * 3_600_000
                wait_for(lambda: check.called and panel.job is None)
                assert panel.fields["Latest published"].text() == "No public releases"
            finally:
                reopened.close()
        app.processEvents()
    results["restored_monitor_and_tray"] = "New and legacy settings restored All Systems at five minutes with a separate tray source"
    results["startup_update_and_periodic_timer"] = True
    verify_abrupt_display_restart(work, results)


def verify_abrupt_display_restart(work, results):
    from arm.config import ConfigStore, Settings, Target
    from arm.model import ALL

    root = work / "abrupt-display"
    ConfigStore(root / "settings.json").save(Settings(
        hover_machine=ALL, targets=[Target(identifier="qa-remote", name="QA profile", os_type="Windows")]
    ))
    argv = [sys.executable, str(Path(__file__).resolve()), "--desktop", results["desktop"], "--work", str(root)]
    with subprocess.Popen([*argv, "--abrupt-display", "write"], creationflags=subprocess.CREATE_NO_WINDOW) as instance:
        try:
            deadline = monotonic() + 20
            while not (root / "saved").is_file():
                assert instance.poll() is None and monotonic() < deadline, "Isolated display test did not save"
                sleep(.05)
        finally:
            instance.kill()
            instance.wait(8)
    assert instance.returncode != 0
    result = subprocess.run([*argv, "--abrupt-display", "inspect"], timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0, f"Isolated restart failed with exit {result.returncode}"
    results["forced_termination_restored_display"] = True


def abrupt_display_child(args):
    from PySide6.QtWidgets import QApplication
    from arm.application import Application
    from arm.model import LOCAL

    verify_desktop(args.desktop)
    app = QApplication([])
    assert app.platformName() == "windows"
    session = Application(app, args.work)
    if args.abrupt_display == "write":
        session.reorder_machines(session.popup.displayed, LOCAL, 1, session.popup)
        session.popup.machine.checklist.entries[LOCAL].click()
        assert session.popup.displayed == ("qa-remote",)
        (args.work / "saved").touch()
        app.exec()
        raise RuntimeError("The isolated process was expected to be terminated")
    try:
        assert session.dashboard.machines() == ("qa-remote", LOCAL)
        assert session.popup.displayed == session.expanded.displayed == ("qa-remote",)
    finally:
        session.close()


def child(args):
    result = {"desktop": verify_desktop(args.desktop)}
    try:
        if args.package:
            validate_packages(args.package, args.work, result, args.upgrade_from, args.captures, args.portable_only)
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
        if args.portable_only:
            command.append("--portable-only")
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
    parser.add_argument("--portable-only", action="store_true")
    parser.add_argument("--upgrade-from", type=Path)
    parser.add_argument("--captures", type=Path)
    parser.add_argument("--short", action="store_true")
    parser.add_argument("--abrupt-display", choices=("write", "inspect"))
    args = parser.parse_args()
    if args.abrupt_display:
        abrupt_display_child(args)
        raise SystemExit(0)
    if args.desktop:
        raise SystemExit(child(args))
    raise SystemExit(parent(args))
