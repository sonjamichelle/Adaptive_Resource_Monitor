"""Presentation and persisted outcomes for the shared updater."""
from enum import Enum, auto
import json
from pathlib import Path
import re

from .update_client import write_atomic
from .version import VERSION, version_key


class Phase(Enum):
    CURRENT = auto()
    CHECKING = auto()
    AVAILABLE = auto()
    DOWNLOADING = auto()
    PAUSED = auto()
    READY = auto()
    INSTALLING = auto()
    SUCCESS = auto()
    FAILED = auto()
    RESTORED = auto()


def notice(phase, version, ready=False):
    if not version:
        return ""
    if phase is Phase.SUCCESS:
        return f"Adaptive Resource Monitor successfully updated to {version}."
    if phase is not Phase.INSTALLING:
        title = "Update Ready to Install" if ready else "Update Available"
        return f"{title}: {version}"
    return ""


def read_json(path, default=None):
    try:
        return json.loads(path.read_bytes())
    except (OSError, ValueError):
        return default


def notify_once(path, key, enabled):
    if not enabled:
        return False
    cached = read_json(path, [])
    keys = cached if isinstance(cached, list) else []
    if key in keys:
        return False
    write_atomic(path, json.dumps([*keys, key]).encode())
    return True


def result_for(directory, running=VERSION):
    plan = read_json(directory / "plan.json")
    status = read_json(directory / "status.json")
    if not isinstance(plan, dict) or not isinstance(status, dict):
        return None
    try:
        version_key(plan["new"])
        version_key(plan["old"])
    except (KeyError, ValueError, TypeError):
        return None
    state, message = status.get("state"), status.get("message")
    if not isinstance(message, str):
        return None
    if state == "complete" and plan["new"] == running:
        ready = read_json(directory / "ready.json", {})
        if (isinstance(ready, dict) and ready.get("version") == running
                and type(ready.get("pid")) is int and ready["pid"] > 0):
            return Phase.SUCCESS, notice(Phase.SUCCESS, running)
    if state in ("rolled_back", "failed") and plan["old"] == running:
        return (Phase.RESTORED if state == "rolled_back" else Phase.FAILED), message
    return None


def transaction_from_ack(root, value):
    if value:
        path = Path(value).resolve()
        if (path.name == "ready.json" and re.fullmatch(r"[0-9a-f]{32}", path.parent.name)
                and path.parent.parent == (root / "updates" / "transactions").resolve()):
            return path.parent
    return None
