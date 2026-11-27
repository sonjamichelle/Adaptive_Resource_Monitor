# Adaptive Resource Monitor
# Original developer: Sonja M Thomas
# Copyright 2010-2026 SLT Design Creations, LLC
# Licensed under the Design Creations Attribution-NonCommercial-ShareAlike License v1.0.
# See LICENSE.md for complete license terms.
# https://www.designcreations.us/

"""Sign an archived Jenkins candidate and publish an explicitly pinned build."""
import argparse
from base64 import b64decode, b64encode
from hashlib import file_digest, sha256 as hash_bytes
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.branding import APP_MODEL_ID
from arm.update_client import ReleaseClient
from arm.update_release import (
    ARCHITECTURE, KINDS, LICENSE_FILE, LICENSE_NOTE, MANIFEST, UpdateError, artifact_name, canonical, sha256,
    software_license_digest, source_config, verify_file, verify_manifest,
)
from arm.update_worker import unpack_portable, verify_executable
from arm.version import VERSION, version_key

CHECKSUMS = "SHA256SUMS.txt"
NOTES = "RELEASE_NOTES.md"
KEY = "arm-ed25519.pub"
RECEIPT = "release-build.json"


def git(*args):
    return subprocess.check_output(("git", *args), cwd=ROOT, text=True, encoding="utf-8").strip()


def head_version(commit, version):
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise UpdateError("Expected a 40-character Git commit")
    version_key(version)
    if git("show", f"{commit}:VERSION.md") != version:
        raise UpdateError("Pinned commit and authoritative version disagree")


