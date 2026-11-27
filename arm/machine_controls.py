"""Machine checklists and drag controls shared by monitoring views."""
from PySide6.QtCore import QEvent, QObject, QPoint, QSignalBlocker, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFrame, QMenu, QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget, QWidgetAction,
)

from .model import ALL


class MachineCheckbox(QCheckBox):
    def hitButton(self, point):
        return self.rect().contains(point)


class MachineMenu(QMenu):
    def __init__(self, dashboard, toggle, parent=None):
        super().__init__(parent)
        self.dashboard = dashboard
        self.toggle = toggle
        self.entries = {}
        self.signature = None
        self.master = self.checkbox("All Systems", ALL)
        action = QWidgetAction(self)
        action.setDefaultWidget(self.master)
        self.addAction(action)
        self.addSeparator()
        self.scroll = QScrollArea()
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        rows = QWidget()
        self.rows = QVBoxLayout(rows)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(0)
        self.scroll.setWidget(rows)
        action = QWidgetAction(self)
        action.setDefaultWidget(self.scroll)
        self.addAction(action)
        self.aboutToShow.connect(self.sync)

    def checkbox(self, name, machine):
        box = MachineCheckbox(name.replace("&", "&&"))
        box.setStyleSheet("QCheckBox { padding: 4px 9px; }")
        box.setAccessibleName(name)
        box.clicked.connect(lambda: self.toggle(machine))
        return box

    def sync(self):
        dashboard = self.dashboard
        eligible = set(dashboard.monitored())
        display = dashboard.machine_display
        signature = [(machine, dashboard.name(machine)) for machine in dashboard.machines()]
        if signature != self.signature:
            for row in self.entries.values():
                self.rows.removeWidget(row)
                row.hide()
                row.deleteLater()
            self.entries = {machine: self.checkbox(name, machine) for machine, name in signature}
            self.signature = signature
            for box in self.entries.values():
                self.rows.addWidget(box)
            height = sum(box.sizeHint().height() for box in self.entries.values())
            self.scroll.setFixedHeight(min(height, 280))
            self.scroll.setMinimumWidth(max(box.sizeHint().width() for box in self.entries.values()) + 18)
        selected = set(display.selected)
        with QSignalBlocker(self.master):
            self.master.setTristate(True)
            self.master.setCheckState(
                Qt.CheckState.Checked if eligible <= selected else
                Qt.CheckState.PartiallyChecked if eligible & selected else Qt.CheckState.Unchecked)
        for machine, box in self.entries.items():
            box.setEnabled(machine in eligible)
            box.setChecked(machine in selected)


class MachineDropdown(QPushButton):
    def __init__(self, dashboard, toggle):
        super().__init__()
        self.dashboard = dashboard
        self.setAccessibleName("Machine selection")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(145)
        self.setStyleSheet("""
            QPushButton { text-align: left; padding: 3px 22px 3px 8px; min-height: 17px; }
            QPushButton::menu-indicator { subcontrol-position: center right; right: 5px; }
        """)
        self.checklist = MachineMenu(dashboard, toggle, self)
        self.setMenu(self.checklist)

    def sync(self, displayed):
        names = [self.dashboard.name(machine) for machine in displayed]
        if not names:
            label = "No Systems Selected"
        elif len(names) == 1:
            label = names[0]
        elif len(names) == len(self.dashboard.monitored()):
            label = "All Systems"
        else:
            label = f"{len(names)} Systems Selected"
        metrics = self.fontMetrics()
        label = metrics.elidedText(label, Qt.TextElideMode.ElideRight, 165)
        self.setMinimumWidth(max(145, metrics.horizontalAdvance(label) + 34))
        self.setText(label)
        self.setToolTip("\n".join(names))
        self.checklist.sync()


class MachineDrag(QObject):
    def __init__(self, scroll, items, dropped):
        super().__init__(scroll)
        self.scroll, self.items, self.dropped = scroll, items, dropped
        self.viewport = scroll.viewport()
        self.line = QFrame(self.viewport)
        self.line.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.line.setStyleSheet("background-color: palette(highlight)")
        self.line.hide()
        self.widgets = {}
        self.source = self.origin = self.position = self.index = None
        self.active = False
        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self.autoscroll)

    def watch(self, widget, machine_at):
        self.widgets[widget] = machine_at
        widget.installEventFilter(self)
        widget.setCursor(Qt.CursorShape.OpenHandCursor)

    def unwatch(self, widget):
        if self.origin is widget:
            self.cancel()
        self.widgets.pop(widget, None)
        widget.removeEventFilter(self)

    def eventFilter(self, widget, event):
        kind = event.type()
        if kind == QEvent.Type.KeyPress and self.active and event.key() == Qt.Key.Key_Escape:
            self.cancel()
            return True
        if widget is self.origin and kind in (QEvent.Type.Hide, QEvent.Type.UngrabMouse):
            self.cancel()
        if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self.source = self.widgets[widget](event.position().toPoint())
            self.origin = widget if self.source is not None else None
            self.start = event.globalPosition().toPoint()
            return widget is self.origin and widget is not self.viewport
        if widget is not self.origin:
            return False
        if kind == QEvent.Type.MouseMove:
            position = event.globalPosition().toPoint()
            if (not self.active and event.buttons() & Qt.MouseButton.LeftButton
                    and (position - self.start).manhattanLength() >= QApplication.startDragDistance()):
                self.active = True
                widget.setCursor(Qt.CursorShape.ClosedHandCursor)
                widget.grabMouse()
                widget.grabKeyboard()
                self.timer.start()
            if self.active:
                self.position = position
                self.indicate()
                return True
        if kind == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            active = self.active
            if active:
                self.position = event.globalPosition().toPoint()
                self.indicate()
            source, index = self.source, self.index
            self.cancel()
            if active and index is not None:
                self.dropped(source, index)
            return active
        return False

    def indicate(self):
        point = self.viewport.mapFromGlobal(self.position)
        if not self.viewport.rect().contains(point):
            self.index = None
            self.line.hide()
            return
        rows = [(machine, rect) for machine, rect in self.items() if machine != self.source]
        self.index = next((index for index, (_, rect) in enumerate(rows) if point.y() < rect.center().y()), len(rows))
        if not rows:
            return
        edges = [rect.top() for _, rect in rows] + [rows[-1][1].bottom() + 1]
        y = max(0, min(self.viewport.height() - 3, edges[self.index]))
        self.line.setGeometry(3, y, max(1, self.viewport.width() - 6), 2)
        self.line.raise_()
        self.line.show()

    def autoscroll(self):
        point = self.viewport.mapFromGlobal(self.position)
        threshold = min(40, self.viewport.height() // 4)
        if 0 <= point.x() < self.viewport.width() and -threshold <= point.y() < self.viewport.height() + threshold:
            direction = -1 if point.y() < threshold else 1 if point.y() >= self.viewport.height() - threshold else 0
            if direction:
                bar = self.scroll.verticalScrollBar()
                bar.setValue(bar.value() + direction * max(4, bar.singleStep() // 2))
                self.indicate()

    def cancel(self):
        widget, active = self.origin, self.active
        self.source = self.origin = self.index = None
        self.active = False
        self.timer.stop()
        self.line.hide()
        if active:
            widget.releaseKeyboard()
            widget.releaseMouse()
            widget.setCursor(Qt.CursorShape.OpenHandCursor)
