import logging
import platform
from time import perf_counter as monotonic, time

import psutil

from . import Provider
from .native import Pdh, commit, cpu_identity, interface_info, pagefiles, physical_cores
from ..model import (
    LOCAL, TOTAL, Availability, Device, Reading, Sample, aggregate, rate, readings, usage,
)

LOG = logging.getLogger(__name__)


class Cpu(Provider):
    identifier = "CPU"

    def __init__(self, settings):
        self.interval = settings.local_interval
        self.last = {}
        self.name = cpu_identity()
        self.cores = physical_cores()
        self.stamp = 0

    @staticmethod
    def times(row):
        return row.user + row.system + row.idle, row.user + row.system

    def sample(self):
        stamp, now = time(), monotonic()
        times = {index: self.times(value) for index, value in enumerate(psutil.cpu_times(percpu=True))}
        elapsed = now - self.stamp
        devices = [Device("cpu", f"cpu:{i}", f"Logical processor {i}") for i in times]
        devices.append(Device("cpu-info", "identity", self.name))
        values = {}
        items = []
        for index, (total, busy) in times.items():
            previous = self.last.get(index, (None, None))
            values[index] = (
                rate(previous[1], busy, elapsed, self.interval),
                rate(previous[0], total, elapsed, self.interval),
            )
            items.extend(readings(LOCAL, stamp, f"cpu:{index}", {
                "cpu.util": (usage(*values[index]), "%")
            }))
        cores = self.cores if {p for core in self.cores for p in core} == set(times) else []
        for index, core in enumerate(cores):
            device = f"core:{index}"
            devices.append(Device("cpu", device, f"Physical core {index}"))
            items.extend(readings(LOCAL, stamp, device, {"cpu.util": (cpu_group(values, core), "%")}))
        self.last, self.stamp = times, now
        frequency = psutil.cpu_freq()
        items.extend(readings(LOCAL, stamp, TOTAL, {
            "cpu.util": (cpu_group(values, times), "%"),
            "cpu.frequency": (frequency.current if frequency else None, "MHz"),
            "cpu.physical": (len(cores) or psutil.cpu_count(logical=False), "count"),
            "cpu.logical": (len(times), "count"),
        }))
        items.extend(Reading(LOCAL, TOTAL, metric, None, unit, stamp, Availability.UNSUPPORTED,
                             "No supported Windows CPU sensor provider")
                     for metric, unit in (("cpu.temperature", "°C"), ("cpu.power", "W")))
        return Sample(LOCAL, self.identifier, stamp, tuple(items), tuple(devices))


def cpu_group(values, indexes):
    pairs = [values[index] for index in indexes if index in values]
    if pairs and all(busy is not None and total is not None for busy, total in pairs):
        return usage(sum(busy for busy, _ in pairs), sum(total for _, total in pairs))
    return None


class Memory(Provider):
    identifier = "Memory"

    def __init__(self, settings):
        pass

    def sample(self):
        stamp = time()
        mem = psutil.virtual_memory()
        swap_used, swap_total = pagefiles()
        used = mem.total - mem.available
        committed, limit = commit()
        return Sample(LOCAL, self.identifier, stamp, readings(LOCAL, stamp, TOTAL, {
            "ram.util": (usage(used, mem.total), "%"), "ram.total": (mem.total, "B"),
            "ram.used": (used, "B"), "ram.available": (mem.available, "B"),
            "ram.pagefile_used": (swap_used, "B"), "ram.pagefile_total": (swap_total, "B"),
            "ram.committed": (committed, "B"), "ram.commit_limit": (limit, "B"),
        }))


class Counters(Provider):
    def __init__(self, settings):
        self.interval = settings.local_interval
        self.stamp = 0
        self.last = {}

    def measure(self, stamp, now, rows, selected, convert):
        items, devices, totals = [], [], []
        elapsed = now - self.stamp
        for key, row in rows.items():
            devices.append(Device(self.kind, key, key))
            values = convert(key, row, self.last.get(key), elapsed)
            items.extend(readings(LOCAL, stamp, key, values))
            if key in selected:
                totals.append(values)
        self.last, self.stamp = rows, now
        return Sample(LOCAL, self.identifier, stamp, tuple(items) +
                      aggregate(LOCAL, stamp, self.kind, totals), tuple(devices))