def notes_at(commit, version):
    text = git("show", f"{commit}:CHANGELOG.md")
    section = re.search(rf"^## {re.escape(version)}\s[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not section or not section[1].strip():
        raise UpdateError("Pinned version has no changelog entry")
    notes = section[1].strip()
    if git("ls-tree", "--name-only", commit, "--", LICENSE_FILE):
        license_text = subprocess.check_output(("git", "show", f"{commit}:{LICENSE_FILE}"), cwd=ROOT)
        notes += f"\n\n{LICENSE_NOTE}{hash_bytes(license_text).hexdigest()}"
    return notes


def expected_receipt(release):
    return {
        "application": APP_MODEL_ID, "architecture": ARCHITECTURE, "version": release.version,
        "source_commit": release.commit, "jenkins_build": release.build,
        "packages": {kind: {"name": p.name, "size": p.size, "sha256": p.sha256}
                     for kind, p in release.packages.items()},
    }


def checksums(release):
    return "".join(f"{package.sha256}  {package.name}\n" for _, package in sorted(release.packages.items()))


def files_for(release):
    return {*(p.name for p in release.packages.values()), MANIFEST, CHECKSUMS, NOTES, KEY, RECEIPT}


def verify(folder, version, commit, number):
    head_version(commit, version)
    source = source_config()
    release = verify_manifest((folder / MANIFEST).read_bytes(), source["public_key"], version)
    if (release.commit, release.build, release.notes) != (commit, number, notes_at(commit, version)):
        raise UpdateError("Signed manifest does not match the pinned Jenkins build or changelog")
    if {path.name for path in folder.iterdir()} != files_for(release):
        raise UpdateError("Release folder contains missing or unexpected files")
    if (json.loads((folder / RECEIPT).read_bytes()) != expected_receipt(release)
            or (folder / KEY).read_text(encoding="ascii").strip() != source["public_key"]
            or (folder / NOTES).read_text(encoding="utf-8").strip() != release.notes
            or (folder / CHECKSUMS).read_text(encoding="ascii") != checksums(release)):
        raise UpdateError("Artifact receipt, notes, key or checksums disagree with the signed manifest")
    for package in release.packages.values():
        verify_file(folder / package.name, package)
        print(f"{package.name} | {package.size:,} bytes | SHA-256 {package.sha256}")
    verify_executable(folder / release.packages["installed"].name, version)
    with TemporaryDirectory(prefix="arm-release-verify-") as temporary:
        payload = Path(temporary)
        unpack_portable(folder / release.packages["portable"].name, payload, version)
        build = json.loads((payload / "BUILD.json").read_bytes())
        if (build.get("source_revision"), build.get("jenkins_build"), build.get("source_modified")) != (commit, number, False):
            raise UpdateError("Portable package is inconsistent with the selected Jenkins build")
        if json.loads((payload / "_internal" / "update-source.json").read_bytes()) != source:
            raise UpdateError("Packaged update repository or trust key is inconsistent")
        if (license_digest := software_license_digest(release.notes)):
            if not (payload / LICENSE_FILE).is_file() or sha256(payload / LICENSE_FILE) != license_digest:
                raise UpdateError("Packaged software license disagrees with the signed source license")
    print(f"Verified Ed25519 signature, Windows x64 packages and build identity | {version} | {commit} | Jenkins #{number}")
    return release


def sign(folder, commit, number):
    head_version(commit, VERSION)
    source = source_config()
    key = Ed25519PrivateKey.from_private_bytes(b64decode(os.environ.pop("ARM_ED25519_SIGNING_KEY"), validate=True))
    if b64encode(key.public_key().public_bytes_raw()).decode() != source["public_key"]:
        raise UpdateError("Jenkins signing identity does not match the application's public key")
    archives = {}
    for kind in KINDS:
        name = artifact_name(VERSION, kind)
        path = folder / name
        archives[kind] = {"name": name, "size": path.stat().st_size, "sha256": sha256(path)}
    notes = notes_at(commit, VERSION)
    manifest = {"protocol": 1, "application": APP_MODEL_ID, "architecture": ARCHITECTURE, "version": VERSION,
                "commit": commit, "build": number, "notes": notes, "packages": archives}
    raw = canonical({"manifest": manifest, "signature": b64encode(key.sign(canonical(manifest))).decode()})
    release = verify_manifest(raw, source["public_key"], VERSION)
    (folder / MANIFEST).write_bytes(raw)
    (folder / RECEIPT).write_bytes(canonical(expected_receipt(release)) + b"\n")
    (folder / CHECKSUMS).write_bytes(checksums(release).encode("ascii"))
    (folder / NOTES).write_bytes((notes + "\n").encode("utf-8"))
    (folder / KEY).write_bytes((source["public_key"] + "\n").encode("ascii"))
    print(f"Signed {VERSION} with the ARM-specific Ed25519 Jenkins credential")


class Publication:
    def __init__(self, client, token):
        self.client = client
        self.auth = {"Authorization": f"token {token}", "Accept": "application/json"}

    def request(self, path, data=None, method=None, optional=False, headers=None):
        if isinstance(data, dict):
            data = canonical(data)
        request = Request(self.client.api + path, data, method=method, headers={
            **self.auth, "Content-Type": "application/json", **(headers or {})
        })
        try:
            with self.client.opener.open(request, timeout=120) as response:
                return json.load(response)
        except HTTPError as exc:
            if optional and exc.code == 404:
                return None
            raise UpdateError(f"Gitea {method or 'GET'} {path} failed HTTP {exc.code}") from None

    def upload(self, release_id, path):
        boundary = uuid4().hex
        start = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"attachment\";"
                 f" filename=\"{path.name}\"\r\nContent-Type: application/octet-stream\r\n\r\n").encode("ascii")
        body = start + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode("ascii")
        row = self.request(f"/releases/{release_id}/assets?name={quote(path.name)}", body, "POST", headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}"
        })
        if (row.get("name"), row.get("size")) != (path.name, path.stat().st_size):
            raise UpdateError(f"Gitea returned unexpected attachment details for {path.name}")
        print(f"Uploaded draft attachment {path.name}")

    def verify_downloads(self, folder, row, signed, anonymous):
        matches = row["assets"]
        if len(matches) != len(files_for(signed)) or {entry["name"] for entry in matches} != files_for(signed):
            raise UpdateError("Release contains unexpected or missing attachments")
        version = signed.version
        if (row["tag_name"], row["body"], row["prerelease"]) != (version, signed.notes, not version.endswith("_stable")):
            raise UpdateError("Release title, body or classification disagrees with the signed metadata")
        for entry in matches:
            file = folder / entry["name"]
            url = self.client.attachment(row, version, file.name, file.stat().st_size)
            headers = {} if anonymous else self.auth
            with self.client.open(url, headers) as response:
                if response.headers.get("Content-Length") not in (None, str(file.stat().st_size)):
                    raise UpdateError(f"Release download size mismatch for {file.name}")
                if file.name == MANIFEST:
                    remote = response.read(file.stat().st_size + 1)
                    if remote != signed.envelope:
                        raise UpdateError("Downloaded signed release manifest differs from the archived candidate")
                    verify_manifest(remote, self.client.source["public_key"], version)
                elif file_digest(response, "sha256").hexdigest() != sha256(file):
                    raise UpdateError(f"Downloaded SHA-256 mismatch for {file.name}")
            print(f"{'Anonymous' if anonymous else 'Draft'} readback verified {file.name}")


