from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QRect, QSignalBlocker, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QScrollArea, QSpinBox, QTabWidget, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QHeaderView, QVBoxLayout, QWidget,
)

from .config import TRAY_MODES
from .machine_controls import MachineDrag
from .model import DISK_MODES, LOCAL, NETWORK, RANGES, RESOURCES, Connection
from .views import fill, interval_choices, plain
from .window_geometry import WindowGeometry


def checkbox(value):
    check = QCheckBox()
    check.setChecked(value)
    return check


def combo(values, value):
    control = QComboBox()
    fill(control, values, value)
    return control


def spin(value, low, high, suffix=""):
    control = QSpinBox()
    control.setRange(low, high)
    control.setValue(value)
    control.setSuffix(suffix)
    return control


def scale_spin(value):
    control = QDoubleSpinBox()
    control.setRange(0, 1048576)
    control.setDecimals(2)
    control.setSuffix(" MiB/s")
    control.setSpecialValueText("Automatic")
    control.setValue(value / 2**20)
    return control


def path_control(value, select, parent):
    field = QLineEdit(value)
    browse = QPushButton("Browse…")
    browse.clicked.connect(lambda: pick_path(field, select, parent))
    widget = QWidget()
    row = QHBoxLayout(widget)
    row.setContentsMargins(0, 0, 0, 0)
    row.addWidget(field, 1)
    row.addWidget(browse)
    return widget, field


def pick_path(field, select, parent):
    filename = select(parent, "Choose file", field.text())[0]
    if filename:
        field.setText(filename)


class Choices(QListWidget):
    def __init__(self, values, active):
        super().__init__()
        self.setMaximumHeight(113)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        selected = set(active)
        for label, key in values:
            item = QListWidgetItem(label, self)
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if key in selected else Qt.CheckState.Unchecked)

    def keys(self):
        return [self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())
                if self.item(i).checkState() == Qt.CheckState.Checked]


class DeviceChoices(Choices):
    def __init__(self, devices, kind, selected):
        available = {device.identifier: device.name for device in devices.values() if device.kind == kind}
        available.update((key, key) for key in selected if key not in available)
        super().__init__([(f"{label} ({key})" if label != key else label, key)
                          for key, label in available.items()], selected)
        self.setMaximumHeight(75)
        self.setToolTip("With no checked device, the provider uses its automatic selection.")
        if not available:
            self.setVisible(False)


