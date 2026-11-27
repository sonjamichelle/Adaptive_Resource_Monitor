# Adaptive Resource Monitor
# Original developer: Sonja M Thomas
# Copyright 2010-2026 SLT Design Creations, LLC
# Licensed under the Design Creations Attribution-NonCommercial-ShareAlike License v1.0.
# See LICENSE.md for complete license terms.
# https://www.designcreations.us/

"""Signed release contract shared by the updater, maintenance worker and CI."""
from base64 import b64decode
from dataclasses import dataclass
from hashlib import file_digest
import json
from pathlib import Path
import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .branding import APP_MODEL_ID
from .version import CHANNELS, ROOT, version_key

MANIFEST = "arm-update-windows-x64.json"
LICENSE_FILE = "LICENSE.md"
LICENSE_NOTE = "Software license SHA-256 "
ARCHITECTURE = "windows-x64"
KINDS = {"installed": "-setup.exe", "portable": "-portable.zip"}
MAX_PACKAGE_SIZE = 1024**3
MAX_MANIFEST_SIZE = 256 * 1024
MAX_NOTES_LENGTH = 32_000
SHA256 = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")


class UpdateError(Exception):
    pass


def source_config():
    return json.loads((ROOT / "update-source.json").read_text(encoding="utf-8"))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256(path):
    with Path(path).open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def software_license_digest(notes):
    last = notes.rsplit("\n", 1)[-1]
    if last.startswith(LICENSE_NOTE):
        digest = last[len(LICENSE_NOTE):]
        if SHA256.fullmatch(digest):
            return digest
    return None


def artifact_name(version, kind):
    version_key(version)
    return f"AdaptiveResourceMonitor-{version}-{ARCHITECTURE}{KINDS[kind]}"


@dataclass(frozen=True)
class Package:
    kind: str
    name: str
    size: int
    sha256: str


@dataclass(frozen=True)
class Release:
    version: str
    commit: str
    build: int
    notes: str
    packages: dict[str, Package]
    envelope: bytes


def verify_manifest(raw, public_key, expected_version=None):
    try:
        if len(raw) > MAX_MANIFEST_SIZE:
            raise ValueError()
        envelope = json.loads(raw)
        if set(envelope) != {"manifest", "signature"}:
            raise ValueError()
        manifest = envelope["manifest"]
        key = Ed25519PublicKey.from_public_bytes(b64decode(public_key, validate=True))
        key.verify(b64decode(envelope["signature"], validate=True), canonical(manifest))
        if (set(manifest) != {"protocol", "application", "architecture", "version", "commit", "build", "notes", "packages"}
                or type(manifest["protocol"]) is not int or manifest["protocol"] != 1
                or manifest["application"] != APP_MODEL_ID or manifest["architecture"] != ARCHITECTURE):
            raise ValueError()
        version = manifest["version"]
        version_key(version)
        if expected_version is not None and version != expected_version:
            raise ValueError()
        if (not COMMIT.fullmatch(manifest["commit"]) or type(manifest["build"]) is not int or manifest["build"] < 1
                or not isinstance(manifest["notes"], str) or not 1 <= len(manifest["notes"]) <= MAX_NOTES_LENGTH
                or set(manifest["packages"]) != set(KINDS)):
            raise ValueError()
        packages = {}
        for kind, data in manifest["packages"].items():
            if (set(data) != {"name", "size", "sha256"} or data["name"] != artifact_name(version, kind)
                    or type(data["size"]) is not int or not 0 < data["size"] <= MAX_PACKAGE_SIZE
                    or not SHA256.fullmatch(data["sha256"])):
                raise ValueError()
            packages[kind] = Package(kind, **data)
    except InvalidSignature:
        raise UpdateError("Ed25519 manifest signature is invalid") from None
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        raise UpdateError("Signed release metadata is invalid or inconsistent") from None
    return Release(version, manifest["commit"], manifest["build"], manifest["notes"], packages, raw)


def verify_file(path, package):
    path = Path(path)
    if path.name != package.name or not path.is_file() or path.stat().st_size != package.size:
        raise UpdateError("Package filename or size does not match the signed manifest")
    if sha256(path) != package.sha256:
        raise UpdateError("Package SHA-256 does not match the signed manifest")


def exclusion_reason(version, installed):
    """Return the policy reason a tag cannot be considered for this installation."""
    candidate = version_key(version)
    current = version_key(installed)
    if candidate[:4] < current[:4]:
        return f"Numerical version is older than installed {installed}"
    if candidate[-1] < current[-1]:
        return f"{CHANNELS[candidate[-1]].capitalize()} releases are ineligible for a {CHANNELS[current[-1]]} installation"
    return None


def eligible(version, installed):
    return exclusion_reason(version, installed) is None
