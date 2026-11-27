# Adaptive Resource Monitor
# Original developer: Sonja M Thomas
# Copyright 2010-2026 SLT Design Creations, LLC
# Licensed under the Design Creations Attribution-NonCommercial-ShareAlike License v1.0.
# See LICENSE.md for complete license terms.
# https://www.designcreations.us/

import logging
import re
from collections import Counter, defaultdict
from time import perf_counter as monotonic, time

from . import Provider
from .native import Pdh, adapter_identity, adapters
from ..model import LOCAL, Device, Sample, aggregate, readings, usage

LOG = logging.getLogger(__name__)
LUID = re.compile(r"(luid_0x[0-9a-f]+_0x[0-9a-f]+)(?:_phys_(\d+))?", re.I)
ENGINE = re.compile(r"_eng_(\d+)_engtype_(.+?)(?:#\d+)?$", re.I)
GPU_UNITS = {
    "util": "%", "vram_used": "B", "vram_total": "B", "vram_free": "B", "vram_pct": "%",
    "shared_used": "B", "shared_total": "B", "shared_pct": "%",
    "temperature": "°C", "clock": "MHz", "memory_clock": "MHz", "power": "W",
    "power_limit": "W", "fan": "%", "encode": "%", "decode": "%", "compute": "%",
}


def gpu_metrics(values):
    for key, capacity, used in (("vram", "vram_total", "vram_used"),
                                ("shared", "shared_total", "shared_used")):
        values[f"{key}_pct"] = usage(values.get(used), values.get(capacity))
    if values.get("vram_used") is not None and values.get("vram_total"):
        values.setdefault("vram_free", max(0, values["vram_total"] - values["vram_used"]))
    return {f"gpu.{key}": (values.get(key), unit) for key, unit in GPU_UNITS.items()}


def engine_usage(rows):
    engines = defaultdict(lambda: defaultdict(float))
    for label, value in rows.items():
        adapter, engine = LUID.search(label), ENGINE.search(label)
        if adapter and engine:
            engines[adapter[1].lower()][(adapter[2], engine[1], engine[2].lower())] += value
    result = {}
    for identifier, nodes in engines.items():
        values = {"util": min(100, max(nodes.values()))}
        for key, tokens in {"encode": ("videoencode",), "decode": ("videodecode",),
                            "compute": ("compute", "cuda")}.items():
            values[key] = max((min(100, value) for node, value in nodes.items()
                               if any(token in node[-1] for token in tokens)), default=None)
        result[identifier] = values
    return result


def memory_usage(rows):
    values = defaultdict(float)
    for label, value in rows.items():
        adapter = LUID.search(label)
        if adapter:
            values[adapter[1].lower()] += value
    return values


class Nvml:
    def __init__(self):
        self.api = None
        self.devices = []
        try:
            import pynvml
            pynvml.nvmlInit()
            self.api = pynvml
            for index in range(pynvml.nvmlDeviceGetCount()):
                handle = self.get("HandleByIndex", index)
                if handle is None:
                    continue
                name, pci, identifier = (self.get(key, handle) for key in ("Name", "PciInfo", "UUID"))
                if name and pci and identifier:
                    if isinstance(name, bytes):
                        name = name.decode("utf-8", "replace")
                    if isinstance(identifier, bytes):
                        identifier = identifier.decode("ascii", "replace")
                    self.devices.append((str(identifier), name, pci.pciDeviceId >> 16,
                                         (pci.bus, pci.device), handle))
            LOG.info("NVML found %d GPU(s)", len(self.devices))
        except (ImportError, OSError):
            LOG.info("NVML unavailable")
        except Exception as exc:
            LOG.info("NVML unavailable (%s)", type(exc).__name__)

    def get(self, key, *args):
        try:
            return getattr(self.api, "nvmlDeviceGet" + key)(*args)
        except (self.api.NVMLError, AttributeError):
            return None

    def metrics(self, handle):
        n = self.api
        sensors = {}
        utilization = self.get("UtilizationRates", handle)
        if utilization is not None:
            sensors["util"] = utilization.gpu
        mem = self.get("MemoryInfo", handle)
        if mem is not None:
            for attr in ("total", "used", "free"):
                sensors[f"vram_{attr}"] = getattr(mem, attr)
        for key, command, args, factor in (
            ("temperature", "Temperature", (n.NVML_TEMPERATURE_GPU,), 1),
            ("clock", "ClockInfo", (n.NVML_CLOCK_GRAPHICS,), 1),
            ("memory_clock", "ClockInfo", (n.NVML_CLOCK_MEM,), 1),
            ("power", "PowerUsage", (), .001), ("power_limit", "PowerManagementLimit", (), .001),
            ("fan", "FanSpeed", (), 1), ("encode", "EncoderUtilization", (), 1),
            ("decode", "DecoderUtilization", (), 1),
        ):
            value = self.get(command, handle, *args)
            if value is not None:
                sensors[key] = value[0] * factor if isinstance(value, (tuple, list)) else value * factor
        return sensors

    def close(self):
        if self.api:
            try:
                self.api.nvmlShutdown()
            except self.api.NVMLError as exc:
                LOG.debug("NVML shutdown returned %s", type(exc).__name__)


