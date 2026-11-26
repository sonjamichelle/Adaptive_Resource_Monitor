"""Use the cursor and Explorer's registered icon geometry for hover."""
import ctypes as ct
from ctypes import wintypes as w
from time import monotonic

from PySide6.QtCore import QPoint, QRect, QSignalBlocker, QSize
from PySide6.QtGui import QCursor, QGuiApplication


class NativeCursor:
    def __init__(self):
        user = ct.WinDLL("user32")
        self.position = user.GetCursorPos
        self.position.argtypes = [ct.POINTER(w.POINT)]
        self.position.restype = w.BOOL

    def raw(self):
        pt = w.POINT()
        if self.position(ct.byref(pt)):
            return QPoint(pt.x, pt.y)
        return None


def place_popup(area, icon, size):
    width, height = min(size.width(), area.width()), min(size.height(), area.height())
    # Pick the edge adjacent to the icon, including vertical taskbars.
    distances = {
        "top": abs(icon.center().y() - area.top()),
        "bottom": abs(icon.center().y() - area.bottom()),
        "left": abs(icon.center().x() - area.left()),
        "right": abs(icon.center().x() - area.right()),
    }
    edge = min(distances, key=distances.get)
    x, y = icon.center().x() - width // 2, icon.center().y() - height // 2
    if edge == "bottom":
        y = min(area.bottom() - height + 1, icon.top() - height - 2)
    elif edge == "top":
        y = max(area.top(), icon.bottom() + 2)
    elif edge == "right":
        x = min(area.right() - width + 1, icon.left() - width - 2)
    else:
        x = max(area.left(), icon.right() + 2)
    x = max(area.left(), min(x, area.right() - width + 1))
    y = max(area.top(), min(y, area.bottom() - height + 1))
    return QRect(x, y, width, height)


class HoverState:
    def __init__(self):
        self.candidate = None
        self.entered = 0
        self.left = None

    def update(self, now, hovered, over_popup, visible, pinned, hover_delay, dismiss_delay):
        if hovered != self.candidate:
            self.candidate, self.entered = hovered, now
        if pinned:
            self.left = None
            return None
        if hovered is not None:
            self.left = None
            if not visible and now - self.entered >= hover_delay:
                return "show"
        elif visible and not over_popup:
            if self.left is None:
                self.left = now
            elif now - self.left >= dismiss_delay:
                self.left = None
                return "hide"
        else:
            self.left = None
        return None


class HoverMonitor:
    def __init__(self, popup, dashboard, icons, monitor_scope):
        self.popup, self.dashboard, self.icons = popup, dashboard, icons
        self.monitor_scope = monitor_scope
        self.cursor = NativeCursor()
        self.state = HoverState()
        self.anchor = None

    def tick(self):
        raw, cursor = self.cursor.raw(), QCursor.pos()
        if raw is None:
            return
        hovered = None
        for machine, tray in self.icons.items():
            # Qt's Windows backend calls Shell_NotifyIconGetRect and exposes
            # the result in native pixels through QSystemTrayIcon.geometry().
            if tray.geometry().contains(raw):
                hovered = machine
                break
        over = self.popup.isVisible() and (self.popup.frameGeometry().contains(cursor)
                                           or self.popup.interval.view().isVisible()
                                           or self.popup.machine.view().isVisible())
        cfg = self.dashboard.settings
        visible = self.popup.isVisible() and (self.anchor == hovered or hovered is None or over)
        action = self.state.update(monotonic(), hovered, over, visible, self.popup.pinned,
                                   cfg.hover_delay / 1000, cfg.dismiss_delay / 1000)
        if action == "show":
            self.show(hovered)
        elif action == "hide":
            self.popup.hide()

    def show(self, machine):
        tray = self.icons.get(machine)
        raw_rect = tray.geometry() if tray else QRect()
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        cfg = self.dashboard.settings
        screen_rect = screen.geometry()
        raw, qt = self.cursor.raw(), QCursor.pos()
        if raw is not None and not raw_rect.isEmpty():
            ratio = screen.devicePixelRatio()
            corner = qt + QPoint(round((raw_rect.x() - raw.x()) / ratio), round((raw_rect.y() - raw.y()) / ratio))
            rect = QRect(corner, QSize(max(1, round(raw_rect.width() / ratio)),
                                      max(1, round(raw_rect.height() / ratio))))
        else:
            rect = QRect(qt if screen_rect.contains(qt) else screen_rect.center(), QSize(1, 1))
        self.anchor = machine
        self.popup.set_machine(self.monitor_scope(machine))
        position = place_popup(screen.availableGeometry(), rect, QSize(cfg.popup_width, cfg.popup_height))
        self.popup.setGeometry(position)
        self.popup.show()
        self.popup.refresh()

    def pin(self, value, machine=None):
        self.popup.pinned = value
        with QSignalBlocker(self.popup.pin):
            self.popup.pin.setChecked(value)
        self.popup.pin.setText("Unpin" if value else "Pin")
        if value and (not self.popup.isVisible() or machine is not None):
            self.show(machine or self.popup.selected_machine)
