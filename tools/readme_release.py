# Adaptive Resource Monitor
# Original developer: Sonja M Thomas
# Copyright 2010-2026 SLT Design Creations, LLC
# Licensed under the Design Creations Attribution-NonCommercial-ShareAlike License v1.0.
# See LICENSE.md for complete license terms.
# https://www.designcreations.us/

"""Refresh the public README from an already verified release."""
from base64 import b64decode, b64encode
import re
from urllib.parse import quote

from arm.update_release import MANIFEST, UpdateError
from arm.version import version_key

PUBLIC_VERSION = re.compile(r"<!-- arm-public-version: (v[0-9._a-z]+) -->")


def replace_block(readme, name, content):
    start, end = f"<!-- arm-{name}:start -->", f"<!-- arm-{name}:end -->"
    if readme.count(start) != 1 or readme.count(end) != 1:
        raise UpdateError(f"README public release block is invalid ({name})")
    before, rest = readme.split(start)
    _, after = rest.split(end)
    return f"{before}{start}\n{content}\n{end}{after}"


def render_readme(readme, client, release):
    version = release.version
    recorded = PUBLIC_VERSION.search(readme)
    if recorded and version_key(recorded[1]) > version_key(version):
        return readme
    releases = f"{client.base}/{client.repository}/releases"
    page = f"{releases}/tag/{quote(version, safe='')}"
    channel = {"alpha": "Alpha", "beta": "Beta", "rc": "Release Candidate", "stable": "Stable"}[version.rsplit("_", 1)[1]]
    badge = quote(version.replace("_", "__"), safe=".")
    stage = quote(channel.replace(" ", "_"), safe="_")
    header = f'''<!-- arm-public-version: {version} -->
<p align="center"><strong>{version} · {channel}</strong> · Windows x64 · DC-ANCSA v1.0</p>
<p align="center"><a href="{page}">Latest release</a> · <a href="#download">Download</a> · <a href="LICENSE.md">Read the license</a></p>
<p align="center">
  <a href="{page}"><img src="https://img.shields.io/badge/release-{badge}-176B6D" alt="Latest release {version}"></a>
  <a href="{page}"><img src="https://img.shields.io/badge/development-{stage}-A35C15" alt="{channel} development status"></a>
</p>'''
    downloads = f"""**{version} · {channel} · Windows x64**

| Download | Size | Use it for |
| --- | ---: | --- |
| [Windows installer]({client.url(version, release.packages['installed'].name)}) | {release.packages['installed'].size / 2**20:.1f} MiB | A per-user installation with Start menu access, optional startup and managed upgrades |
| [Portable ZIP]({client.url(version, release.packages['portable'].name)}) | {release.packages['portable'].size / 2**20:.1f} MiB | Running ARM from an extracted folder with portable updates |

[Release notes and downloads]({page}) · [All releases]({releases}) ·
[SHA-256 checksums]({client.url(version, 'SHA256SUMS.txt')}) ·
[Signed manifest]({client.url(version, MANIFEST)}) ·
[Public verification key]({client.url(version, 'arm-ed25519.pub')})"""
    readme = replace_block(readme, "public-header", header)
    return replace_block(readme, "public-downloads", downloads)


def update_public_readme(api, release):
    address = "/contents/README.md"
    existing = api.request(f"{address}?ref=main")
    readme = b64decode(existing["content"]).decode("utf-8")
    if "<!-- arm-public-header:start -->" not in readme:
        return
    newest = api.client.check("v0.0.0.0_alpha", "installed").release
    if newest is None or newest.version != release.version:
        return
    updated = render_readme(readme, api.client, release)
    if updated == readme:
        return
    api.request(address, {"branch": "main", "sha": existing["sha"],
                          "content": b64encode(updated.encode("utf-8")).decode("ascii"),
                          "message": f"Update public download links for {release.version}"}, "PUT")
    print(f"Updated the public README for {release.version}")
