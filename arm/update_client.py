"""Anonymous update discovery and verified downloads from the ARM release repository."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .update_release import (
    MANIFEST, MAX_MANIFEST_SIZE, Release, UpdateError, eligible, exclusion_reason, source_config, verify_file, verify_manifest,
)
from .version import VERSION, version_key

MAX_INDEX_SIZE = 2 * 1024**2
BLOCK = 256 * 1024


class UpdateCancelled(UpdateError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


@dataclass(frozen=True)
class Check:
    published: str | None
    release: Release | None
    issues: tuple[str, ...]
    exclusions: tuple[str, ...] = ()


class ReleaseClient:
    def __init__(self, source=None):
        self.source = source if source is not None else source_config()
        self.base = self.source["base"].rstrip("/")
        origin = urlsplit(self.base)
        if origin.scheme != "https" or not origin.hostname or origin.username or origin.password or origin.query or origin.fragment:
            raise UpdateError("Update source requires a validated HTTPS origin")
        for field in ("owner", "repository"):
            if not re.fullmatch(r"[A-Za-z0-9_-]+", self.source[field]):
                raise UpdateError("Update source repository is invalid")
        self.repository = f"{self.source['owner']}/{self.source['repository']}"
        self.api = f"{self.base}/api/v1/repos/{self.repository}"
        self.opener = build_opener(NoRedirect())

    def url(self, version, name):
        return f"{self.base}/{self.repository}/releases/download/{quote(version, safe='')}/{quote(name, safe='')}"

    def open(self, url, headers=None):
        return self.opener.open(Request(url, headers={
            "User-Agent": f"AdaptiveResourceMonitor/{VERSION}", "Accept-Encoding": "identity", **(headers or {})
        }), timeout=15)

    def read(self, url, limit):
        with self.open(url) as response:
            data = response.read(limit + 1)
        if len(data) > limit:
            raise UpdateError("Release server returned oversized metadata")
        return data

    def attachment(self, row, version, name, size=None):
        matches = [asset for asset in row["assets"] if asset.get("name") == name]
        expected = self.url(version, name)
        if len(matches) != 1 or matches[0].get("browser_download_url") != expected:
            raise UpdateError(f"Missing or inconsistent release attachment: {name}")
        if size is not None and matches[0].get("size") != size:
            raise UpdateError(f"Release attachment size is inconsistent: {name}")
        return expected

    def check(self, installed, kind):
        rows = {}
        for page in range(1, 11):
            batch = json.loads(self.read(f"{self.api}/releases?limit=50&page={page}", MAX_INDEX_SIZE))
            if not isinstance(batch, list):
                raise UpdateError("Release server returned an invalid index")
            for row in batch:
                if not isinstance(row, dict) or row.get("draft") is not False:
                    continue
                version = row.get("tag_name")
                try:
                    version_key(version)
                except ValueError:
                    continue
                rows.setdefault(version, []).append(row)
            if len(batch) < 50:
                break
        ordered = sorted(rows, key=version_key, reverse=True)
        issues = []
        exclusions = []
        for version in ordered:
            if reason := exclusion_reason(version, installed):
                exclusions.append(f"{version}: {reason}")
                continue
            try:
                if len(rows[version]) != 1:
                    raise UpdateError("Release tag appears more than once")
                row = rows[version][0]
                address = self.attachment(row, version, MANIFEST)
                release = verify_manifest(self.read(address, MAX_MANIFEST_SIZE), self.source["public_key"], version)
                if row.get("prerelease") is not (not version.endswith("_stable")):
                    raise UpdateError("Release classification disagrees with its signed version")
                if row.get("body") != release.notes:
                    raise UpdateError("Public release notes disagree with the signed manifest")
                for package in release.packages.values():
                    self.attachment(row, version, package.name, package.size)
            except (UpdateError, HTTPError, KeyError, TypeError, AttributeError) as exc:
                issues.append(f"{version}: {exc.code if isinstance(exc, HTTPError) else exc}")
                continue
            return Check(ordered[0], release, tuple(issues), tuple(exclusions))
        return Check(ordered[0] if ordered else None, None, tuple(issues), tuple(exclusions))

    def download(self, release, kind, storage, progress, cancelled):
        signed = verify_manifest(release.envelope, self.source["public_key"], release.version)
        if not eligible(signed.version, VERSION) or signed.version == VERSION:
            raise UpdateError("Only an eligible version newer than the installed application may be downloaded")
        package = signed.packages[kind]
        folder = Path(storage) / f"{signed.version}-{package.sha256}"
        folder.mkdir(parents=True, exist_ok=True)
        output = folder / package.name
        part = output.with_suffix(output.suffix + ".part")
        write_atomic(folder / MANIFEST, signed.envelope)
        if output.is_file():
            try:
                verify_file(output, package)
            except UpdateError:
                output.unlink()
        if not output.is_file():
            try:
                self.fetch(self.url(signed.version, package.name), part, package.size, progress, cancelled)
                if cancelled():
                    raise UpdateCancelled("Download paused. Its partial file can be resumed.")
                part.replace(output)
                try:
                    verify_file(output, package)
                except UpdateError:
                    output.unlink(missing_ok=True)
                    raise
            except (URLError, OSError) as exc:
                raise UpdateError(f"Download interrupted: {exc}. Retry to resume.") from None
        return output

    def fetch(self, address, part, size, progress, cancelled):
        offset = part.stat().st_size if part.is_file() else 0
        if offset > size:
            part.unlink()
            offset = 0
        if offset == size:
            return
        with self.open(address, {"Range": f"bytes={offset}-"} if offset else {}) as response:
            if response.status == 200:
                offset = 0
            elif not (offset and response.status == 206
                      and response.headers.get("Content-Range") == f"bytes {offset}-{size-1}/{size}"):
                raise UpdateError("Update server returned an invalid download range")
            remaining = size - offset
            length = response.headers.get("Content-Length")
            if length is not None and length != str(remaining):
                raise UpdateError("Download length does not match the signed manifest")
            with part.open("ab" if offset else "wb") as output:
                progress(offset, size)
                while remaining:
                    if cancelled():
                        raise UpdateCancelled("Download paused. Its partial file can be resumed.")
                    data = response.read(min(BLOCK, remaining))
                    if not data:
                        raise UpdateError("Download interrupted. Retry to resume.")
                    output.write(data)
                    remaining -= len(data)
                    progress(size - remaining, size)
            if response.read(1):
                part.unlink(missing_ok=True)
                raise UpdateError("Update server returned bytes beyond the signed size")


def write_atomic(path, data):
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
