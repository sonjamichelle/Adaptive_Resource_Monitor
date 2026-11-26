import json
import logging
import math
import os
from pathlib import Path
from dataclasses import asdict, dataclass, field, fields
from uuid import uuid4

from .model import ALL, DISK_MODES, INTERVALS, LOCAL, RANGES, RESOURCES

LOG = logging.getLogger(__name__)
APP_DIR = "Adaptive Resource Monitor"
STATIC_TRAY_MODE = "Application Icon"
TRAY_MODES = ("Overlay", "Stacked", "Composite", STATIC_TRAY_MODE)


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
        if not isinstance(cfg.identifier, str) or not cfg.identifier or cfg.identifier in (LOCAL, ALL):
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
    tray_mode: str = "Local"
    tray_remote: str = ""
    resources: list[str] = field(default_factory=lambda: list(RESOURCES))
    colors: dict[str, str] = field(default_factory=lambda: {r: info[1] for r, info in RESOURCES.items()})
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
            ("tray_mode", ("Local", "Selected remote", "Separate", "Consolidated"), "Local"),
            ("disk_mode", DISK_MODES, "disk.total"),
            ("log_level", ("DEBUG", "INFO", "WARNING", "ERROR"), "INFO"),
        ):
            value = getattr(cfg, key)
            if not isinstance(value, str) or value not in choices:
                setattr(cfg, key, fallback)
        for key in ("default_machine", "tray_remote", "history_file"):
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
        cfg.background = valid_color(cfg.background, "#171a22")
        cfg.targets = [Target.from_dict(item) for item in cfg.targets if isinstance(item, dict)] if isinstance(cfg.targets, list) else []
        cfg.targets = list({target.identifier: target for target in cfg.targets}.values())
        return cfg


def valid_color(value, default):
    if isinstance(value, str) and len(value) == 7 and value.startswith("#"):
        if all(char in "0123456789abcdef" for char in value[1:].lower()):
            return value
    return default


class ConfigStore:
    def __init__(self, path):
        self.path = Path(path)

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
