"""Keep user-facing windows within the work area and remember their placement."""
import logging

from PySide6.QtCore import QByteArray, QEvent, QObject, QTimer
from PySide6.QtGui import QGuiApplication

from .update_client import write_atomic

LOG = logging.getLogger(__name__)


def fit_work_area(window):
    if window.isMinimized() or window.isMaximized() or window.isFullScreen():
        return
    frame = window.frameGeometry()
    screen = QGuiApplication.screenAt(frame.center()) or window.screen()
    if screen is None:
        return
    area = screen.availableGeometry()
    if frame.width() > area.width() or frame.height() > area.height():
        window.resize(window.width() - max(0, frame.width() - area.width()),
                      window.height() - max(0, frame.height() - area.height()))
        frame = window.frameGeometry()
    x = max(area.left(), min(frame.left(), area.right() - frame.width() + 1))
    y = max(area.top(), min(frame.top(), area.bottom() - frame.height() + 1))
    if (x, y) != (frame.left(), frame.top()):
        window.move(x, y)


class WindowGeometry(QObject):
    def __init__(self, window, path):
        super().__init__(window)
        self.window, self.path = window, path
        self.saved = None
        try:
            geometry = path.read_bytes()
            if window.restoreGeometry(QByteArray(geometry)):
                self.saved = geometry
        except FileNotFoundError:
            pass
        except OSError as exc:
            LOG.warning("Could not read %s: %s", path.name, exc)
        self.timer = QTimer(self, singleShot=True, interval=350)
        self.timer.timeout.connect(self.save)
        window.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Show:
            fit_work_area(watched)
        if event.type() == QEvent.Type.Hide:
            self.timer.stop()
            self.save()
        elif watched.isVisible() and event.type() in (QEvent.Type.Show, QEvent.Type.Move, QEvent.Type.Resize,
                                                     QEvent.Type.WindowStateChange):
            self.timer.start()
        return super().eventFilter(watched, event)

    def save(self):
        if self.window.isMinimized():
            return
        if self.window.isVisible():
            fit_work_area(self.window)
        geometry = bytes(self.window.saveGeometry())
        if geometry != self.saved:
            try:
                write_atomic(self.path, geometry)
                self.saved = geometry
            except OSError as exc:
                LOG.warning("Could not save %s: %s", self.path.name, exc)