class SettingsDialog(QDialog):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.cfg = app.settings
        self.setWindowTitle("ARM Settings")
        self.resize(610, 610)
        self.controls = {}
        self.tabs = QTabWidget()
        self.colors = dict(self.cfg.colors)
        self.network_colors = dict(self.cfg.network_colors)
        self.background = self.cfg.background
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.general()
        self.tray()
        self.hover()
        self.monitoring()
        self.remote()
        self.history()
        self.diagnostics()
        self.timer = QTimer(self)
        self.timer.setInterval(1500)
        self.timer.timeout.connect(self.update_diagnostics)
        self.timer.start()
        self.update_diagnostics()
        self.window_geometry = WindowGeometry(self, app.root / "settings-window.bin")

    def section(self, title):
        page = QWidget()
        form = QFormLayout(page)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        self.tabs.addTab(scroll, title)
        return form

    def add(self, form, label, name, widget, read):
        form.addRow(label, widget)
        self.controls[name] = read

    def check(self, form, label, name):
        widget = checkbox(getattr(self.cfg, name))
        self.add(form, label, name, widget, widget.isChecked)

    def select(self, form, label, name, values):
        widget = combo(values, getattr(self.cfg, name))
        self.add(form, label, name, widget, widget.currentData)

    def integer(self, form, label, name, low, high, suffix=""):
        widget = spin(getattr(self.cfg, name), low, high, suffix)
        self.add(form, label, name, widget, widget.value)

    def resource_choices(self, form, label, name):
        widget = Choices([(title, key) for key, (title, _, _) in RESOURCES.items()], getattr(self.cfg, name))
        self.add(form, label, name, widget, widget.keys)

    def general(self):
        form = self.section("General")
        self.startup = checkbox(self.app.startup_enabled())
        form.addRow("Start with Windows", self.startup)
        self.check(form, "Start minimized", "minimized")
        self.select(form, "Theme", "theme", [(value, value) for value in ("System", "Light", "Dark")])
        self.check(form, "Check for updates at startup", "update_startup")
        self.check(form, "Show Windows update notifications", "update_notifications")
        self.select(form, "Check for updates periodically", "update_interval",
                    [("Off", 0), ("Every 4 hours", 4), ("Every 12 hours", 12),
                     ("Daily", 24), ("Weekly", 168)])

    def tray(self):
        form = self.section("Tray Icon")
        self.select(form, "Visualization", "mode", [(v, v) for v in TRAY_MODES])
        self.select(form, "Tray icon machine", "tray_machine",
                    [(self.app.dashboard.name(machine), machine) for machine in self.app.dashboard.machines()])
        self.check(form, "Separate machine icons", "separate_tray_icons")
        self.select(form, "Refresh", "tray_refresh", interval_choices())
        self.select(form, "History range", "tray_range", [(v, k) for k, v in RANGES.items() if k <= 3600])
        self.select(form, "Disk graph", "disk_mode", [(v, k) for k, v in DISK_MODES.items()])
        for label, key in (("Disk throughput scale", "disk_scale"), ("Network throughput scale", "net_scale")):
            widget = scale_spin(getattr(self.cfg, key))
            self.add(form, label, key, widget, lambda widget=widget: widget.value() * 2**20)
        self.resource_choices(form, "Visible resources", "resources")
        self.check(form, "Transparent background", "transparent")
        for key, title, color in [("background", "Background", self.background)] + [
            (key, info[0], self.colors[key]) for key, info in RESOURCES.items() if key != "net"
        ] + [
            (key, f"Network {direction}", self.network_colors[key]) for key, (direction, _) in NETWORK.items()
        ]:
            button = QPushButton(color)
            button.clicked.connect(lambda _, key=key, button=button: self.choose_color(key, button))
            form.addRow(f"{title} color", button)

    def choose_color(self, key, button):
        color = QColorDialog.getColor(QColor(button.text()), self)
        if color.isValid():
            button.setText(color.name())
            if key == "background":
                self.background = color.name()
            elif key in NETWORK:
                self.network_colors[key] = color.name()
            else:
                self.colors[key] = color.name()

    def hover(self):
        form = self.section("Hover Monitor")
        self.integer(form, "Hover delay", "hover_delay", 0, 5000, " ms")
        self.integer(form, "Dismissal delay", "dismiss_delay", 100, 10000, " ms")
        self.integer(form, "Width", "popup_width", 300, 1800, " px")
        self.integer(form, "Height", "popup_height", 210, 1200, " px")
        self.integer(form, "Graph columns", "popup_columns", 1, 3)
        self.select(form, "Default history range", "hover_range",
                    [(v, k) for k, v in RANGES.items() if k <= 3600])
        self.resource_choices(form, "Visible graphs", "hover_resources")

    def monitoring(self):
        form = self.section("Monitoring")
        self.select(form, "Local sampling interval", "local_interval", interval_choices())
        self.select(form, "Default remote sampling interval", "remote_interval", interval_choices())
        devices = self.app.collectors.devices[LOCAL]
        for kind, key, label in (("gpu", "gpus", "GPUs"), ("disk", "disks", "Disks"), ("net", "interfaces", "Interfaces")):
            widget = DeviceChoices(devices, kind, getattr(self.cfg, key))
            self.add(form, label, key, widget, widget.keys)
        note = plain(QLabel("An empty selection uses automatic device selection. When selecting interfaces, choose one layer of each bridge or VPN path."))
        note.setWordWrap(True)
        form.addRow(note)

    def remote(self):
        form = self.section("Remote Connections")
        self.integer(form, "Default connection timeout", "connection_timeout", 2, 30, " s")
        self.check(form, "Retry new targets automatically", "reconnect")
        manage = QPushButton("Manage targets, credentials and SSH host keys")
        manage.clicked.connect(self.app.manage)
        form.addRow(manage)

    def history(self):
        form = self.section("History")
        self.check(form, "Record persistent history", "persistent")
        self.integer(form, "Retention", "retention_days", 1, 365, " days")
        self.integer(form, "Maximum database size", "max_history_mb", 16, 4096, " MiB")
        widget, field = path_control(self.cfg.history_file, QFileDialog.getSaveFileName, self)
        field.setPlaceholderText(str(self.app.root / "history.sqlite"))
        self.add(form, "Database location", "history_file", widget, field.text)
        clear = QPushButton("Clear recorded history…")
        clear.clicked.connect(lambda: self.app.clear_history(self))
        form.addRow(clear)

    def diagnostics(self):
        form = self.section("Diagnostics")
        self.select(form, "Logging level", "log_level", [(v, v) for v in ("DEBUG", "INFO", "WARNING", "ERROR")])
        self.diagnostic = plain()
        self.diagnostic.setWordWrap(True)
        self.diagnostic.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow(self.diagnostic)

    def update_diagnostics(self):
        self.diagnostic.setText(self.app.diagnostics())

    def save(self):
        updates = {key: getter() for key, getter in self.controls.items()}
        cfg = replace(self.app.settings, **updates, background=self.background, colors=self.colors,
                      network_colors=self.network_colors)
        try:
            self.app.apply(cfg)
            if self.startup.isChecked() != self.app.startup_enabled():
                self.app.set_startup(self.startup.isChecked())
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Settings", str(exc))
            return
        self.accept()


