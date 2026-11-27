# Adaptive Resource Monitor
# Original developer: Sonja M Thomas
# Copyright 2010-2026 SLT Design Creations, LLC
# Licensed under the Design Creations Attribution-NonCommercial-ShareAlike License v1.0.
# See LICENSE.md for complete license terms.
# https://www.designcreations.us/

"""The Design Creations About tab and bundled project documents."""
import json
import logging
import platform
import re
import struct
import sys
import winreg
from html import escape
from pathlib import Path

from PySide6.QtCore import QRectF, QSysInfo, Qt, QUrl, qVersion
from PySide6.QtGui import QDesktopServices, QFont, QGuiApplication, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QPushButton, QStyle, QTextBrowser, QVBoxLayout, QWidget,
)

from .branding import (
    APPLICATION_IMAGE, COMPANY_LOGO, COPYRIGHT, DEVELOPER, DESCRIPTION, DONATION_URL, INSTALL_ID,
    WEBSITE, asset, document, open_issue_tracker,
)
from .software_license import LICENSE_LABEL, LicenseDialog
from .update_release import LICENSE_FILE
from .version import NAME, VERSION
from .update_ui import UpdatePanel
from .window_geometry import WindowGeometry

LOG = logging.getLogger(__name__)
ISSUE_ICON = QStyle.StandardPixmap.SP_MessageBoxWarning
DOCS = {
    "README.md": "README",
    "CHANGELOG.md": "Change Log",
    "THIRD_PARTY.md": "Third-party Notices",
}
UNINSTALL_KEY = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{INSTALL_ID}_is1"


def release_classification():
    return VERSION.partition("_")[2].capitalize() or "Stable"


def installation():
    if not getattr(sys, "frozen", False):
        return "Source checkout", document("README.md").parent
    directory = Path(sys.executable).resolve().parent
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY, 0, winreg.KEY_READ | view) as key:
                path, _ = winreg.QueryValueEx(key, "InstallLocation")
            if path and Path(path).resolve() == directory:
                return "Windows installed", directory
        except OSError:
            continue
    return "Windows portable", directory


