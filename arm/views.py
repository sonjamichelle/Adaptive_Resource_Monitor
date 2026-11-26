from time import time, strftime, localtime

from PySide6.QtCore import QSize, Qt, QSignalBlocker, QTimer
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QGridLayout, QHeaderView, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QSizePolicy, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from .graphs import Plot, resource_series, selected_resource
from .model import ALL, LOCAL, NETWORK, TOTAL, Connection, INTERVALS, RANGES, RESOURCES, format_value

METRIC_NAMES = {
    "cpu.util": "CPU utilization", "cpu.frequency": "Frequency", "cpu.temperature": "CPU temperature",
    "cpu.power": "CPU power", "cpu.physical": "Physical cores", "cpu.logical": "Logical processors",
    "ram.util": "Physical RAM utilization", "ram.total": "Physical RAM capacity", "ram.used": "Physical RAM used",
    "ram.available": "Physical RAM available", "ram.committed": "Committed memory",
    "ram.commit_limit": "Commit limit", "ram.pagefile_used": "Pagefile / swap used",
    "ram.pagefile_total": "Pagefile / swap capacity", "gpu.util": "GPU utilization",
    "gpu.vram_pct": "Dedicated VRAM utilization", "gpu.vram_used": "Dedicated VRAM used",
    "gpu.vram_total": "Dedicated VRAM capacity", "gpu.vram_free": "Dedicated VRAM free",
    "gpu.shared_used": "Shared GPU memory used", "gpu.shared_total": "Shared GPU memory limit",
    "gpu.shared_pct": "Shared GPU memory utilization", "gpu.temperature": "GPU temperature",
    "gpu.clock": "GPU clock", "gpu.memory_clock": "Memory clock", "gpu.power": "GPU power",
    "gpu.power_limit": "Power limit", "gpu.fan": "Fan speed", "gpu.encode": "Video encode",
    "gpu.decode": "Video decode", "gpu.compute": "Compute engine", "disk.active": "Disk active time",
    "disk.total": "Disk combined", "disk.read": "Disk read", "disk.write": "Disk write",
    "disk.read_ops": "Read operations", "disk.write_ops": "Write operations",
    "net.total": "Network combined", "net.receive": "Network receive", "net.transmit": "Network transmit",
    "net.up": "Link status", "net.link": "Negotiated link speed", "net.util": "Peak link utilization",
}


def fill(combo, values, selected=None):
    with QSignalBlocker(combo):
        combo.clear()
        for label, value in values:
            combo.addItem(label, value)
        index = combo.findData(selected)
        combo.setCurrentIndex(max(index, 0))


def machine_choices(dashboard):
    return [(dashboard.name(machine), machine) for machine in (*dashboard.machines(), ALL)]


def interval_choices():
    return [(f"{value:g} s", value) for value in INTERVALS]


def set_label(label, value):
    if label.text() != value:
        label.setText(value)


def heading(label):
    label.setStyleSheet("font-weight: 600")
    label.setTextFormat(Qt.TextFormat.PlainText)
    return label


def plain(label=None):
    label = label or QLabel()
    label.setTextFormat(Qt.TextFormat.PlainText)
    return label


def display_value(item):
    if not item:
        return "Unavailable"
    if item.value is None:
        return item.availability.value.capitalize()
    description = format_value(item.value, item.unit)
    return description if item.valid else f"{description} · {item.availability}"


class Card(QFrame):
    def __init__(self, resource, detailed, compact=False):
        super().__init__()
        self.title = heading(QLabel(RESOURCES[resource][0]))
        self.value = plain()
        self.plot = Plot()
        self.plot.setAccessibleName(f"{RESOURCES[resource][0]} history")
        self.footer = plain()
        self.footer.setWordWrap(True)
        layout = QVBoxLayout(self)
        margins = (5, 1, 5, 2) if compact else (6, 3, 6, 4)
        layout.setContentsMargins(*margins)
        layout.setSpacing(1 if compact else 3)
        row = QHBoxLayout()
        row.addWidget(self.title, 0)
        row.addStretch()
        self.direction_labels = {}
        if resource == "net":
            layout.addLayout(row)
            self.direction_labels = {metric: plain() for metric in NETWORK}
            for label in self.direction_labels.values():
                layout.addWidget(label)
        elif compact:
            layout.addLayout(row)
            layout.addWidget(self.value)
        else:
            row.addWidget(self.value)
            layout.addLayout(row)
        layout.addWidget(self.plot, 1)
        layout.addWidget(self.footer)
        self.footer.setVisible(detailed and not compact)
        if compact:
            self.setMinimumWidth(124)
            self.plot.setFixedHeight(34 if detailed else 30)


