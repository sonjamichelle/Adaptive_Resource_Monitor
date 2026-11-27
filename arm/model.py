# Adaptive Resource Monitor
# Original developer: Sonja M Thomas
# Copyright 2010-2026 SLT Design Creations, LLC
# Licensed under the Design Creations Attribution-NonCommercial-ShareAlike License v1.0.
# See LICENSE.md for complete license terms.
# https://www.designcreations.us/

from collections import defaultdict, deque
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from time import time

LOCAL = "local"
ALL = "@all"
TOTAL = "@total"
NETWORK = {"net.receive": ("IN", "#65df79"), "net.transmit": ("OUT", "#ff686b")}
INTERVALS = (0.5, 1, 2, 5, 10)
RANGES = {30: "30 seconds", 60: "60 seconds", 300: "5 minutes", 900: "15 minutes",
          1800: "30 minutes", 3600: "1 hour", 21600: "6 hours", 86400: "1 day",
          604800: "7 days", 2592000: "30 days"}
RESOURCES = {
    "cpu": ("CPU", "#68df79", "cpu.util"),
    "gpu": ("GPU", "#d394ff", "gpu.util"),
    "ram": ("RAM", "#66aaff", "ram.util"),
    "vram": ("VRAM", "#ffd75a", "gpu.vram_pct"),
    "disk": ("Disk I/O", "#ff686b", "disk.total"),
    "net": ("Network", "#58e7e7", "net.total"),
}
DISK_MODES = {"disk.active": "Active time", "disk.read": "Read throughput",
              "disk.write": "Write throughput", "disk.total": "Combined throughput"}


class Availability(StrEnum):
    VALID = "valid"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    ERROR = "error"
    STALE = "stale"
    DISCONNECTED = "disconnected"


class Connection(StrEnum):
    OFFLINE = "Disconnected"
    CONNECTING = "Connecting"
    ONLINE = "Connected"
    RETRYING = "Reconnecting"
    ERROR = "Connection failed"
    TRUST = "Host key approval required"
    UNSUPPORTED = "Unsupported"
    DISABLED = "Monitoring disabled"


@dataclass(frozen=True, slots=True)
class Device:
    kind: str
    identifier: str
    name: str


@dataclass(frozen=True, slots=True)
class Reading:
    machine: str
    device: str
    metric: str
    value: float | None
    unit: str
    timestamp: float
    availability: Availability = Availability.VALID
    diagnostic: str = ""

    @property
    def valid(self):
        return (self.availability == Availability.VALID and self.value is not None
                and isinstance(self.value, (int, float)) and isfinite(self.value))


@dataclass(frozen=True, slots=True)
class Sample:
    machine: str
    provider: str
    timestamp: float
    readings: tuple[Reading, ...]
    devices: tuple[Device, ...] = ()


@dataclass(frozen=True, slots=True)
class Status:
    machine: str
    state: Connection
    detail: str = ""
    trust: object = None


def readings(machine, timestamp, device, metrics):
    return tuple(
        Reading(machine, device, key, value, unit, timestamp, Availability.VALID if value is not None
                else Availability.UNAVAILABLE)
        for key, (value, unit) in metrics.items()
    )


def rate(previous, current, elapsed, interval):
    if previous is None or current is None or current < previous:
        return None
    if not 0 < elapsed <= max(interval * 3, 2):
        return None
    return (current - previous) / elapsed


def usage(used, total):
    return min(100.0, 100.0 * used / total) if used is not None and total and used >= 0 else None


def sum_known(values):
    values = [v for v in values if v is not None]
    return sum(values) if values else None


def max_known(values):
    return max((v for v in values if v is not None), default=None)


def aggregate(machine, stamp, kind, data):
    if not data:
        return ()
    metrics = {}
    for key, (_, unit) in data[0].items():
        maximum = key in {"gpu.util", "gpu.encode", "gpu.decode", "gpu.compute", "disk.active"}
        if key in {"gpu.vram_used", "gpu.vram_total", "gpu.vram_free"}:
            # Include only devices with a measured capacity and usage pair.
            values = (item[key][0] for item in data
                      if item["gpu.vram_used"][0] is not None and item["gpu.vram_total"][0])
        else:
            values = (item[key][0] for item in data)
        metrics[key] = ((max_known if maximum else sum_known)(values), unit)
    if kind == "gpu":
        for key in ("temperature", "clock", "memory_clock", "power_limit", "fan"):
            metrics.pop(f"gpu.{key}", None)
        metrics["gpu.vram_pct"] = (usage(metrics["gpu.vram_used"][0],
                                         metrics["gpu.vram_total"][0]), "%")
        for key in ("shared_pct", "shared_used", "shared_total"):
            metrics.pop(f"gpu.{key}", None)
    if kind == "net":
        metrics.pop("net.up", None)
        metrics.pop("net.link", None)
        metrics["net.util"] = (max_known(item["net.util"][0] for item in data), "%")
    return readings(machine, stamp, TOTAL, metrics)


class History:
    def __init__(self, max_seconds=3600, max_points=7400):
        self.max_seconds = max_seconds
        self.series = defaultdict(lambda: deque(maxlen=max_points))
        self.last_valid = {}

    def add(self, items):
        for item in items:
            key = (item.machine, item.device, item.metric)
            buf = self.series[key]
            if buf and item.timestamp <= buf[-1].timestamp:
                continue
            buf.append(item)
            if item.valid:
                self.last_valid[key] = item
            cutoff = item.timestamp - self.max_seconds
            while buf and buf[0].timestamp < cutoff:
                buf.popleft()

    def since(self, machine, device, metric, cutoff):
        buf = self.series.get((machine, device, metric), ())
        result = []
        for item in reversed(buf):
            if item.timestamp < cutoff:
                break
            result.append(item)
        return list(reversed(result))

    def latest(self, machine, device, metric):
        buf = self.series.get((machine, device, metric))
        return buf[-1] if buf else None

    def remove_machine(self, machine):
        for key in list(self.series):
            if key[0] == machine:
                del self.series[key]
                self.last_valid.pop(key, None)


def graph_scale(items, reference=0):
    if reference > 0:
        return reference
    peak = max((r.value for r in items if r.valid), default=0)
    step = 1024.0
    while step < peak:
        step *= 2
    return step


def normalized(reading, scale):
    if not reading.valid or scale <= 0:
        return None
    return min(100, max(0, reading.value * 100 / scale))


def current_reading(reading, status, interval, now=None):
    if reading is None or not reading.valid:
        return reading
    now = time() if now is None else now
    if status != Connection.ONLINE or now - reading.timestamp > max(3 * interval, 2):
        return Reading(reading.machine, reading.device, reading.metric, reading.value,
                       reading.unit, reading.timestamp, Availability.STALE)
    return reading


def format_value(value, unit):
    if value is None:
        return "Unavailable"
    if unit in {"B", "B/s"}:
        suffix = "/s" if unit == "B/s" else ""
        for base in ("B", "KiB", "MiB", "GiB", "TiB"):
            if abs(value) < 1024 or base == "TiB":
                return f"{value:,.1f} {base}{suffix}"
            value /= 1024
    if unit == "Mb/s" and value >= 1000:
        return f"{value / 1000:,.2f} Gb/s"
    if unit in {"count", "bool"}:
        return ("Up" if value else "Down") if unit == "bool" else f"{int(value)}"
    return f"{value:,.1f} {unit}"
