# Adaptive Resource Monitor
# Original developer: Sonja M Thomas
# Copyright 2010-2026 SLT Design Creations, LLC
# Licensed under the Design Creations Attribution-NonCommercial-ShareAlike License v1.0.
# See LICENSE.md for complete license terms.
# https://www.designcreations.us/

"""Timestamp-based plots shared by the monitoring windows and tray."""
from time import time

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from .config import MachineDisplay
from .model import ALL, Connection, LOCAL, NETWORK, RESOURCES, TOTAL, current_reading, graph_scale, normalized

METRICS = {kind: d[2] for kind, d in RESOURCES.items()}


def metric_for(kind, settings):
    return settings.disk_mode if kind == "disk" else METRICS[kind]


def resource_series(kind, settings):
    if kind == "net":
        return tuple(settings.network_colors.items())
    return ((metric_for(kind, settings), settings.colors[kind]),)


def selected_resource(machine, kind, settings):
    return machine == LOCAL or any(target.identifier == machine and kind in target.resources
                                   for target in settings.targets)


def plot_scale(metric, settings, readings):
    if metric not in ("disk.read", "disk.write", "disk.total", "net.receive", "net.transmit", "net.total"):
        return 100
    reference = settings.disk_scale if metric.startswith("disk") else settings.net_scale
    return graph_scale(readings, reference)


def bucket_peaks(points, now, span, columns):
    """Thin densely sampled history to the largest actual observation per column."""
    result = []
    last_column = None
    for stamp, value in points:
        column = int((stamp - now + span) / span * columns)
        if not 0 <= column <= columns:
            continue
        if value is None:
            if result and result[-1][1] is not None:
                result.append((stamp, None))
            last_column = None
        elif column == last_column:
            if value >= result[-1][1]:
                result[-1] = stamp, value
        else:
            result.append((stamp, value))
            last_column = column
    return result


def composite_samples(series, now, span, gap, columns):
    """Pick the strongest resource trace within each time bin of one machine."""
    step = max(span / columns, min(gap, span) / 3)
    size = max(1, int(span / step))
    bins = {}
    for label, readings in series.items():
        for stamp, value in readings:
            index = min(size, int((stamp - now + span) / step))
            if value is None:
                bins.setdefault(index, (stamp, None, label))
                continue
            old = bins.get(index)
            if old is None or old[1] is None or value > old[1]:
                bins[index] = stamp, value, label
    return [bins[index] for index in sorted(bins)]


def stroke(painter, rect, points, now, span, gap, color, width=1.3):
    if not points:
        return
    points = bucket_peaks(points, now, span, max(2, int(rect.width())))
    path = QPainterPath()
    previous = None
    for stamp, value in points:
        if value is None:
            previous = None
            continue
        fraction = (stamp - (now - span)) / span
        x = rect.left() + fraction * max(0, rect.width() - .5)
        y = rect.bottom() - value / 100 * rect.height()
        point = QPointF(x, y)
        if previous is None or stamp - previous > gap:
            path.moveTo(point)
            path.lineTo(point + QPointF(.2, 0))
            path.moveTo(point)
        else:
            path.lineTo(point)
        previous = stamp
    painter.setPen(QPen(QColor(color), width))
    painter.drawPath(path)


class Dashboard:
    def __init__(self, collectors, machine_display=None):
        self.collectors = collectors
        self.machine_display = machine_display or MachineDisplay.from_legacy(collectors.settings)
        self.archived = {}

    @property
    def settings(self):
        return self.collectors.settings

    def name(self, machine):
        if machine == LOCAL:
            return "Local Machine"
        if machine == ALL:
            return "All Systems"
        return next((t.name for t in self.settings.targets if t.identifier == machine), "Unknown machine")

    def machines(self):
        return self.machine_display.order

    def monitored(self):
        eligible = MachineDisplay.eligible(self.settings)
        return [machine for machine in self.machines() if machine in eligible]

    def state(self, machine):
        status = self.collectors.statuses.get(machine)
        return status.state if status else Connection.OFFLINE

    def interval(self, machine):
        return self.collectors.intervals.get(machine, 1)

    def history(self, key, cutoff, archive=False):
        live = self.collectors.history.since(*key, cutoff)
        if not archive:
            return live
        archived = self.archived.get(key, ())
        limit = live[0].timestamp if live else float("inf")
        return [r for r in archived if cutoff <= r.timestamp < limit] + live

    def observation(self, machine, kind, device, metric, now):
        key = (machine, device, metric)
        candidate = self.collectors.history.latest(*key)
        provider = {"cpu": "CPU", "ram": "Memory", "gpu": "GPU", "vram": "GPU",
                    "disk": "Storage", "net": "Network"}.get(kind)
        provider_state = self.collectors.provider_status.get((machine, provider))
        status = provider_state.state if machine == LOCAL and provider_state else self.state(machine)
        if status != Connection.ONLINE:
            candidate = self.collectors.history.last_valid.get(key, candidate)
        return current_reading(candidate, status, self.interval(machine), now)

    def series(self, machine, kind, metrics, device, span, now, archive=False):
        """Normalize one machine's resource traces against a shared reference."""
        enabled = selected_resource(machine, kind, self.settings)
        histories = {
            metric: self.history((machine, device, metric), now - span, archive) if enabled else []
            for metric in metrics
        }
        scale = plot_scale(metrics[0], self.settings,
                           (item for values in histories.values() for item in values))
        gap = max(2, self.interval(machine) * 3)
        if archive:
            gap = max(gap, span / 1200)
        result = {}
        for metric, values in histories.items():
            points = [(item.timestamp, normalized(item, scale)) for item in values]
            current = self.observation(machine, kind, device, metric, now) if enabled else None
            result[metric] = points, current
        return result, scale, gap