class TargetDialog(QDialog):
    def __init__(self, app, target, parent):
        super().__init__(parent)
        self.app, self.target = app, target
        self.setWindowTitle("Remote Machine")
        self.resize(520, 635)
        self.name = QLineEdit(target.name)
        self.host = QLineEdit(target.host)
        self.os = combo([(s, s) for s in ("Linux", "Windows")], target.os_type)
        self.method = plain()
        self.port = spin(target.port, 1, 65535)
        self.username = QLineEdit(target.username)
        self.auth = combo([(s, s) for s in ("Password", "Private key")], target.auth)
        self.secret = QLineEdit()
        self.secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.secret.setPlaceholderText("Saved in Windows Credential Manager" if target.credential else "Enter a secret if required")
        self.remove_secret = checkbox(False)
        key_widget, self.key = path_control(target.key_file, QFileDialog.getOpenFileName, self)
        self.interval = combo(interval_choices(), target.interval)
        self.timeout = spin(target.timeout, 2, 30, " s")
        self.enabled, self.reconnect, self.tray = [checkbox(value) for value in (target.enabled, target.reconnect, target.tray)]
        self.resources = Choices([(title, key) for key, (title, _, _) in RESOURCES.items()], target.resources)
        devices = app.collectors.devices[target.identifier]
        self.ids = {}
        page = QWidget()
        form = QFormLayout(page)
        for title, widget in (
            ("Display name", self.name), ("Host or IP", self.host), ("Operating system", self.os),
            ("Connection", self.method), ("Port", self.port), ("Username", self.username),
            ("Authentication", self.auth), ("Private key", key_widget), ("Password or key passphrase", self.secret),
            ("Remove saved secret", self.remove_secret), ("Sampling interval", self.interval),
            ("Timeout", self.timeout), ("Enable monitoring", self.enabled), ("Reconnect automatically", self.reconnect),
            ("Include in separate tray icons", self.tray), ("Resources", self.resources),
        ):
            form.addRow(title, widget)
        for kind, key, label in (("gpu", "gpus", "GPU identifiers"), ("disk", "disks", "Disk identifiers"),
                                 ("net", "interfaces", "Interface identifiers")):
            choices = DeviceChoices(devices, kind, getattr(target, key))
            manual = QLineEdit(",".join(x for x in getattr(target, key) if x not in devices))
            manual.setPlaceholderText("Additional identifiers, separated by commas")
            form.addRow(label, choices)
            form.addRow("", manual)
            self.ids[key] = (choices, manual)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        layout = QVBoxLayout(self)
        layout.addWidget(scroll)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        def update():
            linux = self.os.currentData() == "Linux"
            self.method.setText("SSH" if linux else "Planned")
            key_widget.setEnabled(linux and self.auth.currentData() == "Private key")
            for widget in (self.username, self.port, self.auth, self.secret, self.remove_secret):
                widget.setEnabled(linux)

        self.os.currentIndexChanged.connect(update)
        self.auth.currentIndexChanged.connect(update)
        update()
        self.window_geometry = WindowGeometry(self, app.root / "remote-machine-window.bin")

    def save(self):
        host, name, user = (field.text().strip() for field in (self.host, self.name, self.username))
        os_type, auth = self.os.currentData(), self.auth.currentData()
        key = self.key.text().strip()
        if not name or not host or any(char.isspace() for char in host) or any(c in host for c in "[],"):
            QMessageBox.warning(self, "Remote Machine", "Enter a display name and a valid hostname or IP address.")
            return
        if os_type == "Linux" and (not user or (auth == "Private key" and not Path(key).is_file())):
            QMessageBox.warning(self, "Remote Machine", "Enter an SSH username and choose an existing key file if using key authentication.")
            return
        filters = {k: list(dict.fromkeys(choices.keys() + [v.strip() for v in line.text().split(",") if v.strip()]))
                   for k, (choices, line) in self.ids.items()}
        target = replace(self.target, name=name, host=host, username=user, os_type=os_type,
                         method="SSH" if os_type == "Linux" else "Planned", port=self.port.value(),
                         auth=auth, key_file=key, interval=self.interval.currentData(),
                         timeout=self.timeout.value(), enabled=self.enabled.isChecked(),
                         reconnect=self.reconnect.isChecked(), tray=self.tray.isChecked(),
                         resources=self.resources.keys(), **filters)
        identity = ("host", "username", "auth", "port", "os_type")
        forget = self.remove_secret.isChecked() or any(
            getattr(self.target, k) != getattr(target, k) for k in identity)
        try:
            self.app.save_target(target, self.secret.text() if os_type == "Linux" else "", forget)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Remote Machine", str(exc))
            return
        self.secret.clear()
        self.accept()


