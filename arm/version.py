# Adaptive Resource Monitor
# Original developer: Sonja M Thomas
# Copyright 2010-2026 SLT Design Creations, LLC
# Licensed under the Design Creations Attribution-NonCommercial-ShareAlike License v1.0.
# See LICENSE.md for complete license terms.
# https://www.designcreations.us/

import re
import sys
from pathlib import Path


VERSION_PATTERN = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)_(alpha|beta|rc|stable)")
CHANNELS = ("alpha", "beta", "rc", "stable")


def version_key(value):
    match = VERSION_PATTERN.fullmatch(value) if isinstance(value, str) else None
    if not match:
        raise ValueError("Invalid application version")
    numbers = tuple(map(int, match.groups()[:4]))
    if max(numbers) > 65535:
        raise ValueError("Application version exceeds Windows version resource limits")
    return (*numbers, CHANNELS.index(match[5]))


def read_version(path):
    value = Path(path).read_text(encoding="utf-8").rstrip("\n")
    version_key(value)
    return value


ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
VERSION = read_version(ROOT / "VERSION.md")
NAME = "Adaptive Resource Monitor"
