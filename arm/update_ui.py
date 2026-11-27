"""Asynchronous Workshop-style update controls for the About tab."""
from datetime import datetime
import json
import logging
from threading import Event, Thread
from time import monotonic

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFormLayout, QGridLayout, QGroupBox, QLabel, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QVBoxLayout,
)

from .update_client import ReleaseClient, UpdateCancelled, write_atomic
from .update_release import MANIFEST, UpdateError, eligible, verify_file, verify_manifest
from .update_state import Phase, notice, notify_once, read_json, result_for
from .version import VERSION, version_key

LOG = logging.getLogger(__name__)
PACKAGE_LABELS = {"installed": "Windows x64 installer", "portable": "Windows x64 portable ZIP"}


class UpdatePanel(QGroupBox):
    notify = Signal(str)
    changed = Signal(str, bool)
    result = Signal(str, object)
    transferred = Signal(int, int)
    quit_requested = Signal(object)

    def __init__(self, root, installation_kind):
        super().__init__("Application Update")
        self.root = root / "updates"
        self.kind = "installed" if installation_kind == "Windows installed" else "portable"
        self.installable = installation_kind != "Source checkout"
        self.client = ReleaseClient()
        self.job = None
        self.release = self.downloaded = self.plan = None
        self.phase = Phase.CURRENT
        self.outcome = None
        self.success_banner = False
        self.message = ""
        self.paused = False
        self.worker = None
        self.cancel = Event()
        self.closing = False
        self.policy = None
        self.last_file = self.root / "last-check.json"
        self.root.mkdir(parents=True, exist_ok=True)

        layout = QVBoxLayout(self)
        summary = QFormLayout()
        self.fields = {}
        for caption, value in (
            ("Installed version", VERSION), ("Latest published", "Not checked"),
            ("Latest eligible verified", "Not checked"), ("Last successful check", self.last_check()),
            ("Package", PACKAGE_LABELS[self.kind]), ("Download size", "—"),
            ("Verification", "Awaiting a signed manifest"),
        ):
            field = QLabel(value, textFormat=Qt.TextFormat.PlainText, wordWrap=True)
            self.fields[caption] = field
            summary.addRow(caption, field)
        layout.addLayout(summary)
        self.status = QLabel("Ready to check for updates.", textFormat=Qt.TextFormat.PlainText, wordWrap=True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setAccessibleName("Update progress")
        self.progress.hide()
        layout.addWidget(self.progress)
        buttons = QGridLayout()
        actions = (
            ("Check for Updates", self.check_now), ("Download Update", self.download_now),
            ("Cancel Download", self.cancel.set), ("View Details", self.toggle_details),
            ("Install Update", self.install_now), ("Install Later", self.defer_install),
        )
        self.buttons = {}
        for index, (name, action) in enumerate(actions):
            button = QPushButton(name)
            button.clicked.connect(action)
            buttons.addWidget(button, index // 3, index % 3)
            self.buttons[name] = button
        layout.addLayout(buttons)
        self.notes = QPlainTextEdit(readOnly=True)
        self.notes.setAccessibleName("Signed release notes")
        self.notes.setMaximumHeight(110)
        self.notes.hide()
        layout.addWidget(self.notes)
        self.periodic = QTimer(self)
        self.periodic.timeout.connect(self.check_now)
        self.handoff = QTimer(self, interval=250)
        self.handoff.timeout.connect(self.poll_worker)
        self.receipt = QTimer(self, interval=350)
        self.receipt.timeout.connect(self.poll_receipt)
        self.result.connect(self.finished)
        self.transferred.connect(self.update_progress)
        self.set_controls()

    def configure(self, settings):
        policy = (settings.update_startup, settings.update_interval, settings.update_notifications)
        if self.policy == policy:
            return
        first = self.policy is None
        self.policy = policy
        self.periodic.stop()
        if settings.update_interval:
            self.periodic.start(settings.update_interval * 3_600_000)
        if first:
            QTimer.singleShot(900, self.initialize)
        else:
            self.set_controls()

    def initialize(self):
        if self.job:
            return
        self.start("restore", self.restore)

    def last_check(self):
        try:
            last = datetime.fromisoformat(json.loads(self.last_file.read_bytes()))
            return last.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z (UTC%z)")
        except (ValueError, TypeError, OSError):
            return "No successful check recorded"

    def restore(self):
        status = None
        plans = sorted((self.root / "transactions").glob("*/status.json"),
                       key=lambda path: path.stat().st_mtime, reverse=True)
        if plans:
            status = result_for(plans[0].parent)
        verified = []
        for manifest in (self.root / "downloads").glob(f"*/{MANIFEST}"):
            try:
                release = verify_manifest(manifest.read_bytes(), self.client.source["public_key"])
                if eligible(release.version, VERSION) and release.version != VERSION:
                    package = release.packages[self.kind]
                    artifact = manifest.parent / package.name
                    if artifact.is_file():
                        verify_file(artifact, package)
                        verified.append((release, artifact, False))
                    elif artifact.with_suffix(artifact.suffix + ".part").is_file():
                        verified.append((release, None, True))
            except (OSError, UpdateError):
                continue
        return status, max(verified, key=lambda entry: version_key(entry[0].version),
                           default=(None, None, False))

    def follow_restart(self, directory):
        self.restart_result = directory
        self.receipt_deadline = monotonic() + 45
        self.receipt.start()

    def poll_receipt(self):
        result = result_for(self.restart_result)
        if result:
            self.receipt.stop()
            self.accept_outcome(result)
        elif monotonic() > self.receipt_deadline:
            self.receipt.stop()

    def accept_outcome(self, result):
        self.outcome, self.message = result
        if self.outcome is Phase.SUCCESS:
            try:
                self.success_banner |= notify_once(self.root / "confirmation.json", VERSION, True)
            except OSError:
                self.success_banner = True
                LOG.exception("Could not persist the ARM update confirmation")
        self.status.setText(self.message)
        self.set_controls()

    def start(self, operation, action):
        if self.closing or self.job or self.plan:
            return
        self.job = operation
        self.cancel.clear()
        self.set_controls()

        def work():
            try:
                value = action()
            except UpdateCancelled as exc:
                operation_result = ("paused", str(exc))
            except Exception as exc:
                LOG.warning("ARM update %s: %s", operation, exc)
                operation_result = ("error", str(exc))
            else:
                operation_result = (operation, value)
            if not self.closing:
                self.result.emit(*operation_result)

        self.worker = Thread(target=work, name=f"ARM update {operation}", daemon=True)
        self.worker.start()

    def check_now(self):
        if self.job or self.plan:
            return
        self.status.setText("Checking the public release repository…")
        self.progress.hide()
        self.start("check", lambda: self.client.check(VERSION, self.kind))

    def set_release(self, release):
        self.release = release
        package = release.packages[self.kind]
        self.fields["Latest eligible verified"].setText(release.version)
        self.fields["Download size"].setText(f"{package.size / 1024**2:.1f} MiB ({package.size:,} bytes)")
        self.fields["Verification"].setText("Ed25519 manifest and release metadata verified")
        self.notes.setPlainText(release.notes)

    def finished(self, operation, value):
        previous_job = self.job
        self.job = None
        self.progress.hide()
        if operation == "restore":
            outcome, (release, artifact, self.paused) = value
            if release:
                self.set_release(release)
                self.downloaded = artifact
                if artifact:
                    self.fields["Verification"].setText("Manifest signature and package SHA-256 verified")
                    self.status.setText("Verified package saved. Install it when ready.")
                else:
                    self.status.setText("Download paused. Retry to resume.")
            if outcome:
                self.accept_outcome(outcome)
            if self.policy and self.policy[0]:
                self.check_now()
        elif operation == "check":
            self.fields["Latest published"].setText(value.published or "No public releases")
            if value.release:
                if not self.release or value.release.envelope != self.release.envelope:
                    self.downloaded = None
                    self.paused = False
                self.set_release(value.release)
                if self.release.version == VERSION:
                    self.status.setText("This is the latest verified version.")
                else:
                    self.status.setText("A verified update is available." if self.downloaded is None else "Verified package saved.")
                    if self.downloaded:
                        self.fields["Verification"].setText("Manifest signature and package SHA-256 verified")
            else:
                if not self.downloaded:
                    self.release = None
                    self.paused = False
                    self.notes.clear()
                    self.fields["Latest eligible verified"].setText("None")
                    self.fields["Download size"].setText("—")
                    self.fields["Verification"].setText("Verification failed" if value.issues else "No eligible manifest")
                self.status.setText("No eligible verified update is available.")
            if value.issues:
                self.status.setText(self.status.text() + " Rejected " + "; ".join(value.issues)[:380])
            if value.release or not value.issues:
                try:
                    write_atomic(self.last_file, json.dumps(datetime.now().astimezone().isoformat()).encode())
                    self.fields["Last successful check"].setText(self.last_check())
                except OSError:
                    LOG.exception("Could not save the last successful ARM update check")
        elif operation == "download":
            self.paused = False
            self.downloaded = value
            self.fields["Verification"].setText("Manifest signature and package SHA-256 verified")
            self.status.setText("Verified package saved. Install it when ready.")
        elif operation == "prepare":
            self.plan = value
            self.elapsed = 0
            self.handoff.start()
        else:
            self.status.setText(("Update unavailable. " if operation == "error" else "") + value)
            if previous_job == "download":
                self.paused = True
            elif previous_job == "prepare":
                self.downloaded = None
                self.outcome = Phase.FAILED
                self.message = self.status.text()
        self.set_controls()

    def download_now(self):
        release = self.release
        if self.job or self.plan or release is None or release.version == VERSION:
            return
        self.status.setText("Downloading the signed release package…")
        self.progress.setRange(0, 0)
        self.progress.show()
        self.start("download", lambda: self.client.download(
            release, self.kind, self.root / "downloads", self.transferred.emit, self.cancel.is_set))

    def update_progress(self, received, total):
        if self.job == "download":
            self.progress.setRange(0, 1000)
            self.progress.setValue(received * 1000 // total)

    def toggle_details(self):
        self.notes.setVisible(self.notes.isHidden())

    def install_now(self):
        if not self.downloaded or self.job or self.plan or not self.installable:
            return
        if QMessageBox.question(self, "Install Update", f"Install {self.release.version} and restart Adaptive Resource Monitor?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        from .about import installation
        from .update_worker import prepare
        release, artifact, target = self.release, self.downloaded, installation()[1]
        self.outcome = None
        self.status.setText("Revalidating the package and preparing the maintenance launcher…")
        self.progress.setRange(0, 0)
        self.progress.show()
        self.start("prepare", lambda: prepare(release, artifact, target, self.kind, self.root))

    def defer_install(self):
        self.status.setText("Installation deferred. The verified package will be available from About.")

    def poll_worker(self):
        self.elapsed += 250
        status = read_json(self.plan / "status.json", {})
        if status.get("state") == "waiting":
            self.handoff.stop()
            self.quit_requested.emit(self.plan)
        elif status.get("state") == "failed" or self.elapsed > 70_000:
            self.handoff.stop()
            self.abort_install(status.get("message") or
                               "The maintenance launcher did not become ready. Installation was deferred.")

    def abort_install(self, message):
        if self.plan:
            try:
                (self.plan / "abort").touch()
            except OSError:
                LOG.exception("Could not signal that ARM canceled the installation")
            self.plan = None
        self.accept_outcome((Phase.FAILED, message))

    def set_controls(self):
        available = self.release is not None and self.release.version != VERSION
        idle = self.job is None and self.plan is None
        states = (idle, idle and available and self.downloaded is None, self.job == "download",
                  self.release is not None, idle and self.downloaded is not None and self.installable,
                  idle and self.downloaded is not None)
        for button, enabled in zip(self.buttons.values(), states):
            button.setEnabled(enabled)
        if self.plan or self.job == "prepare":
            self.phase = Phase.INSTALLING
        elif self.job == "download":
            self.phase = Phase.DOWNLOADING
        elif self.job == "check":
            self.phase = Phase.CHECKING
        elif self.outcome in (Phase.FAILED, Phase.RESTORED):
            self.phase = self.outcome
        elif self.downloaded:
            self.phase = Phase.READY
        elif self.paused:
            self.phase = Phase.PAUSED
        elif available:
            self.phase = Phase.AVAILABLE
        else:
            self.phase = self.outcome or Phase.CURRENT
        version = self.release.version if available else None
        show_success = self.phase is Phase.SUCCESS and self.success_banner
        label = notice(self.phase, VERSION if show_success else version, bool(self.downloaded))
        self.changed.emit(label, self.phase is Phase.SUCCESS)
        key = f"success:{VERSION}" if self.phase is Phase.SUCCESS else f"available:{version}"
        if label and self.policy:
            try:
                if notify_once(self.root / "notifications.json", key, self.policy[2]):
                    self.notify.emit(label)
            except OSError:
                LOG.exception("Could not persist the ARM update notification")

    def stop(self):
        self.closing = True
        self.cancel.set()
        self.handoff.stop()
        self.periodic.stop()
        self.receipt.stop()
        if self.worker:
            self.worker.join(timeout=20)
            return not self.worker.is_alive()
        return True