class ConnectionsDialog(QDialog):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setWindowTitle("Remote Targets")
        self.resize(730, 385)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(("Machine", "Host", "Connection", "Status"))
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.cellDoubleClicked.connect(lambda *_: self.edit())
        self.info = plain()
        self.info.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addWidget(self.info)
        for actions in (
            (("Add", self.add), ("Edit", self.edit), ("Remove", self.remove), ("Test connection", self.test),
             ("Connect", self.connect_target), ("Disconnect", self.disconnect), ("Enable / disable", self.toggle)),
            (("Approve SSH host key", self.approve), ("Forget SSH host key…", self.forget)),
        ):
            row = QHBoxLayout()
            for title, action in actions:
                button = QPushButton(title)
                button.clicked.connect(action)
                row.addWidget(button)
            row.addStretch()
            layout.addLayout(row)
        self.test_results = {}
        self.identifiers = ()
        self.drag = MachineDrag(self.table, self.row_rects, self.reorder)
        self.drag.watch(self.table.viewport(), self.machine_at)
        self.table.itemSelectionChanged.connect(self.status_text)
        app.collectors.changed.connect(self.sync)
        app.display_changed.connect(self.sync)
        app.collectors.test_finished.connect(self.test_finished)
        self.sync()
        self.window_geometry = WindowGeometry(self, app.root / "remote-targets-window.bin")

    def selected(self):
        row = self.table.currentRow()
        item = self.table.item(row, 0)
        identifier = item.data(Qt.ItemDataRole.UserRole) if item else None
        return next((target for target in self.app.settings.targets if target.identifier == identifier), None)

    def machine_at(self, point):
        row = self.table.rowAt(point.y())
        return self.identifiers[row] if 0 <= row < len(self.identifiers) else None

    def row_rects(self):
        return [(machine, QRect(0, self.table.rowViewportPosition(row), self.table.viewport().width(),
                                self.table.rowHeight(row))) for row, machine in enumerate(self.identifiers)]

    def reorder(self, source, index):
        self.app.reorder_machines(self.identifiers, source, index, self)

    def sync(self):
        prior = self.selected()
        targets = {target.identifier: target for target in self.app.settings.targets}
        self.identifiers = tuple(machine for machine in self.app.dashboard.machines() if machine in targets)
        with QSignalBlocker(self.table):
            self.table.setRowCount(len(self.identifiers))
            for row, machine in enumerate(self.identifiers):
                target = targets[machine]
                state = self.app.dashboard.state(machine)
                for column, value in enumerate((target.name, f"{target.host}:{target.port}", target.method, state.value)):
                    item = self.table.item(row, column)
                    if item is None:
                        item = QTableWidgetItem()
                        self.table.setItem(row, column, item)
                    item.setText(value)
                    if column == 0:
                        item.setData(Qt.ItemDataRole.UserRole, machine)
            if self.identifiers:
                selected = prior.identifier if prior else None
                self.table.selectRow(self.identifiers.index(selected) if selected in self.identifiers else 0)
        self.status_text()

    def status_text(self):
        target = self.selected()
        if not target:
            self.info.clear()
            return
        status = self.app.collectors.statuses.get(target.identifier)
        test = self.test_results.get(target.identifier, "")
        self.info.setText(" · ".join(v for v in (status.detail if status else "", test) if v))

    def add(self):
        self.app.add_target(self)

    def edit(self):
        if target := self.selected():
            self.test_results.pop(target.identifier, None)
            TargetDialog(self.app, target, self).exec()

    def remove(self):
        if target := self.selected():
            if QMessageBox.question(self, "Remove Machine", f"Remove profile {target.name} and its saved credential?",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                    QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
                try:
                    self.test_results.pop(target.identifier, None)
                    self.app.remove_target(target)
                except OSError as exc:
                    QMessageBox.warning(self, "Remove Machine", str(exc))

    def test(self):
        if target := self.selected():
            self.test_results[target.identifier] = "Testing SSH telemetry…"
            self.status_text()
            self.app.collectors.test(target)

    def test_finished(self, status):
        self.test_results[status.machine] = f"Test: {status.state} {status.detail}"
        if status.trust:
            self.app.test_keys[status.machine] = status.trust
        self.status_text()

    def connect_target(self):
        if target := self.selected():
            if not target.enabled:
                self.app.save_target(replace(target, enabled=True), "", False)
            self.app.collectors.reconnect(target.identifier)

    def disconnect(self):
        if target := self.selected():
            self.app.collectors.disconnect(target.identifier)

    def toggle(self):
        if target := self.selected():
            self.app.save_target(replace(target, enabled=not target.enabled), "", False)
            if not target.enabled:
                self.app.collectors.reconnect(target.identifier)

    def approve(self):
        if target := self.selected():
            self.app.approve_key(target, self)

    def forget(self):
        if target := self.selected():
            self.app.forget_key(target, self)
