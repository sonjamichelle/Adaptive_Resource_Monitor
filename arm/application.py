from dataclasses import replace
from functools import partial
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import subprocess
import sys
from threading import Thread
from time import time
import winreg

import psutil
from PySide6.QtCore import QLockFile, QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QSystemTrayIcon

from .about import AboutPage
from .branding import DARK, LIGHT, PUBLISHER, WEBSITE, application_icon, set_windows_identity
from .collect import Collectors
from .config import STATIC_TRAY_MODE, ConfigStore, Target, data_path
from .credentials import CredentialStore
from .dialogs import ConnectionsDialog, SettingsDialog, TargetDialog
from .graphs import Dashboard, tray_icon
from .history_db import HistoryDb
from .model import ALL, LOCAL, TOTAL, Connection
from .providers.ssh import update_host_key
from .tray import HoverMonitor
from .tray_menu import TrayMenu
from .version import NAME, VERSION
from .views import METRIC_NAMES, Monitor

LOG = logging.getLogger(__name__)
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "AdaptiveResourceMonitor"


def setup_logging(root, level):
    root.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(root / "arm.log", maxBytes=1024 * 1024, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)
    # The application logs SSH transitions with predictable, credential-free messages.
    logging.getLogger("paramiko").setLevel(logging.CRITICAL + 1)
    sys.excepthook = lambda kind, value, trace: LOG.error("Unhandled exception", exc_info=(kind, value, trace))
    return handler