def deltas(current, previous, fields, elapsed, interval):
    return [rate(getattr(previous, key, None), getattr(current, key, None), elapsed, interval) for key in fields]


def combined(first, second):
    return first + second if first is not None and second is not None else None


def disk_metrics(read, write, reads, writes, active):
    return {"disk.read": (read, "B/s"), "disk.write": (write, "B/s"),
            "disk.total": (combined(read, write), "B/s"), "disk.read_ops": (reads, "ops/s"),
            "disk.write_ops": (writes, "ops/s"), "disk.active": (active, "%")}


def net_metrics(receive, transmit, up, rx_link, tx_link):
    link = max(rx_link or 0, tx_link or 0) or None
    rx_util = usage(receive * 8, rx_link * 1e6) if up and rx_link and receive is not None else None
    tx_util = usage(transmit * 8, tx_link * 1e6) if up and tx_link and transmit is not None else None
    return {"net.receive": (receive, "B/s"), "net.transmit": (transmit, "B/s"),
            "net.total": (combined(receive, transmit), "B/s"), "net.up": (up, "bool"),
            "net.link": (link, "Mb/s"), "net.util": (max(rx_util, tx_util) if
                                                   rx_util is not None and tx_util is not None else None, "%")}


class Disk(Counters):
    identifier = "Storage"
    kind = "disk"

    def __init__(self, settings):
        super().__init__(settings)
        self.selected = settings.disks
        self.native = Pdh({"idle": r"\PhysicalDisk(*)\% Idle Time"})

    def sample(self):
        stamp, now = time(), monotonic()
        rows = psutil.disk_io_counters(perdisk=True, nowrap=False) or {}
        rows = {key: row for key, row in rows.items() if key.lower().startswith("physicaldrive")}
        idle = self.native.collect().get("idle", {})
        idle = {key.split(" ", 1)[0]: max(0, min(100, 100 - value)) for key, value in idle.items()
                if key[0].isdigit()}

        def convert(key, row, previous, elapsed):
            values = deltas(row, previous, ("read_bytes", "write_bytes", "read_count", "write_count"),
                            elapsed, self.interval)
            active = idle.get(key.removeprefix("PhysicalDrive")) if values[0] is not None else None
            return disk_metrics(*values, active)

        return self.measure(stamp, now, rows, self.selected or rows, convert)

    def close(self):
        self.native.close()


class Network(Counters):
    identifier = "Network"
    kind = "net"

    def __init__(self, settings):
        super().__init__(settings)
        self.selected = settings.interfaces
        self.identities = {}

    def sample(self):
        stamp, now = time(), monotonic()
        rows = psutil.net_io_counters(pernic=True, nowrap=False) or {}
        stats = psutil.net_if_stats()
        native = interface_info()
        absent = (False, 0, 0, None)
        selected = self.selected or [key for key in rows if native.get(key, absent)[0]]
        identities = {key: (native.get(key, absent)[3], stats[key].isup if key in stats else None)
                      for key in rows}

        def convert(key, row, previous, elapsed):
            if self.identities.get(key) != identities[key]:
                previous = None
            values = deltas(row, previous, ("bytes_recv", "bytes_sent"), elapsed, self.interval)
            stat = stats.get(key)
            up = stat.isup if stat else None
            _, tx_link, rx_link, _ = native.get(key, absent)
            if tx_link in (0, 2**64 - 1):
                tx_link = (stat.speed * 1e6) if stat and stat.speed > 0 else 0
            if rx_link in (0, 2**64 - 1):
                rx_link = (stat.speed * 1e6) if stat and stat.speed > 0 else 0
            return net_metrics(*values, up, rx_link / 1e6 if up else None, tx_link / 1e6 if up else None)

        sample = self.measure(stamp, now, rows, selected, convert)
        self.identities = identities
        return sample


def os_name():
    build = platform.version().rsplit(".", 1)[-1]
    return f"Windows {'11' if build.isdecimal() and int(build) >= 22000 else '10'} ({build})"
