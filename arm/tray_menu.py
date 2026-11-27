"""Design Creations tray commands for each visible ARM icon."""
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QActionGroup, QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QStyle, QVBoxLayout, QWidget, QWidgetAction

from .about import BrandImage
from .config import TRAY_MODES
from .model import ALL, LOCAL
from .version import NAME, VERSION

SP = QStyle.StandardPixmap


class TrayMenu(QMenu):
    def __init__(self, app, scope):
        super().__init__()
        self.app, self.scope = app, scope
        self.setAccessibleName(f"{NAME} tray menu")
        self.add_header()
        self.update = self.action(self, "", None, app.open_update)
        self.update.setVisible(False)
        font = self.update.font()
        font.setBold(True)
        self.update.setFont(font)
        self.addSeparator()
        open_monitor = self.action(self, "Open Resource Monitor", SP.SP_ComputerIcon,
                                   app.open_expanded)
        self.setDefaultAction(open_monitor)
        self.pin = self.action(self, "Pin Resource Monitor", None, lambda: app.toggle_pin(scope))
        self.pin.setCheckable(True)

        self.addSeparator()
        machines = self.submenu("Monitor Machine", SP.SP_ComputerIcon)
        self.machine_group = QActionGroup(self)
        self.machine_group.setExclusive(True)
        self.local = self.machine_action(machines, "Local Machine", LOCAL)
        self.remote = machines.addMenu(self.standard_icon(SP.SP_DriveNetIcon), "Configured Remote Machines")
        self.all = self.machine_action(machines, "All Systems", ALL)
        self.remote_entries = {}
        self.targets = None

        display = self.submenu("Tray Display", SP.SP_FileDialogDetailedView)
        mode_group = QActionGroup(self)
        mode_group.setExclusive(True)
        self.modes = {}
        for mode in TRAY_MODES:
            action = self.action(display, mode, None, lambda mode=mode: app.set_tray_display(mode))
            action.setCheckable(True)
            mode_group.addAction(action)
            self.modes[mode] = action
        self.action(self, "Resource History", SP.SP_FileDialogListView,
                    lambda: app.open_expanded(history=True))

        self.addSeparator()
        targets = self.submenu("Remote Targets", SP.SP_DriveNetIcon)
        self.action(targets, "Add Remote Target", SP.SP_FileDialogNewFolder, app.add_target)
        self.action(targets, "Manage Remote Targets", SP.SP_DriveNetIcon, app.manage)
        self.action(self, "Settings", SP.SP_FileDialogDetailedView, app.open_settings)
        self.start = self.action(self, "Start with Windows", None, app.toggle_startup)
        self.start.setCheckable(True)

        self.addSeparator()
        self.action(self, f"About {NAME}", SP.SP_MessageBoxInformation, app.about)
        self.action(self, "Check for Updates", SP.SP_BrowserReload, app.check_for_updates)
        self.action(self, "Design Creations Website", SP.SP_DriveNetIcon, app.open_website)
        self.addSeparator()
        self.action(self, f"Exit {NAME}", None, app.qt.quit)
        self.aboutToShow.connect(self.refresh)

    def add_header(self):
        wrapper = QWidget()
        wrapper.setObjectName("trayIdentity")
        header = QHBoxLayout(wrapper)
        header.setContentsMargins(10, 5, 10, 3)
        header.setSpacing(8)
        artwork = BrandImage(self.app.brand_icon.pixmap(QSize(24, 24), self.devicePixelRatioF()),
                             f"{NAME} icon", (24, 24))
        header.addWidget(artwork)
        labels = QVBoxLayout()
        labels.setSpacing(0)
        title = QLabel(NAME)
        title.setFont(QFont("Georgia", 10, QFont.Weight.Bold))
        self.version = QLabel(VERSION)
        self.version.setObjectName("trayVersion")
        labels.addWidget(title)
        labels.addWidget(self.version)
        header.addLayout(labels)
        identity = QWidgetAction(self)
        identity.setDefaultWidget(wrapper)
        identity.setEnabled(False)
        self.addAction(identity)

    def standard_icon(self, icon):
        return self.style().standardIcon(icon) if icon is not None else QIcon()

    def action(self, menu, title, icon, callback):
        action = menu.addAction(self.standard_icon(icon), title)
        action.triggered.connect(lambda _checked=False: callback())
        return action

    def submenu(self, title, icon):
        return self.addMenu(self.standard_icon(icon), title)

    def machine_action(self, menu, name, machine):
        action = self.action(menu, name, None, lambda: self.app.select_machine(machine, self.scope))
        action.setCheckable(True)
        self.machine_group.addAction(action)
        return action

    def refresh(self):
        app = self.app
        targets = [(t.identifier, t.name, app.dashboard.state(t.identifier).value) for t in app.settings.targets]
        if targets != self.targets:
            self.targets = targets
            self.remote.clear()
            self.remote_entries = {
                machine: self.machine_action(self.remote, f"{name.replace('&', '&&')} · {status}", machine)
                for machine, name, status in targets
            }
            self.remote.menuAction().setVisible(bool(targets))
        choices = {LOCAL: self.local, ALL: self.all, **self.remote_entries}
        choices[app.monitor_machine()].setChecked(True)
        self.modes[app.settings.mode].setChecked(True)
        self.pin.setChecked(app.popup.pinned and app.hover.anchor == self.scope)
        self.start.setChecked(app.startup_enabled())

    def theme(self, colors):
        icon = QIcon()
        for size in (16, 24, 32):
            pixels = QPixmap(size, size)
            pixels.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixels)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.scale(size / 16, size / 16)
            pen = QPen(QColor(colors.accent), 1.7)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(8, 2, 8, 10)
            painter.drawLine(5, 7, 8, 10)
            painter.drawLine(11, 7, 8, 10)
            painter.drawLine(3, 13, 13, 13)
            painter.end()
            icon.addPixmap(pixels)
        self.update.setIcon(icon)
        self.setStyleSheet(f"""
            QMenu {{
                background-color: {colors.background}; color: {colors.text};
                border: 1px solid {colors.border}; padding: 3px;
            }}
            QMenu::item {{ padding: 4px 25px 4px 27px; }}
            QMenu::item:selected {{ background: {colors.highlight}; color: {colors.text}; }}
            QMenu::separator {{
                height: 1px; background: {colors.border}; margin: 3px 6px;
            }}
            QWidget#trayIdentity {{ background-color: {colors.background}; }}
            QWidget#trayIdentity QLabel {{ color: {colors.text}; }}
            QLabel#trayVersion {{ color: {colors.muted}; }}
        """)