def build_data():
    try:
        data = json.loads(document("BUILD.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def link(url, text, color):
    return f'<a style="color:{color}" href="{escape(url, quote=True)}">{escape(text)}</a>'


class BrandImage(QWidget):
    def __init__(self, picture, description, size=(138, 116)):
        super().__init__()
        self.setFixedSize(*size)
        self.setAccessibleName(description)
        self.picture = picture

    def paintEvent(self, _event):
        if self.picture.isNull():
            return
        size = self.picture.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        destination = QRectF((self.width() - size.width()) / 2, (self.height() - size.height()) / 2,
                             size.width(), size.height())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(destination, self.picture, QRectF(self.picture.rect()))


class AboutPage(QWidget):
    def __init__(self, data_root):
        super().__init__()
        self.data_root = data_root
        self.setObjectName("armAbout")
        self.setAccessibleName(f"About {NAME}")
        self.documents = {name: label for name, label in DOCS.items() if document(name).is_file()}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 9, 10, 10)
        layout.setSpacing(9)
        header = QHBoxLayout()
        header.setSpacing(12)
        self.app_image = BrandImage(QPixmap(str(asset(APPLICATION_IMAGE))), f"{NAME} application image")
        self.company_image = BrandImage(QPixmap(str(asset(COMPANY_LOGO))), "Design Creations logo")
        header.addWidget(self.app_image)

        center = Qt.AlignmentFlag.AlignCenter
        identity = QVBoxLayout()
        identity.setSpacing(4)
        identity.addStretch()
        self.title = QLabel(NAME, alignment=center)
        self.title.setWordWrap(True)
        self.title.setFont(QFont("Georgia", 26, QFont.Weight.Bold))
        identity.addWidget(self.title)
        attribution = QLabel(f"{DEVELOPER} · {COPYRIGHT}", alignment=center)
        attribution.setWordWrap(True)
        identity.addWidget(attribution)
        self.website = QLabel(alignment=center)
        self.website.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.website.linkActivated.connect(self.open_link)
        identity.addWidget(self.website)
        identity.addStretch()
        header.addLayout(identity, 1)
        header.addWidget(self.company_image)
        layout.addLayout(header)

        information = QGroupBox("Application Information")
        details = QFormLayout(information)
        details.setHorizontalSpacing(14)
        description = QLabel(DESCRIPTION)
        description.setWordWrap(True)
        details.addRow(description)
        self.version = QLabel(VERSION)
        details.addRow("Installed version", self.version)
        details.addRow("Release classification", QLabel(release_classification()))
        bundled = document(LICENSE_FILE).is_file()
        license_label = QLabel(LICENSE_LABEL if bundled else "License file unavailable",
                               textFormat=Qt.TextFormat.PlainText)
        details.addRow("Software license", license_label)
        details.addRow("Distribution model", QLabel("Donationware"))
        view = QPushButton("Application Details")
        view.clicked.connect(self.show_details)
        self.view_license = QPushButton("View License")
        self.view_license.setEnabled(bundled)
        self.view_license.clicked.connect(self.show_license)
        buttons = QHBoxLayout()
        buttons.addWidget(view)
        buttons.addWidget(self.view_license)
        donate = QPushButton("Donate")
        donate.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(DONATION_URL)))
        buttons.addWidget(donate)
        self.report_issue = QPushButton(self.style().standardIcon(ISSUE_ICON), "Report Issue")
        self.report_issue.clicked.connect(open_issue_tracker)
        buttons.addWidget(self.report_issue)
        buttons.addStretch()
        details.addRow(buttons)
        donationware = QLabel(
            "Adaptive Resource Monitor is Donationware. If you find this application useful, "
            "voluntary donations are appreciated and help support continued development. "
            "Donations are not required and do not provide additional functionality, "
            "preferential support or development priority."
        )
        donationware.setWordWrap(True)
        details.addRow(donationware)
        layout.addWidget(information)

        self.updates = UpdatePanel(data_root, installation()[0])
        layout.addWidget(self.updates)

        self.links = QLabel(alignment=center)
        self.links.setWordWrap(True)
        self.links.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.links.linkActivated.connect(self.open_link)
        layout.addWidget(self.links)

        self.document_group = QGroupBox("Change Log")
        document_layout = QVBoxLayout(self.document_group)
        self.browser = QTextBrowser()
        self.browser.setAccessibleName("Project documentation")
        self.browser.setOpenLinks(False)
        self.browser.anchorClicked.connect(lambda url: self.open_link(url.toString()))
        self.browser.setMinimumHeight(135)
        document_layout.addWidget(self.browser)
        layout.addWidget(self.document_group, 1)
        self.show_document("CHANGELOG.md")

    def theme(self, colors):
        self.setStyleSheet(f"""
            QWidget#armAbout {{ background: {colors.background}; }}
            QWidget#armAbout QLabel {{ color: {colors.text}; }}
            QWidget#armAbout QGroupBox {{
                color: {colors.accent}; border: 1px solid {colors.border};
                border-radius: 4px; margin-top: 8px; padding: 7px 6px 5px;
            }}
            QWidget#armAbout QGroupBox::title {{
                subcontrol-origin: margin; left: 8px; padding: 0 4px;
            }}
            QWidget#armAbout QTextBrowser {{
                background: {colors.panel}; color: {colors.text};
                border: 1px solid {colors.border}; selection-background-color: {colors.highlight};
            }}
            QWidget#armAbout QPushButton {{
                background: {colors.panel}; color: {colors.text}; padding: 4px 10px;
                border: 1px solid {colors.border}; border-radius: 3px;
            }}
            QWidget#armAbout QPushButton:hover, QWidget#armAbout QPushButton:focus {{
                background: {colors.highlight}; border-color: {colors.accent};
            }}
        """)
        self.website.setText(link(WEBSITE, "www.designcreations.us", colors.accent))
        items = [link(name, name if name in ("README.md", "CHANGELOG.md") else label, colors.accent)
                 for name, label in self.documents.items()]
        self.links.setText(" | ".join(items))

    def show_document(self, name):
        if name not in self.documents:
            return False
        path = document(name)
        self.document_group.setTitle(self.documents[name])
        try:
            markdown = path.read_text(encoding="utf-8")
            if name == "README.md":
                # The public README includes HTML layout and images for Gitea.
                # Keep its Markdown prose and tables readable in Qt's offline viewer.
                markdown = re.sub(r"(?ms)^<(div|p|table)\b.*?</\1>[ \t]*\n", "", markdown)
                markdown = re.sub(r"(?m)^(?:</?details>|<summary>.*</summary>|<img\b[^>\n]*>|<!--.*-->)[ \t]*\n",
                                  "", markdown)
            self.browser.setMarkdown(markdown)
        except (OSError, UnicodeError) as exc:
            LOG.warning("Unable to read About document %s: %s", name, exc)
            self.browser.setPlainText(f"Unable to open {name}.")
            return False
        self.browser.verticalScrollBar().setValue(0)
        return True

    def open_changelog(self):
        if self.show_document("CHANGELOG.md"):
            self.updates.dismiss_success_notice()
            self.browser.setFocus()

    def show_license(self):
        try:
            markdown = document(LICENSE_FILE).read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            LOG.warning("Unable to read the bundled software license: %s", exc)
            return
        dialog = LicenseDialog(self, self.data_root, markdown)
        dialog.exec()
        dialog.deleteLater()

    def open_link(self, target):
        if target == "CHANGELOG.md":
            self.open_changelog()
        elif target in self.documents:
            self.show_document(target)
        elif QUrl(target).scheme() == "https":
            QDesktopServices.openUrl(QUrl(target))

    def copy_application_information(self):
        kind, _ = installation()
        information = (
            ("Application", NAME),
            ("Version", VERSION),
            ("Release classification", release_classification()),
            ("Operating system", f"{QSysInfo.prettyProductName()} ({QSysInfo.kernelVersion()})"),
            ("Processor architecture", QSysInfo.currentCpuArchitecture()),
            ("Distribution", kind),
            ("Framework", f"Qt {qVersion()}"),
        )
        QGuiApplication.clipboard().setText("\n".join(f"{label}: {value}" for label, value in information))

    def show_details(self):
        kind, directory = installation()
        build = build_data()
        revision = build.get("source_revision") or "Unavailable"
        if build.get("source_modified"):
            revision += " (including local changes)"
        rows = (
            ("Application", NAME), ("Version", VERSION), ("Release classification", release_classification()),
            ("Build time (UTC)", build.get("built_at") or "Source checkout"),
            ("Source revision", revision),
            ("Platform", f"{platform.system()} · {platform.machine()} · {struct.calcsize('P') * 8}-bit"),
            ("Installation type", kind), ("Installation location", str(directory)),
            ("Application data", str(self.data_root)),
        )
        dialog = QDialog(self)
        dialog.setWindowTitle("Application Details")
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        for name, value in rows:
            label = QLabel(str(value))
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow(name, label)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        copy = buttons.addButton("Copy Application Information", QDialogButtonBox.ButtonRole.ActionRole)
        copy.clicked.connect(self.copy_application_information)
        layout.addWidget(buttons)
        dialog.resize(620, dialog.sizeHint().height())
        dialog.window_geometry = WindowGeometry(dialog, self.data_root / "application-details-window.bin")
        dialog.exec()