class Application(QObject):
    archived = Signal(object, object)
    history_error = Signal(str)
    process_info = Signal(str)

    def __init__(self, qt, root):
        super().__init__()
        self.qt, self.root = qt, Path(root)
        self.brand_icon = application_icon()
        self.qt.setWindowIcon(self.brand_icon)
        self.store = ConfigStore(self.root / "settings.json")
        self.settings = self.store.load()
        self.logger = setup_logging(self.root, self.settings.log_level)
        LOG.info("%s %s starting", NAME, VERSION)
        self.credentials = CredentialStore()
        self.hosts = self.root / "known_hosts"
        self.storage = None
        self.retired_storage = []
        self.storage_signature = None
        self.archive_token = 0
        self.archive_signature = None
        self.history_message = ""
        self.process_message = ""
        self.diagnostic_thread = None
        self.test_keys = {}
        self.archived.connect(self.accept_archive)
        self.history_error.connect(self.report_history_error)
        self.process_info.connect(self.accept_process_info)
        self.collectors = Collectors(self.settings, self.credentials, self.hosts)
        self.dashboard = Dashboard(self.collectors)
        self.collectors.changed.connect(self.sync_status)
        self.icons = {}
        self.menus = {}
        self.monitor_machines = {}
        self.about_page = AboutPage(self.root)
        self.expanded = Monitor(self.dashboard, True, self.request_archive, self.open_expanded,
                                self.set_pin, self.about_page)
        self.expanded.setWindowIcon(self.brand_icon)
        self.popup = Monitor(self.dashboard, False, self.request_archive, self.open_expanded, self.set_pin)
        self.hover = HoverMonitor(self.popup, self.dashboard, self.icons, self.tray_machine)
        self.tray_timer = QTimer(self)
        self.tray_timer.timeout.connect(self.render)
        self.hover_timer = QTimer(self)
        self.hover_timer.setInterval(80)
        self.hover_timer.timeout.connect(self.hover.tick)
        self.hover_timer.start()
        self.view_timer = QTimer(self)
        self.view_timer.setInterval(500)
        self.view_timer.timeout.connect(self.refresh_views)
        self.view_timer.start()
        self.manager = None
        self.settings_dialog = None
        self._closed = False
        self.qt.styleHints().colorSchemeChanged.connect(self.change_brand_theme)
        self.change_brand_theme()
        self.configure()

    def change_brand_theme(self, scheme=None):
        scheme = scheme or self.qt.styleHints().colorScheme()
        self.brand_colors = DARK if scheme == Qt.ColorScheme.Dark else LIGHT
        self.about_page.theme(self.brand_colors)
        self.expanded.brand_tabs(self.brand_colors)
        for menu in self.menus.values():
            menu.theme(self.brand_colors)

    def configure(self):
        settings = self.settings
        scheme = {"Light": Qt.ColorScheme.Light, "Dark": Qt.ColorScheme.Dark, "System": Qt.ColorScheme.Unknown}
        self.qt.styleHints().setColorScheme(scheme[settings.theme])
        logging.getLogger().setLevel(settings.log_level)
        self.configure_history()
        self.collectors.apply(settings)
        self.tray_timer.start(round(1000 * settings.tray_refresh))
        self.sync_icons()
        self.popup.sync()
        self.expanded.sync()
        self.render()

    def configure_history(self):
        cfg = self.settings
        path = Path(cfg.history_file).expanduser() if cfg.history_file else self.root / "history.sqlite"
        signature = (path, cfg.retention_days, cfg.max_history_mb) if cfg.persistent else None
        if signature == self.storage_signature:
            return
        previous = self.storage
        if previous:
            previous.stop()
            self.retired_storage.append(previous)
        self.storage_signature = signature
        predecessor = previous or next((db for db in reversed(self.retired_storage) if db.thread.is_alive()), None)
        self.storage = (HistoryDb(*signature, self.archived.emit, self.history_error.emit, previous=predecessor)
                        if signature else None)
        self.collectors.storage = self.storage
        self.archive_token += 1
        self.archive_signature = None
        self.history_message = ""
        self.dashboard.archived.clear()
        self.retired_storage = [db for db in self.retired_storage if db.thread.is_alive()]

    def apply(self, settings):
        self.store.save(settings)
        old_default = self.settings.default_machine
        old_hover = self.settings.hover_range
        self.settings = settings
        self.configure()
        if old_default != settings.default_machine:
            self.popup.set_machine(settings.default_machine)
            self.expanded.set_machine(settings.default_machine)
        if old_hover != settings.hover_range:
            self.popup.interval.setCurrentIndex(self.popup.interval.findData(settings.hover_range))
        self.expanded.archive()
        LOG.info("Settings updated")

    def sync_status(self):
        self.popup.sync()
        self.expanded.sync()
        self.sync_menus()
        self.refresh_views()

    def scopes(self):
        cfg = self.settings
        if cfg.tray_mode == "Consolidated":
            return [ALL]
        if cfg.tray_mode == "Selected remote":
            return [cfg.tray_remote] if any(t.identifier == cfg.tray_remote for t in cfg.targets) else [LOCAL]
        return [LOCAL] + ([t.identifier for t in cfg.targets if t.tray] if cfg.tray_mode == "Separate" else [])

    def sync_icons(self):
        scopes = self.scopes()
        for machine in list(self.icons):
            if machine not in scopes:
                icon = self.icons.pop(machine)
                icon.hide()
                icon.setContextMenu(None)
                icon.deleteLater()
                self.menus.pop(machine).deleteLater()
                self.monitor_machines.pop(machine, None)
        for machine in scopes:
            if machine in self.icons:
                continue
            icon = QSystemTrayIcon(self)
            icon.setIcon(self.brand_icon)
            icon.activated.connect(partial(self.activate_icon, machine))
            self.icons[machine] = icon
            self.menus[machine] = TrayMenu(self, machine)
            self.menus[machine].theme(self.brand_colors)
            icon.setContextMenu(self.menus[machine])
            icon.show()
        self.sync_menus()

    def sync_menus(self):
        for menu in self.menus.values():
            if not menu.isVisible():
                menu.refresh()

    def tray_machine(self, scope):
        choices = {ALL, *self.dashboard.machines()}
        chosen = self.monitor_machines.get(scope, scope)
        return chosen if chosen in choices else scope if scope in choices else LOCAL

    def select_machine(self, machine, scope):
        self.monitor_machines[scope] = machine
        self.expanded.set_machine(machine)
        self.hover.show(scope)
        self.render()
        self.sync_menus()

    def set_tray_display(self, mode):
        if mode == self.settings.mode:
            return
        try:
            self.apply(replace(self.settings, mode=mode))
        except (OSError, ValueError) as exc:
            self.sync_menus()
            QMessageBox.warning(self.expanded, "Tray Display", str(exc))

    def activate_icon(self, machine, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_pin(machine)
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.open_expanded(self.tray_machine(machine))

    def toggle_pin(self, machine):
        self.hover.pin(not self.popup.pinned or self.hover.anchor != machine, machine)
        self.sync_menus()

    def set_pin(self, enabled):
        self.hover.pin(enabled)
        self.sync_menus()

    def render(self):
        now = time()
        for machine, icon in self.icons.items():
            scope = self.tray_machine(machine)
            members = self.dashboard.machines() if scope == ALL else (scope,)
            initializing = all(self.dashboard.state(member) == Connection.CONNECTING
                               and member not in self.collectors.last for member in members)
            if self.settings.mode == STATIC_TRAY_MODE or initializing:
                image = self.brand_icon
            else:
                image = tray_icon(self.dashboard, scope, now)
            if icon.icon().cacheKey() != image.cacheKey():
                icon.setIcon(image)

    def refresh_views(self):
        for view in (self.popup, self.expanded):
            if view.monitor_visible:
                view.refresh()

    def open_expanded(self, machine=None, history=False):
        if machine in self.dashboard.machines() or machine == ALL:
            self.expanded.set_machine(machine)
        if history:
            index = self.expanded.interval.findData(3600)
            self.expanded.interval.setCurrentIndex(max(0, index))
        self.expanded.show_page()
        self.expanded.refresh()
        self.expanded.archive()

    def request_archive(self, scope, span, selection):
        if not self.storage:
            return
        kind, device = selection
        signature = (scope, span, selection)
        if signature == self.archive_signature:
            return
        self.archive_signature = signature
        self.archive_token += 1
        machines = self.dashboard.machines() if scope == ALL else [scope]
        keys = {(machine, device, metric) for machine in machines for metric in METRIC_NAMES}
        if kind:
            keys.update((machine, TOTAL, metric) for machine in machines for metric in METRIC_NAMES)
        self.storage.request(self.archive_token, sorted(keys), time() - span)

    def accept_archive(self, token, results):
        if token != self.archive_token:
            return
        self.dashboard.archived = results
        if self.expanded.isVisible():
            self.expanded.refresh()

    def report_history_error(self, message):
        self.history_message = message
        self.archive_signature = None

    def clear_history(self, parent):
        if not self.storage:
            QMessageBox.information(parent, "Resource History", "Enable recording to access and clear the selected database.")
            return
        if QMessageBox.question(parent, "Clear Resource History", "Delete all readings in the selected history database?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.archive_token += 1
            self.archive_signature = None
            self.storage.send("clear", self.archive_token)

    def diagnostics(self):
        if self.diagnostic_thread is None or not self.diagnostic_thread.is_alive():
            self.diagnostic_thread = Thread(target=self.sample_process, name="ARM diagnostics", daemon=True)
            self.diagnostic_thread.start()
        lines = [f"{NAME} {VERSION}", f"Log file {self.root / 'arm.log'}", self.process_message]
        for key, status in self.collectors.provider_status.items():
            duration = self.collectors.timings.get(key)
            timing = f" · {1000 * duration:.1f} ms" if duration is not None else ""
            lines.append(f"{self.dashboard.name(key[0])} · {key[1]} · {status.state}{timing}")
        lines.extend(f"{target.name} · {self.dashboard.state(target.identifier)}"
                     for target in self.settings.targets)
        if self.history_message:
            lines.append(self.history_message)
        return "\n".join(lines)

    def sample_process(self):
        from time import monotonic
        try:
            proc = psutil.Process()
            values = proc.cpu_times()
            now = monotonic()
            total = values.user + values.system
            previous = getattr(self, "_last_cpu", (0, now))
            self._last_cpu = total, now
            percent = (total - previous[0]) / (now - previous[1]) * 100 if now > previous[1] else 0
            self.process_info.emit(f"ARM CPU {percent:.2f}% of one logical processor · RSS {proc.memory_info().rss / 2**20:.1f} MiB")
        except (OSError, psutil.Error) as exc:
            self.process_info.emit(f"Application resource usage unavailable ({type(exc).__name__})")

    def accept_process_info(self, message):
        self.process_message = message

    def open_settings(self):
        if self.settings_dialog:
            self.settings_dialog.raise_()
            return
        dialog = SettingsDialog(self)
        self.settings_dialog = dialog
        try:
            dialog.exec()
        finally:
            self.settings_dialog = None
            dialog.deleteLater()

    def manage(self):
        if self.manager:
            self.manager.raise_()
            return
        dialog = ConnectionsDialog(self)
        self.manager = dialog
        try:
            dialog.exec()
        finally:
            self.manager = None
            dialog.deleteLater()

    def add_target(self, parent=None):
        new = Target(interval=self.settings.remote_interval, timeout=self.settings.connection_timeout,
                     reconnect=self.settings.reconnect, enabled=False)
        TargetDialog(self, new, parent if isinstance(parent, QDialog) else None).exec()

    def save_target(self, target, secret, forget):
        old = next((t for t in self.settings.targets if t.identifier == target.identifier), None)
        previous = old.credential if old else ""
        reference = self.credentials.save(target.username, secret) if secret else ("" if forget else previous)
        target = replace(target, credential=reference)
        others = [target if t.identifier == target.identifier else t for t in self.settings.targets]
        if old is None:
            others.append(target)
        try:
            self.apply(replace(self.settings, targets=others))
        except (OSError, ValueError):
            if secret:
                self.credentials.delete(reference)
            raise
        if previous and previous != reference and all(t.credential != previous for t in others):
            self.remove_secret(previous)
        self.test_keys.pop(target.identifier, None)

    def remove_target(self, target):
        self.collectors.cancel_test(target.identifier)
        others = [t for t in self.settings.targets if t.identifier != target.identifier]
        self.apply(replace(self.settings, targets=others,
                           default_machine=LOCAL if self.settings.default_machine == target.identifier else self.settings.default_machine))
        if all(t.credential != target.credential for t in others):
            self.remove_secret(target.credential)
        self.test_keys.pop(target.identifier, None)

    def remove_secret(self, reference):
        try:
            self.credentials.delete(reference)
        except (ValueError, OSError) as exc:
            LOG.warning("Could not delete ARM credential (%s)", type(exc).__name__)

    def approve_key(self, target, parent):
        status = self.collectors.statuses.get(target.identifier)
        trust = (status.trust if status else None) or self.test_keys.get(target.identifier)
        label = target.host if target.port == 22 else f"[{target.host}]:{target.port}"
        if not trust or trust.label != label:
            QMessageBox.information(parent, "SSH Host Key", "Test the connection to request a host key.")
            return
        result = QMessageBox.question(
            parent, "Verify SSH Host Key",
            f"SSH host {label}\n{trust.key.get_name()}\n{trust.fingerprint}\n\n"
            "Compare the fingerprint with one obtained directly from the server or its administrator. Does it match?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if result == QMessageBox.StandardButton.Yes:
            try:
                update_host_key(self.hosts, label, trust.key)
            except (ValueError, OSError) as exc:
                QMessageBox.warning(parent, "SSH Host Key", str(exc))
                return
            self.test_keys.pop(target.identifier, None)
            if target.enabled:
                self.collectors.reconnect(target.identifier)
            else:
                self.collectors.test(target)

    def forget_key(self, target, parent):
        label = target.host if target.port == 22 else f"[{target.host}]:{target.port}"
        if QMessageBox.question(parent, "Forget SSH Host Key", f"Remove SSH trust for {label}?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            try:
                update_host_key(self.hosts, label)
            except (OSError, ValueError) as exc:
                QMessageBox.warning(parent, "SSH Host Key", str(exc))
                return
            self.test_keys.pop(target.identifier, None)
            self.collectors.disconnect(target.identifier)

    def startup_enabled(self):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                return bool(winreg.QueryValueEx(key, RUN_VALUE)[0])
        except FileNotFoundError:
            return False

    def set_startup(self, enabled):
        argv = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, str(Path(sys.argv[0]).resolve())]
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            if enabled:
                winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, subprocess.list2cmdline(argv))
            else:
                try:
                    winreg.DeleteValue(key, RUN_VALUE)
                except FileNotFoundError:
                    pass
        self.sync_menus()

    def toggle_startup(self):
        try:
            self.set_startup(not self.startup_enabled())
        except OSError as exc:
            QMessageBox.warning(self.expanded, "Start with Windows", str(exc))

    def about(self):
        self.expanded.show_page(about=True)

    def open_website(self):
        QDesktopServices.openUrl(QUrl(WEBSITE))

    def close(self):
        if self._closed:
            return
        self._closed = True
        for timer in (self.tray_timer, self.hover_timer, self.view_timer):
            timer.stop()
        for icon in self.icons.values():
            icon.hide()
        self.popup.hide()
        self.expanded.hide()
        self.collectors.close()
        if self.storage:
            self.storage.close()
        for database in self.retired_storage:
            database.close()
        LOG.info("%s stopped", NAME)
        logging.getLogger().removeHandler(self.logger)
        self.logger.close()


def main():
    set_windows_identity()
    app = QApplication(sys.argv)
    app.setApplicationName(NAME)
    app.setApplicationVersion(VERSION)
    app.setOrganizationName(PUBLISHER)
    app.setOrganizationDomain(QUrl(WEBSITE).host())
    app.setQuitOnLastWindowClosed(False)
    root = data_path()
    root.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(root / "active.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        return 0
    controller = None
    try:
        controller = Application(app, root)
        if not controller.settings.minimized:
            controller.open_expanded(controller.settings.default_machine)
        return app.exec()
    finally:
        if controller is not None:
            controller.close()
        lock.unlock()