class WddmGpu(Provider):
    identifier = "GPU"

    def __init__(self, settings):
        self.selected = settings.gpus
        self.interval = settings.local_interval
        self.last_tick = 0
        self.nvml = Nvml()
        try:
            self.devices = adapters()
        except OSError:
            LOG.warning("DXGI hardware enumeration failed", exc_info=True)
            self.devices = []
        self.counters = Pdh({
            "engine": r"\GPU Engine(*)\Utilization Percentage",
            "dedicated": r"\GPU Adapter Memory(*)\Dedicated Usage",
            "shared": r"\GPU Adapter Memory(*)\Shared Usage",
        })
        groups = {}
        self.locations = {}
        identities = [(adapter, *adapter_identity(adapter)) for adapter in self.devices]
        physical = {(a.vendor, a.device, a.subsystem) for a, location, _ in identities if location is not None}
        for adapter, location, flags in identities:
            if location is None and (adapter.vendor, adapter.device, adapter.subsystem) in physical:
                LOG.info("Skipping non-PCI DXGI alias %s (%s, type %s)", adapter.identifier, adapter.name, flags)
                continue
            identifier = (f"pci:{adapter.vendor:04x}:{location[0]:02x}:{location[1]:02x}.{location[2]}"
                          if location is not None else adapter.identifier)
            groups.setdefault(identifier, []).append(adapter)
            self.locations[identifier] = location
            LOG.info("DXGI adapter %s %s (%s)", adapter.identifier, adapter.name, identifier)
        self.groups = groups
        nvml_counts = Counter(device for _, _, device, _, _ in self.nvml.devices)
        self.matches = {}
        for identifier, name, device, pci, handle in self.nvml.devices:
            candidates = [key for key, group in groups.items()
                          if group[0].vendor == 0x10de and group[0].device == device]
            matches = [key for key in candidates
                       if self.locations[key] is not None and self.locations[key][:2] == pci]
            if len(matches) == 1:
                self.matches[matches[0]] = handle
            elif len(candidates) == 1 and nvml_counts[device] == 1:
                self.matches[candidates[0]] = handle
            elif not matches and not any(a.vendor == 0x10de for a in self.devices):
                self.matches[identifier] = (name, handle)
            else:
                LOG.info("NVML adapter identity unresolved for %s; using WDDM for that adapter", name)

    def sample(self):
        stamp, tick = time(), monotonic()
        baseline = not 0 < tick - self.last_tick <= max(self.interval * 3, 2)
        self.last_tick = tick
        data = self.counters.collect()
        engines = engine_usage(data.get("engine", {})) if not baseline else {}
        dedicated = memory_usage(data.get("dedicated", {}))
        shared = memory_usage(data.get("shared", {}))
        items, devices, totals = [], [], []

        def collect(identifier, name, metrics):
            devices.append(Device("gpu", identifier, name))
            values = gpu_metrics(metrics)
            items.extend(readings(LOCAL, stamp, identifier, values))
            if not self.selected or identifier in self.selected:
                totals.append(values)

        for identifier, group in self.groups.items():
            adapter = group[0]
            aliases = [item.identifier for item in group]
            # Driver aliases refer to one PCI function. Take the largest reported
            # adapter reading instead of adding capacity or mirrored counters twice.
            metrics = {engine: max((engines[key][engine] for key in aliases
                                    if key in engines and engines[key].get(engine) is not None),
                                   default=None)
                       for engine in ("util", "encode", "decode", "compute")}
            if adapter.dedicated:
                metrics["vram_used"] = max((dedicated[key] for key in aliases if key in dedicated),
                                           default=None)
            metrics["vram_total"] = adapter.dedicated or None
            metrics["shared_total"] = adapter.shared or None
            metrics["shared_used"] = max((shared[key] for key in aliases if key in shared), default=None)
            if identifier in self.matches:
                metrics.update(self.nvml.metrics(self.matches[identifier]))
            collect(identifier, adapter.name, metrics)

        for identifier, match in self.matches.items():
            if isinstance(match, tuple):
                name, handle = match
                collect(identifier, name, self.nvml.metrics(handle))
        return Sample(LOCAL, self.identifier, stamp, tuple(items) + aggregate(LOCAL, stamp, "gpu", totals),
                      tuple(devices))

    def close(self):
        self.counters.close()
        self.nvml.close()
