# Adaptive Resource Monitor
# Original developer: Sonja M Thomas
# Copyright 2010-2026 SLT Design Creations, LLC
# Licensed under the Design Creations Attribution-NonCommercial-ShareAlike License v1.0.
# See LICENSE.md for complete license terms.
# https://www.designcreations.us/

"""Offline display and review of the application's software license."""
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout
from PySide6.QtGui import QDesktopServices

from .window_geometry import WindowGeometry

LICENSE_LABEL = "DC-ANCSA v1.0"


class LicenseDialog(QDialog):
    def __init__(self, parent, root, markdown, review=False):
        super().__init__(parent)
        self.setWindowTitle("Design Creations Software License")
        self.resize(820, 640)
        layout = QVBoxLayout(self)
        self.browser = QTextBrowser(openLinks=False)
        self.browser.setAccessibleName("Software license text")
        self.browser.setMarkdown(markdown)
        self.browser.anchorClicked.connect(self.open_link)
        layout.addWidget(self.browser)
        if review:
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
            accept = buttons.addButton("Accept license and install", QDialogButtonBox.ButtonRole.AcceptRole)
            accept.setAutoDefault(False)
            buttons.button(QDialogButtonBox.StandardButton.Cancel).setDefault(True)
        else:
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.window_geometry = WindowGeometry(self, root / "software-license-window.bin")

    @staticmethod
    def open_link(url):
        if url.scheme() in ("https", "http", "mailto"):
            QDesktopServices.openUrl(url)
