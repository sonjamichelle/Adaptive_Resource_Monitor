# Adaptive Resource Monitor
# Original developer: Sonja M Thomas
# Copyright 2010-2026 SLT Design Creations, LLC
# Licensed under the Design Creations Attribution-NonCommercial-ShareAlike License v1.0.
# See LICENSE.md for complete license terms.
# https://www.designcreations.us/

import json
import logging
import math
import os
from pathlib import Path
from dataclasses import asdict, dataclass, field, fields
from tempfile import NamedTemporaryFile
from uuid import uuid4

from .model import ALL, DISK_MODES, INTERVALS, LOCAL, NETWORK, RANGES, RESOURCES

LOG = logging.getLogger(__name__)
APP_DIR = "Adaptive Resource Monitor"
STATIC_TRAY_MODE = "Application Icon"
TRAY_MODES = ("Overlay", "Stacked", "Composite", STATIC_TRAY_MODE)
LEGACY_PEAK = "@peak"


def data_path():
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / APP_DIR


def existing_values(cls, source):
    return {f.name: source[f.name] for f in fields(cls) if f.name in source}


def strings(value):
    return list(dict.fromkeys(x for x in value if isinstance(x, str))) if isinstance(value, list) else []


def number(value, default, lower, upper, integer=False):
    if isinstance(value, (int, float)) and math.isfinite(value):
        return (int if integer else float)(min(upper, max(lower, value)))
    return default


@dataclass(slots=True)
class Target:
    identifier: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    host: str = ""
    os_type: str = "Linux"
    method: str = "SSH"
    port: int = 22
    username: str = ""
    auth: str = "Password"
    key_file: str = ""
    credential: str = ""
    enabled: bool = True
    interval: float = 2
    reconnect: bool = True
    timeout: int = 6
    resources: list[str] = field(default_factory=lambda: list(RESOURCES))
    gpus: list[str] = field(default_factory=list)
    disks: list[str] = field(default_factory=list)
    interfaces: list[str] = field(default_factory=list)
    tray: bool = True

    @classmethod
    def from_dict(cls, source):
        cfg = cls(**existing_values(cls, source))
        if not isinstance(cfg.identifier, str) or not cfg.identifier or cfg.identifier in (LOCAL, ALL, LEGACY_PEAK):
            cfg.identifier = str(uuid4())
        for key in ("name", "host", "username", "key_file", "credential"):
            if not isinstance(getattr(cfg, key), str):
                setattr(cfg, key, "")
        cfg.os_type = cfg.os_type if cfg.os_type in ("Linux", "Windows") else "Linux"
        cfg.method = "SSH" if cfg.os_type == "Linux" else "Planned"
        cfg.auth = cfg.auth if cfg.auth in ("Password", "Private key") else "Password"
        cfg.port = number(cfg.port, 22, 1, 65535, True)
        cfg.timeout = number(cfg.timeout, 6, 2, 30, True)
        cfg.interval = cfg.interval if cfg.interval in INTERVALS else 2
        for key in ("resources", "gpus", "disks", "interfaces"):
            setattr(cfg, key, strings(getattr(cfg, key)))
        return cfg


