"""Shared Design Creations identity and asset locations."""
from dataclasses import dataclass
from pathlib import Path
import sys

DEVELOPER = "Sonja M Thomas"
PUBLISHER = "SLT Design Creations, LLC"
COPYRIGHT = f"Copyright 2010-2026 {PUBLISHER}"
WEBSITE = "https://www.designcreations.us/"
SUPPORT_URL = "https://www.designcreations.us/contact/index.php"
APP_MODEL_ID = "SLTDesignCreations.AdaptiveResourceMonitor"
INSTALL_ID = "{FB4FA82E-8715-4AC8-BD23-48E33E998D1B}"
DESCRIPTION = (
    "Adaptive Resource Monitor is a lightweight, real-time system resource monitoring "
    "application providing combined system tray visualization, historical resource graphs, "
    "and centralized monitoring of local and remote computers."
)

APPLICATION_IMAGE = "ARM_Application_Image.png"
APPLICATION_LOGO = "ARM_Emblem.png"
APPLICATION_ICON = "ARM_Application.ico"
COMPANY_LOGO = "dc-design-creations.png"
BUNDLED_ASSETS = (APPLICATION_IMAGE, APPLICATION_LOGO, APPLICATION_ICON, COMPANY_LOGO)
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
SOURCE_ROOT = Path(__file__).resolve().parent.parent


def asset(name):
    bundle = getattr(sys, "_MEIPASS", None)
    return (Path(bundle) / "branding" if bundle else SOURCE_ROOT) / name


def document(name):
    if getattr(sys, "frozen", False):
        directory = Path(sys.executable).resolve().parent
        if name == "THIRD_PARTY.md":
            return directory / "Third-party notices" / "README.md"
        return directory / name
    if name == "THIRD_PARTY.md":
        return SOURCE_ROOT / "packaging" / name
    return SOURCE_ROOT / name


def application_icon():
    from PySide6.QtGui import QIcon

    icon = QIcon(str(asset(APPLICATION_ICON)))
    return icon if not icon.isNull() else QIcon(str(asset(APPLICATION_LOGO)))


def set_windows_identity():
    import ctypes as ct

    assign = ct.WinDLL("shell32").SetCurrentProcessExplicitAppUserModelID
    assign.argtypes = [ct.c_wchar_p]
    assign.restype = ct.c_long
    return assign(APP_MODEL_ID)


@dataclass(frozen=True)
class Colors:
    background: str
    panel: str
    text: str
    muted: str
    border: str
    accent: str
    highlight: str


DARK = Colors("#1a1612", "#211a14", "#f1e7d9", "#d5c1a8", "#704b28", "#ffc25f", "#49301a")
LIGHT = Colors("#fbf3e6", "#fff9ee", "#302116", "#66503d", "#b78a5a", "#803f08", "#ebd1ab")