def publish(folder, version, commit, number):
    if subprocess.run(("git", "merge-base", "--is-ancestor", commit, "origin/main"), cwd=ROOT).returncode:
        raise UpdateError("Selected commit is not reachable from main")
    release = verify(folder, version, commit, number)
    api = Publication(ReleaseClient(), os.environ.pop("ARM_GITEA_PUBLISH_TOKEN"))
    tag = quote(version)
    repository = api.request("")
    if repository["private"] is not False:
        raise UpdateError("The release repository must pass anonymous access validation before publication")
    row = api.request(f"/releases/tags/{tag}", optional=True)
    original_tag = api.request(f"/tags/{tag}", optional=True)
    if original_tag and original_tag["commit"]["sha"] != commit:
        raise UpdateError("An existing version tag points at a different commit")
    if row and not row["draft"]:
        api.verify_downloads(folder, row, release, True)
        print(f"Version {version} is already public with the exact selected bytes")
        return
    if row is None:
        row = api.request("/releases", {"tag_name": version, "target_commitish": commit, "name": f"Adaptive Resource Monitor {version}",
                                       "body": release.notes, "draft": True, "prerelease": not version.endswith("_stable")}, "POST")
    address = f"/releases/{row['id']}"
    if (row["body"], row["target_commitish"]) != (release.notes, commit):
        raise UpdateError("Existing draft does not match the selected build")
    existing = {item["name"] for item in row["assets"]}
    if existing - files_for(release):
        raise UpdateError("Draft contains unrecognized attachments")
    for name in sorted(files_for(release) - existing):
        api.upload(row["id"], folder / name)
    api.verify_downloads(folder, api.request(address), release, False)
    api.request(address, {"draft": False}, "PATCH")
    try:
        opened = json.loads(api.client.read(api.client.api + f"/releases/tags/{tag}", 2 * 1024**2))
        tag_info = json.loads(api.client.read(api.client.api + f"/tags/{tag}", 64 * 1024))
        if opened["draft"] or tag_info["commit"]["sha"] != commit:
            raise UpdateError("Published release or Git tag did not match the pinned build")
        api.verify_downloads(folder, opened, release, True)
    except Exception:
        api.request(address, {"draft": True}, "PATCH")
        raise
    print(f"Published and anonymously verified {api.client.base}/{api.client.repository}/releases/tag/{tag}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("sign", "verify", "publish"))
    parser.add_argument("folder", type=Path)
    parser.add_argument("commit")
    parser.add_argument("build", type=int)
    parser.add_argument("--version", default=VERSION)
    args = parser.parse_args()
    if args.build < 1:
        parser.error("Use a positive Jenkins build number")
    if args.action == "sign":
        sign(args.folder, args.commit, args.build)
    elif args.action == "publish":
        publish(args.folder, args.version, args.commit, args.build)
    else:
        verify(args.folder, args.version, args.commit, args.build)


if __name__ == "__main__":
    main()