def measurements_table():
    table = QTableWidget(0, 6)
    table.setHorizontalHeaderLabels(("Metric", "Current", "Minimum", "Maximum", "Average", "Machine / device"))
    table.verticalHeader().setVisible(False)
    table.setAlternatingRowColors(True)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    return table


class MachineSection(QFrame):
    def __init__(self, expanded, refresh):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.title = heading(plain())
        self.title.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 4, 5, 4)
        layout.setSpacing(2)
        header = QHBoxLayout()
        header.addWidget(self.title, 1)
        layout.addLayout(header)
        self.cards = {kind: Card(kind, detailed=expanded, compact=True) for kind in RESOURCES}
        grid = QGridLayout()
        grid.setSpacing(3)
        for column, card in enumerate(self.cards.values()):
            grid.addWidget(card, 0, column)
            grid.setColumnStretch(column, 1)
        layout.addLayout(grid)
        self.table = measurements_table() if expanded else None
        if self.table is not None:
            self.table.setFixedHeight(185)
            layout.addWidget(self.table)
            self.table.hide()
            details = QPushButton("Measurements")
            details.setCheckable(True)
            details.toggled.connect(self.table.setVisible)
            details.toggled.connect(refresh)
            header.addWidget(details)


class Monitor(QWidget):
    def __init__(self, dashboard, expanded, request_archive, switch_expanded, set_pin, about_page=None):
        flags = Qt.WindowType.Window if expanded else (
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        super().__init__(None, flags)
        self.dashboard, self.expanded = dashboard, expanded
        self.request_archive = request_archive
        self.setWindowTitle("Adaptive Resource Monitor" if expanded else "ARM Monitor")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        if not expanded:
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            self.setObjectName("hoverMonitor")
        self.pinned = False
        self.machine = QComboBox()
        self.machine.setAccessibleName("Machine")
        self.interval = QComboBox()
        self.interval.setAccessibleName("History range")
        self.device = QComboBox()
        self.device.setAccessibleName("Hardware device")
        self.header = plain()
        self.header.setWordWrap(True)
        top = QHBoxLayout()
        for control in (self.machine, self.interval):
            top.addWidget(control)
        if expanded:
            top.addWidget(self.device, 1)
        else:
            pin = QPushButton("Pin")
            pin.setCheckable(True)
            pin.toggled.connect(set_pin)
            self.pin = pin
            details = QPushButton("Details")
            details.clicked.connect(lambda: switch_expanded(self.machine.currentData()))
            top.addWidget(pin)
            top.addWidget(details)
        self.cards = {kind: Card(kind, expanded) for kind in RESOURCES}
        self.grid = QGridLayout()
        self.grid.setSpacing(5)
        if expanded:
            self.tabs = QTabWidget()
            self.tabs.setObjectName("armMainTabs")
            self.resource_page = QWidget()
            self.about_page = about_page
            self.tabs.addTab(self.resource_page, "Resource Monitor")
            self.tabs.addTab(self.about_page, "About")
            frame = QVBoxLayout(self)
            frame.setContentsMargins(4, 4, 4, 4)
            frame.addWidget(self.tabs)
        layout = QVBoxLayout(self.resource_page if expanded else self)
        layout.setContentsMargins(8, 7, 8, 7)
        layout.setSpacing(4)
        layout.addLayout(top)
        layout.addWidget(self.header)
        self.single = QWidget()
        single_layout = QVBoxLayout(self.single)
        single_layout.setContentsMargins(0, 0, 0, 0)
        single_layout.addLayout(self.grid, 3)
        layout.addWidget(self.single, 1)
        self.simultaneous = QScrollArea()
        self.simultaneous.setWidgetResizable(True)
        self.simultaneous.setAccessibleName("Individual machine histories")
        groups = QWidget()
        self.group_rows = QVBoxLayout(groups)
        self.group_rows.setContentsMargins(1, 1, 1, 1)
        self.group_rows.setSpacing(4)
        self.group_rows.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.simultaneous.setWidget(groups)
        layout.addWidget(self.simultaneous, 1)
        self.sections = {}
        if expanded:
            self.table = measurements_table()
            single_layout.addWidget(self.table, 2)
            self.resize(900, 690)
            self.machine.currentIndexChanged.connect(self.sync_devices)
            self.device.currentIndexChanged.connect(self.selection_changed)
        self.machine.currentIndexChanged.connect(self.selection_changed)
        self.interval.currentIndexChanged.connect(self.selection_changed)
        self.archive_due = QTimer(self)
        self.archive_due.setSingleShot(True)
        self.archive_due.setInterval(350)
        self.archive_due.timeout.connect(self.archive)
        if expanded:
            self.tabs.currentChanged.connect(self.selection_changed)
        self.setStyleSheet("QWidget#hoverMonitor { border: 1px solid palette(mid); }")
        self.sync()

    @property
    def monitor_visible(self):
        return self.isVisible() and (not self.expanded or self.tabs.currentWidget() is self.resource_page)

    def show_page(self, about=False):
        self.tabs.setCurrentWidget(self.about_page if about else self.resource_page)
        self.show()
        self.raise_()
        self.activateWindow()

    def brand_tabs(self, colors):
        self.tabs.setStyleSheet(f"""
            QTabWidget#armMainTabs::pane {{ border: 1px solid {colors.border}; }}
            QTabWidget#armMainTabs QTabBar::tab {{
                padding: 5px 12px; background: {colors.panel}; color: {colors.text};
                border: 1px solid {colors.border}; border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
            QTabWidget#armMainTabs QTabBar::tab:selected {{
                color: {colors.accent}; background: {colors.highlight};
            }}
        """)

    @property
    def selected_machine(self):
        return self.machine.currentData() or LOCAL

    @property
    def selection(self):
        return self.device.currentData() or ("", TOTAL)

    @property
    def span(self):
        return self.interval.currentData() or 60

    def popup_size(self):
        cfg = self.dashboard.settings
        if self.selected_machine != ALL:
            return QSize(cfg.popup_width, cfg.popup_height)
        # Cap in HoverMonitor against the work area. The scroll area keeps
        # six columns together even on a narrow monitor.
        rows_height = sum(max(138, section.sizeHint().height()) for section in self.sections.values())
        return QSize(max(cfg.popup_width, 875), max(cfg.popup_height, rows_height + 72))

    def sync_devices(self):
        if not self.expanded:
            return
        machine = self.selected_machine
        self.device.setVisible(machine != ALL)
        devices = self.dashboard.collectors.devices.get(machine, {})
        kinds = {"cpu": "CPU", "gpu": "GPU", "disk": "Disk", "net": "Network"}
        values = [("Selected devices · aggregate", ("", TOTAL))] + [
            (f"{kinds[device.kind]} · {device.name}", (device.kind, device.identifier))
            for device in devices.values() if device.kind in kinds
        ]
        if self.device.count() != len(values) or any(
                self.device.itemData(i) != data for i, (_, data) in enumerate(values)):
            fill(self.device, values, self.device.currentData())

    def sync(self):
        settings = self.dashboard.settings
        fill(self.machine, machine_choices(self.dashboard),
             self.machine.currentData() or settings.hover_machine or settings.default_machine)
        ranges = [(label, span) for span, label in RANGES.items()
                  if span <= 3600 or (self.expanded and settings.persistent and span <= settings.retention_days * 86400)]
        fill(self.interval, ranges, (self.interval.currentData() or 60) if self.expanded else settings.hover_range)
        self.sync_devices()
        columns = 2 if self.expanded else settings.popup_columns
        kinds = tuple(self.cards) if self.expanded else tuple(
            kind for kind in self.cards if kind in settings.hover_resources)
        for resource, card in self.cards.items():
            self.grid.removeWidget(card)
            card.setVisible(resource in kinds)
        for index, kind in enumerate(kinds):
            self.grid.addWidget(self.cards[kind], index // columns, index % columns)
        self.sync_sections()

    def set_machine(self, machine):
        index = self.machine.findData(machine)
        if index >= 0:
            with QSignalBlocker(self.machine):
                self.machine.setCurrentIndex(index)
        self.sync_devices()
        self.sync_sections()
        if self.monitor_visible:
            self.selection_changed()

    def sync_sections(self):
        both = self.selected_machine == ALL
        self.single.setVisible(not both)
        self.simultaneous.setVisible(both)
        if not both:
            return
        machines = self.dashboard.monitored()
        for machine in self.sections.keys() - set(machines):
            section = self.sections.pop(machine)
            self.group_rows.removeWidget(section)
            section.hide()
            section.deleteLater()
        for index, machine in enumerate(machines):
            if machine not in self.sections:
                section = MachineSection(self.expanded, self.refresh)
                self.sections[machine] = section
                self.group_rows.insertWidget(index, section)

    def selection_changed(self):
        self.sync_sections()
        if self.monitor_visible:
            self.refresh()
            self.archive_due.start()

    def archive(self):
        if self.expanded and self.monitor_visible:
            self.request_archive(self.selected_machine, self.span, self.selection)

    def refresh(self):
        self.sync_devices()
        now, span, scope = time(), self.span, self.selected_machine
        cfg = self.dashboard.settings
        archive = self.expanded and cfg.persistent
        if scope == ALL:
            self.sync_sections()
            self.refresh_sections(now, span, archive)
            return
        text = self.scope_status(scope)
        set_label(self.header, text + f" · Tray {cfg.tray_refresh:g} s")
        device_kind, selected = self.selection
        for kind, card in self.cards.items():
            if not self.expanded and kind not in cfg.hover_resources:
                continue
            selected_device = selected if kind == device_kind or (kind == "vram" and device_kind == "gpu") else TOTAL
            self.refresh_card(card, scope, kind, selected_device, now, span, archive)
        if self.expanded:
            self.refresh_table(self.table, scope, selected, now, span, archive)

    def scope_status(self, scope, concise=False):
        collectors = self.dashboard.collectors
        cfg = self.dashboard.settings
        status = collectors.statuses.get(scope)
        os_label = collectors.systems.get(scope) or next(
            (t.os_type for t in cfg.targets if t.identifier == scope), "")
        last = collectors.last.get(scope)
        last_text = f" · Last sample {strftime('%H:%M:%S', localtime(last))}" if self.expanded and last else ""
        text = f"{os_label} · {self.dashboard.state(scope)} · Sample {self.dashboard.interval(scope):g} s{last_text}"
        if status and status.detail:
            text += f" · {status.detail}"
        if self.expanded and not concise:
            cpu_name = next((d.name for d in collectors.devices[scope].values() if d.kind == "cpu-info"), "")
            if cpu_name:
                text += f" · {cpu_name}"
        return text

    def refresh_sections(self, now, span, archive):
        machines = self.dashboard.monitored()
        online = sum(self.dashboard.state(machine) == Connection.ONLINE for machine in machines)
        set_label(self.header, f"{online}/{len(machines)} connected · Individual machine histories")
        for machine in machines:
            section = self.sections[machine]
            set_label(section.title, f"{self.dashboard.name(machine)} · {self.scope_status(machine, concise=True)}")
            for kind, card in section.cards.items():
                self.refresh_card(card, machine, kind, TOTAL, now, span, archive, compact=True)
            if section.table is not None and section.table.isVisible():
                self.refresh_table(section.table, machine, TOTAL, now, span, archive)

    def refresh_card(self, card, scope, kind, device, now, span, archive, compact=False):
        spec = resource_series(kind, self.dashboard.settings)
        plots, scale, gap = self.dashboard.series(scope, kind, tuple(metric for metric, _ in spec),
                                                  device, span, now, archive)
        lines = []
        for metric, color in spec:
            chart, current = plots[metric]
            value = display_value(current)
            if kind in ("ram", "vram") and not compact:
                key = "ram.used" if kind == "ram" else "gpu.vram_used"
                extra = self.dashboard.collectors.history.latest(scope, device, key)
                if extra and extra.valid:
                    value += f" · {format_value(extra.value, extra.unit)}"
            if kind == "net":
                label = card.direction_labels[metric]
                set_label(label, f"{NETWORK[metric][0]}: {value}")
                foreground = QColor(color)
                if card.palette().color(QPalette.ColorRole.Window).lightness() > 150:
                    foreground = foreground.darker(180)
                style = f"color: {foreground.name()};"
                if style != label.styleSheet():
                    label.setStyleSheet(style)
            else:
                set_label(card.value, value)
            lines.append((chart, color))
        card.plot.set_data(lines, now, span, gap)
        rate_plot = kind == "net" or (kind == "disk" and spec[0][0] != "disk.active")
        scale_text = f"Scale {format_value(scale, 'B/s')}" if rate_plot else "0–100%"
        set_label(card.footer, scale_text)
        if card.plot.toolTip() != scale_text:
            card.plot.setToolTip(scale_text)

    def refresh_table(self, table, machine, device, now, span, archive):
        data = []
        collectors = self.dashboard.collectors
        device_info = collectors.devices.get(machine, {}).get(device)
        label = self.dashboard.name(machine) + (f" · {device_info.name}" if device_info else "")
        for metric, title in METRIC_NAMES.items():
            resource = "vram" if metric.startswith("gpu.vram") else metric.split(".")[0]
            if not selected_resource(machine, resource, self.dashboard.settings):
                continue
            archive_key = (machine, device, metric)
            current = self.dashboard.observation(machine, resource, device, metric, now)
            if current is None and (not archive or archive_key not in self.dashboard.archived):
                continue
            rows = self.dashboard.history(archive_key, now - span, archive)
            values = [item.value for item in rows if item.valid]
            current_value = display_value(current)
            stats = ([format_value(value, rows[-1].unit) for value in (min(values), max(values), sum(values) / len(values))]
                     if values else ["—"] * 3)
            data.append((title, current_value, *stats, label))
        if table.rowCount() != len(data):
            table.setRowCount(len(data))
        for row, columns in enumerate(data):
            for column, value in enumerate(columns):
                item = table.item(row, column)
                if item is None:
                    table.setItem(row, column, QTableWidgetItem(value))
                elif item.text() != value:
                    item.setText(value)