@dataclass(slots=True)
class Settings:
    minimized: bool = True
    theme: str = "System"
    default_machine: str = LOCAL
    mode: str = "Overlay"
    tray_machine: str = LOCAL
    separate_tray_icons: bool = False
    resources: list[str] = field(default_factory=lambda: list(RESOURCES))
    colors: dict[str, str] = field(default_factory=lambda: {r: info[1] for r, info in RESOURCES.items()})
    network_colors: dict[str, str] = field(default_factory=lambda: {key: value[1] for key, value in NETWORK.items()})
    background: str = "#171a22"
    transparent: bool = False
    tray_refresh: float = 1
    tray_range: int = 60
    disk_mode: str = "disk.total"
    disk_scale: float = 0
    net_scale: float = 0
    hover_delay: int = 350
    dismiss_delay: int = 500
    popup_width: int = 500
    popup_height: int = 330
    popup_columns: int = 2
    hover_range: int = 60
    hover_machine: str = ""
    hover_resources: list[str] = field(default_factory=lambda: list(RESOURCES))
    local_interval: float = 1
    remote_interval: float = 2
    gpus: list[str] = field(default_factory=list)
    disks: list[str] = field(default_factory=list)
    interfaces: list[str] = field(default_factory=list)
    connection_timeout: int = 6
    reconnect: bool = True
    persistent: bool = False
    retention_days: int = 7
    max_history_mb: int = 128
    history_file: str = ""
    log_level: str = "INFO"
    update_startup: bool = False
    update_interval: int = 0
    update_notifications: bool = True
    targets: list[Target] = field(default_factory=list)

    @classmethod
    def from_dict(cls, source):
        cfg = cls(**existing_values(cls, source))
        for key in ("tray_refresh", "local_interval", "remote_interval"):
            if getattr(cfg, key) not in INTERVALS:
                setattr(cfg, key, 1)
        for key in ("tray_range", "hover_range"):
            if not isinstance(getattr(cfg, key), int) or getattr(cfg, key) not in RANGES:
                setattr(cfg, key, 60)
        for key, choices, fallback in (
            ("theme", ("System", "Light", "Dark"), "System"),
            ("mode", TRAY_MODES, "Overlay"),
            ("disk_mode", DISK_MODES, "disk.total"),
            ("log_level", ("DEBUG", "INFO", "WARNING", "ERROR"), "INFO"),
        ):
            value = getattr(cfg, key)
            if not isinstance(value, str) or value not in choices:
                setattr(cfg, key, fallback)
        for key in ("default_machine", "history_file", "hover_machine"):
            if not isinstance(getattr(cfg, key), str):
                setattr(cfg, key, getattr(cls(), key))
        for key in ("resources", "hover_resources", "gpus", "disks", "interfaces"):
            setattr(cfg, key, strings(getattr(cfg, key)))
        for key, default, lower, upper in (
            ("popup_width", 500, 300, 1800), ("popup_height", 330, 210, 1200),
            ("popup_columns", 2, 1, 3), ("hover_delay", 350, 0, 5000),
            ("dismiss_delay", 500, 100, 10000), ("retention_days", 7, 1, 365),
            ("max_history_mb", 128, 16, 4096), ("connection_timeout", 6, 2, 30),
        ):
            setattr(cfg, key, number(getattr(cfg, key), default, lower, upper, True))
        for key in ("disk_scale", "net_scale"):
            setattr(cfg, key, number(getattr(cfg, key), 0, 0, 2**50))
        colors = cfg.colors if isinstance(cfg.colors, dict) else {}
        cfg.colors = {r: valid_color(colors.get(r), info[1]) for r, info in RESOURCES.items()}
        network_colors = cfg.network_colors if isinstance(cfg.network_colors, dict) else {}
        cfg.network_colors = {key: valid_color(network_colors.get(key), value[1])
                              for key, value in NETWORK.items()}
        cfg.background = valid_color(cfg.background, "#171a22")
        if not isinstance(cfg.update_startup, bool):
            cfg.update_startup = False
        if type(cfg.update_interval) is not int or cfg.update_interval not in (0, 4, 12, 24, 168):
            cfg.update_interval = 0
        if not isinstance(cfg.update_notifications, bool):
            cfg.update_notifications = True
        cfg.targets = [Target.from_dict(item) for item in cfg.targets if isinstance(item, dict)] if isinstance(cfg.targets, list) else []
        cfg.targets = list({target.identifier: target for target in cfg.targets}.values())
        legacy_tray = source.get("tray_mode")
        if "tray_machine" not in source and legacy_tray == "Selected remote":
            cfg.tray_machine = source.get("tray_remote")
        if not isinstance(cfg.tray_machine, str) or cfg.tray_machine not in machine_ids(cfg):
            cfg.tray_machine = LOCAL
        if "separate_tray_icons" not in source:
            cfg.separate_tray_icons = legacy_tray == "Separate"
        elif not isinstance(cfg.separate_tray_icons, bool):
            cfg.separate_tray_icons = False
        if cfg.default_machine == LEGACY_PEAK:
            cfg.default_machine = ALL
        if cfg.hover_machine == LEGACY_PEAK:
            cfg.hover_machine = ALL
        if cfg.hover_machine not in monitor_choices(cfg):
            cfg.hover_machine = ""
        # The old consolidated setting selected the all-machine view implicitly
        # when neither a saved monitor nor an explicit non-local default existed.
        if legacy_tray == "Consolidated" and not cfg.hover_machine and cfg.default_machine == LOCAL:
            cfg.hover_machine = ALL
        return cfg