def paint_tray(painter, size, data, settings, period, now, status):
    if not settings.transparent:
        painter.fillRect(QRectF(0, 0, size, size), QColor(settings.background))
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    rect = QRectF(1, 1, size - 2, size - 3)
    if settings.mode == "Stacked" and data:
        height = rect.height() / len(data)
        for index, (traces, gap) in enumerate(data):
            band = QRectF(rect.x(), rect.y() + height * index, rect.width(), max(1, height - .35))
            shade = QColor(traces[0][2])
            shade.setAlpha(63)
            painter.setPen(QPen(shade, .6))
            painter.drawLine(band.bottomLeft(), band.bottomRight())
            for _, points, color in traces:
                stroke(painter, band, points, now, period, gap, color, .8)
    elif settings.mode == "Composite" and data:
        gap = max(gap for _, gap in data)
        points = {metric: values for traces, _ in data for metric, values, _ in traces}
        colors = {metric: color for traces, _ in data for metric, _, color in traces}
        for metric in NETWORK:
            if metric in points:
                stroke(painter, rect, points[metric], now, period, gap, colors[metric], .7)
        combined = composite_samples(points, now, period, gap, size)
        for left, right in zip(combined, combined[1:]):
            if left[1] is not None and right[1] is not None and right[0] - left[0] <= gap:
                stroke(painter, rect, [(left[0], left[1]), (right[0], right[1])], now, period, gap,
                       colors[right[2]], 1.4)
        isolated = [point for index, point in enumerate(combined) if point[1] is not None and
                    (index == 0 or combined[index - 1][1] is None or point[0] - combined[index - 1][0] > gap)]
        for stamp, value, kind in isolated:
            stroke(painter, rect, [(stamp, value)], now, period, gap, colors[kind], 1.4)
    else:
        for traces, gap in data:
            for _, points, color in traces:
                stroke(painter, rect, points, now, period, gap, color)
    if status:
        painter.setPen(QPen(QColor("#151820"), 1))
        painter.setBrush(QColor("#ffd06c"))
        painter.drawEllipse(QRectF(size - 5.5, .5, 5, 5))


def tray_icon(dashboard, machine, now=None):
    settings = dashboard.settings
    now = time() if now is None else now
    period = settings.tray_range
    data = []
    for kind in RESOURCES:
        if kind not in settings.resources:
            continue
        series = resource_series(kind, settings)
        plots, _, gap = dashboard.series(machine, kind, tuple(metric for metric, _ in series),
                                        TOTAL, period, now)
        data.append(([(metric, plots[metric][0], color) for metric, color in series], gap))
    status = dashboard.state(machine) != Connection.ONLINE
    icon = QIcon()
    for size in (16, 20, 24, 32, 40, 48):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        paint_tray(painter, size, data, settings, period, now, status)
        painter.end()
        icon.addPixmap(pixmap)
    return icon


class Plot(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(24)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.data = None
        self.setAccessibleName("Resource history")

    def set_data(self, series, now, period, gap):
        self.data = series, now, period, gap
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -2)
        painter.fillRect(rect, QColor("#151923"))
        painter.setPen(QPen(QColor("#3c4556"), .7))
        for step in range(1, 5):
            x = rect.x() + rect.width() * step / 5
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
        for step in range(1, 3):
            y = rect.y() + rect.height() * step / 3
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        if self.data:
            series, now, period, gap = self.data
            for points, color in series:
                stroke(painter, rect, points, now, period, gap, color)

    def sizeHint(self):
        return QSize(155, 46)
