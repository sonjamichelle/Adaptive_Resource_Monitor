from base64 import b64encode
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch
from urllib.error import URLError
from zipfile import ZipFile
import psutil

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from arm.branding import APP_MODEL_ID
from arm.config import Settings
from arm.update_client import ReleaseClient, UpdateCancelled
from arm.update_release import MANIFEST, UpdateError, artifact_name, canonical, verify_manifest
from arm.update_state import Phase, notice, notify_once, result_for, transaction_from_ack
from arm.update_worker import unpack_portable, wait_parent
from arm.version import VERSION, version_key

COUNTERS = version_key(VERSION)
NEW = "v{}.{}.{}.{}_{}".format(*COUNTERS[:3], COUNTERS[3] + 1, VERSION.rsplit("_", 1)[1])
OLD = "v0.0.0.0_alpha"
PACKAGE = b"abcdefgh" * 100_000


class Response(BytesIO):
    def __init__(self, data, status=200, headers=None):
        super().__init__(data)
        self.status = status
        self.headers = headers or {"Content-Length": str(len(data))}


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.public = b64encode(self.key.public_key().public_bytes_raw()).decode("ascii")
        self.client = ReleaseClient({"base": "https://updates.example.test/gitea", "owner": "qa",
                                     "repository": "arm", "public_key": self.public})
        self.root = self.enterContext(TemporaryDirectory(prefix="arm-update-test-"))
        self.work = Path(self.root)

    def metadata(self, version=NEW):
        return {"protocol": 1, "application": APP_MODEL_ID, "architecture": "windows-x64", "version": version,
                "commit": "d" * 40, "build": 13, "notes": "ARM test update",
                "packages": {kind: {"name": artifact_name(version, kind), "size": len(PACKAGE),
                                    "sha256": sha256(PACKAGE).hexdigest()} for kind in ("installed", "portable")}}

    def sign(self, metadata):
        return canonical({"manifest": metadata, "signature": b64encode(self.key.sign(canonical(metadata))).decode()})

    def row(self, metadata, raw=None):
        version = metadata["version"]
        manifest = raw or self.sign(metadata)
        assets = [{"name": MANIFEST, "size": len(manifest), "browser_download_url": self.client.url(version, MANIFEST)}]
        for package in metadata["packages"].values():
            assets.append({**package, "browser_download_url": self.client.url(version, package["name"])})
        return {"tag_name": version, "draft": False, "prerelease": not version.endswith("_stable"),
                "body": metadata["notes"], "assets": assets}, manifest

    def test_signature_and_signed_identity(self):
        meta = self.metadata()
        signed = self.sign(meta)
        self.assertEqual(verify_manifest(signed, self.public, NEW).build, 13)
        for field, value in (("application", "OtherApp"), ("architecture", "windows-arm64"),
                             ("version", OLD), ("build", 0)):
            with self.subTest(field=field), self.assertRaises(UpdateError):
                verify_manifest(self.sign(meta | {field: value}), self.public, NEW)
        modified = json.loads(signed)
        modified["manifest"]["notes"] = "Modified"
        with self.assertRaisesRegex(UpdateError, "signature"):
            verify_manifest(canonical(modified), self.public, NEW)
        with self.assertRaises(UpdateError):
            verify_manifest(canonical({"manifest": meta}), self.public, NEW)
        for field, value in (("name", "foreign.zip"), ("size", -1), ("sha256", "incorrect")):
            with self.subTest(field=field), self.assertRaises(UpdateError):
                self.verify_bad_package(field, value)

    def verify_bad_package(self, field, value):
        bad = self.metadata()
        bad["packages"]["portable"][field] = value
        return verify_manifest(self.sign(bad), self.public, NEW)

    def test_discovery_verified_current_and_older(self):
        for version in (NEW, VERSION, OLD):
            row, raw = self.row(self.metadata(version))
            with patch.object(self.client, "read", side_effect=[canonical([row]), raw]):
                checked = self.client.check(VERSION, "installed")
            self.assertEqual(checked.published, version)
            if version == OLD:
                self.assertIsNone(checked.release)
            else:
                self.assertEqual(checked.release.version, version)

    def test_bad_latest_manifest_reports_rejection_and_falls_back(self):
        newest, _ = self.row(self.metadata())
        current, raw = self.row(self.metadata(VERSION))
        with patch.object(self.client, "read", side_effect=[canonical([current, newest]), b"invalid", raw]):
            checked = self.client.check(VERSION, "portable")
        self.assertEqual((checked.published, checked.release.version), (NEW, VERSION))
        self.assertIn(NEW, checked.issues[0])
        with patch.object(self.client, "read", side_effect=URLError("unavailable")), self.assertRaises(URLError):
            self.client.check(VERSION, "installed")

    def test_signed_discovery_allows_the_same_or_a_more_mature_channel(self):
        channels = ("alpha", "beta", "rc", "stable")
        for index, installed_channel in enumerate(channels):
            installed = f"v0.6.2.2_{installed_channel}"
            for maturity, offered in enumerate(channels):
                newer = f"v0.6.2.3_{offered}"
                with self.subTest(installed=installed, candidate=newer):
                    row, envelope = self.row(self.metadata(newer))
                    with patch.object(self.client, "read", side_effect=[canonical([row]), envelope]) as read:
                        found = self.client.check(installed, "installed")
                    self.assertEqual(found.issues, ())
                    if maturity >= index:
                        self.assertEqual(found.release.version, newer)
                        self.assertEqual(found.exclusions, ())
                    else:
                        self.assertIsNone(found.release)
                        self.assertIn(f"ineligible for a {installed_channel} installation", found.exclusions[0])
                        self.assertEqual(read.call_count, 1)

    def test_same_number_beta_is_selected_over_signed_current_alpha(self):
        alpha, beta = "v0.6.2.2_alpha", "v0.6.2.2_beta"
        old, _ = self.row(self.metadata(alpha))
        current, signature = self.row(self.metadata(beta))
        with patch.object(self.client, "read", side_effect=[canonical([old, current]), signature]):
            found = self.client.check(alpha, "portable")
        self.assertEqual((found.published, found.release.version, found.exclusions), (beta, beta, ()))
        with patch.object(self.client, "read", return_value=canonical([old])) as read:
            rejected = self.client.check(beta, "portable")
        self.assertIsNone(rejected.release)
        self.assertIn("Alpha releases are ineligible", rejected.exclusions[0])
        self.assertEqual(read.call_count, 1)

    def test_more_mature_channel_cannot_downgrade_the_numerical_version(self):
        row, _ = self.row(self.metadata("v0.6.2.1_stable"))
        with patch.object(self.client, "read", return_value=canonical([row])) as read:
            found = self.client.check("v0.6.2.2_alpha", "installed")
        self.assertIsNone(found.release)
        self.assertIn("Numerical version is older", found.exclusions[0])
        self.assertEqual(read.call_count, 1)

    def test_identical_verified_release_cannot_be_downloaded_as_an_update(self):
        row, envelope = self.row(self.metadata(VERSION))
        with patch.object(self.client, "read", side_effect=[canonical([row]), envelope]):
            found = self.client.check(VERSION, "installed")
        self.assertEqual(found.release.version, VERSION)
        with self.assertRaisesRegex(UpdateError, "newer"):
            self.client.download(found.release, "installed", self.work, lambda *_: None, lambda: False)
        self.assertFalse(list(self.work.iterdir()))

    def test_discovery_rejects_unsupported_and_malformed_tags(self):
        rows = [{"draft": False, "tag_name": tag} for tag in (
            "v0.6.2.2_preview", "v0.6.2_beta", "v00.6.2.2_beta", "v0.6.2.65536_alpha",
        )]
        with patch.object(self.client, "read", return_value=canonical(rows)) as read:
            found = self.client.check("v0.6.2.2_alpha", "installed")
        self.assertIsNone(found.published)
        self.assertIsNone(found.release)
        self.assertEqual(read.call_count, 1)

    def test_discovery_preserves_signature_architecture_and_gitea_classification_checks(self):
        beta = self.metadata("v0.6.2.2_beta")
        stable = self.metadata("v0.6.2.2_stable")
        tampered = json.loads(self.sign(beta))
        tampered["manifest"]["notes"] = "Modified"
        for metadata, envelope, flag, expected in (
            (beta, canonical(tampered), True, "signature is invalid"),
            (beta | {"architecture": "windows-arm64"}, None, True, "metadata is invalid"),
            (beta, None, False, "classification disagrees"),
            (stable, None, True, "classification disagrees"),
        ):
            with self.subTest(expected=expected, tag=metadata["version"]):
                row, signature = self.row(metadata, envelope)
                with patch.object(self.client, "read", side_effect=[canonical([row | {"prerelease": flag}]), signature]):
                    found = self.client.check("v0.6.2.2_alpha", "installed")
                self.assertIsNone(found.release)
                self.assertEqual(found.exclusions, ())
                self.assertIn(expected, found.issues[0])

    def test_download_cancel_and_resume(self):
        release = verify_manifest(self.sign(self.metadata()), self.public)
        cancel = Event()
        cancel_after_bytes = lambda received, total: cancel.set() if received else None
        with patch.object(self.client, "open", return_value=Response(PACKAGE)):
            with self.assertRaises(UpdateCancelled):
                self.client.download(release, "portable", self.work, cancel_after_bytes, cancel.is_set)
        part, = self.work.rglob("*.part")
        start = part.stat().st_size
        self.assertTrue(0 < start < len(PACKAGE))
        cancel.clear()
        response = Response(PACKAGE[start:], 206, {"Content-Length": str(len(PACKAGE) - start),
                            "Content-Range": f"bytes {start}-{len(PACKAGE)-1}/{len(PACKAGE)}"})
        with patch.object(self.client, "open", return_value=response) as fetch:
            path = self.client.download(release, "portable", self.work, lambda *_: None, cancel.is_set)
            self.assertEqual(fetch.call_args.args[1]["Range"], f"bytes={start}-")
        self.assertEqual(path.read_bytes(), PACKAGE)
        self.assertEqual((path.parent / MANIFEST).read_bytes(), release.envelope)
        self.assertFalse(part.exists())

    def test_interrupted_then_corrupted_package(self):
        release = verify_manifest(self.sign(self.metadata()), self.public)
        with patch.object(self.client, "open", return_value=Response(PACKAGE[:30], headers={"Content-Length": str(len(PACKAGE))})):
            with self.assertRaisesRegex(UpdateError, "interrupted"):
                self.client.download(release, "installed", self.work, lambda *_: None, lambda: False)
        part, = self.work.rglob("*.part")
        self.assertEqual(part.read_bytes(), PACKAGE[:30])
        with patch.object(self.client, "open", return_value=Response(b"b" * len(PACKAGE))):
            with self.assertRaisesRegex(UpdateError, "SHA-256"):
                self.client.download(release, "installed", self.work, lambda *_: None, lambda: False)
        self.assertFalse(any(self.work.rglob("*.exe")))

    def test_portable_package_refuses_traversal_and_ntfs_streams(self):
        archive = self.work / "bad.zip"
        for member in ("../escape.exe", "AdaptiveResourceMonitor/_internal/trick:payload.dll",
                       "AdaptiveResourceMonitor/_internal/../escape.exe", "AdaptiveResourceMonitor/_internal/NUL.txt"):
            with self.subTest(member=member), ZipFile(archive, "w") as target:
                target.writestr(member, "test")
            with self.assertRaisesRegex(UpdateError, "unsafe"):
                unpack_portable(archive, self.work / "unzip", NEW)

    def test_version_and_startup_settings_validation(self):
        self.assertGreater(version_key(NEW), version_key(VERSION))
        self.assertGreater(version_key(VERSION), version_key(OLD))
        self.assertEqual(Settings.from_dict({"update_startup": True, "update_interval": 168}).update_interval, 168)
        default = Settings.from_dict({"update_startup": "yes", "update_interval": 169})
        self.assertEqual((default.update_startup, default.update_interval), (False, 0))

    def test_notification_only_once_across_checks_and_restarts(self):
        path = self.work / "notices.json"
        self.assertFalse(notify_once(path, NEW, False))
        self.assertFalse(path.exists())
        self.assertTrue(notify_once(path, NEW, True))
        self.assertFalse(notify_once(path, NEW, True))
        self.assertEqual(notice(Phase.CHECKING, None), "")
        self.assertEqual(notice(Phase.INSTALLING, NEW, True), "")
        self.assertEqual(notice(Phase.AVAILABLE, NEW), f"Update Available: {NEW}")
        self.assertEqual(notice(Phase.READY, NEW, True), f"Update Ready to Install: {NEW}")

    def test_update_result_requires_successful_restart_receipt(self):
        directory = self.work / "updates" / "transactions" / ("a" * 32)
        directory.mkdir(parents=True)
        (directory / "plan.json").write_text(json.dumps({"old": VERSION, "new": NEW}))
        status = directory / "status.json"
        status.write_text(json.dumps({"state": "complete", "message": "Legacy completion status"}))
        ready = directory / "ready.json"
        self.assertEqual(transaction_from_ack(self.work, str(ready)), directory)
        self.assertIsNone(transaction_from_ack(self.work, str(status)))
        self.assertIsNone(result_for(directory, NEW))
        ready.write_text(json.dumps({"version": NEW, "pid": 10}))
        self.assertEqual(result_for(directory, NEW), (Phase.SUCCESS, notice(Phase.SUCCESS, NEW)))
        self.assertIsNone(result_for(directory, VERSION))
        status.write_text(json.dumps({"state": "rolled_back", "message": "Restored prior application"}))
        self.assertEqual(result_for(directory, VERSION), (Phase.RESTORED, "Restored prior application"))
        self.assertIsNone(result_for(directory, NEW))

    def test_shutdown_requires_acknowledgement_and_confirmed_process_exit(self):
        target = self.work
        plan = {"parent": 10, "created": 1, "old": VERSION}
        with patch("arm.update_worker.psutil.Process", side_effect=psutil.NoSuchProcess(10)):
            with self.assertRaisesRegex(UpdateError, "without confirming"):
                wait_parent(plan, target, self.work)
            (self.work / "closed.json").write_text(json.dumps({"pid": 10, "version": VERSION}))
            wait_parent(plan, target, self.work)
            with patch("arm.update_worker.read_json", side_effect=[None, {"pid": 10, "version": VERSION}]):
                wait_parent(plan, target, self.work)
        with patch("arm.update_worker.psutil.Process") as process:
            process.return_value.create_time.return_value = 1
            process.return_value.exe.return_value = str(target / "AdaptiveResourceMonitor.exe")
            with self.assertRaisesRegex(UpdateError, "shut down in time"):
                wait_parent(plan, target, self.work, timeout=.05)
            self.assertEqual(process.return_value.exe.call_count, 1)
            (self.work / "abort").touch()
            with self.assertRaisesRegex(UpdateError, "canceled"):
                wait_parent(plan, target, self.work)