def machine_ids(settings):
    return {LOCAL, *(target.identifier for target in settings.targets)}


def monitor_choices(settings):
    return machine_ids(settings) | {ALL}


@dataclass(frozen=True, slots=True)
class MachineDisplay:
    order: tuple[str, ...]
    selected: tuple[str, ...]
    select_new: bool = False

    @staticmethod
    def eligible(settings):
        return {LOCAL, *(target.identifier for target in settings.targets if target.enabled)}

    @classmethod
    def from_legacy(cls, settings):
        order = (LOCAL, *(target.identifier for target in settings.targets))
        choice = next((item for item in (settings.hover_machine, settings.default_machine)
                       if item in monitor_choices(settings)), LOCAL)
        return cls(order, order if choice == ALL else (choice,)).with_targets(settings)

    def visible(self, settings):
        eligible = self.eligible(settings)
        return tuple(machine for machine in self.order if machine in eligible and machine in self.selected)

    def with_targets(self, settings):
        configured = (LOCAL, *(target.identifier for target in settings.targets))
        prior = tuple(machine for machine in self.order if machine in configured)
        added = tuple(machine for machine in configured if machine not in prior)
        order = prior + added
        checked = set(self.selected) | (set(added) if self.select_new else set())
        return self.with_selection(settings, checked, order)

    def with_selection(self, settings, checked, order=None):
        order = self.order if order is None else order
        return MachineDisplay(order, tuple(machine for machine in order if machine in checked),
                              self.eligible(settings).issubset(checked))

    def move(self, settings, shown, source, index):
        # Reorder only the visible slots. Hidden and disabled machines retain their positions.
        moved = list(shown)
        moved.remove(source)
        moved.insert(index, source)
        remaining = iter(moved)
        order = tuple(next(remaining) if machine in shown else machine for machine in self.order)
        return self.with_selection(settings, set(self.selected), order)


def valid_color(value, default):
    if isinstance(value, str) and len(value) == 7 and value.startswith("#"):
        if all(char in "0123456789abcdef" for char in value[1:].lower()):
            return value
    return default


class ConfigStore:
    def __init__(self, path):
        self.path = Path(path)
        self.display_path = self.path.with_name("machine-display.json")

    def load(self):
        if not self.path.is_file():
            return Settings()
        try:
            source = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(source, dict):
                return Settings.from_dict(source)
        except (ValueError, OSError):
            LOG.warning("Could not load settings")
        return Settings()

    def save(self, settings):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        try:
            temporary.write_text(json.dumps(asdict(settings), indent=2) + "\n", encoding="utf-8")
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def load_display(self, settings):
        try:
            data = json.loads(self.display_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                saved = MachineDisplay(tuple(strings(data.get("order"))),
                                       tuple(strings(data.get("selected"))), data.get("select_new") is True)
                return saved.with_targets(settings)
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            LOG.warning("Could not load machine display preferences", exc_info=True)
        return MachineDisplay.from_legacy(settings)

    def save_display(self, display):
        # Earlier releases can still save settings.json after an update rollback.
        # Keep these preferences in their own atomic file under the same settings root.
        path = self.display_path
        path.parent.mkdir(parents=True, exist_ok=True)
        stream = NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", suffix=".tmp", delete=False)
        temporary = Path(stream.name)
        try:
            with stream:
                stream.write((json.dumps(asdict(display), indent=2) + "\n").encode("utf-8"))
                stream.flush()
                os.fsync(stream.fileno())
            replace_durable(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def replace_durable(temporary, path):
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        move = ctypes.WinDLL("kernel32", use_last_error=True).MoveFileExW
        move.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD)
        move.restype = wintypes.BOOL
        replace_existing, write_through = 0x1, 0x8
        if not move(str(temporary), str(path), replace_existing | write_through):
            raise ctypes.WinError(ctypes.get_last_error())
        return
    temporary.replace(path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
