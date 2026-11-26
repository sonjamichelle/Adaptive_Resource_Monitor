"""Freeze, compile and verify the ARM Windows release."""
import argparse
from datetime import datetime, timezone
from hashlib import file_digest
from importlib import metadata
import json
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from arm.version import NAME, VERSION
from arm.branding import (
    APPLICATION_ICON, APPLICATION_IMAGE, APPLICATION_LOGO, APP_MODEL_ID, BUNDLED_ASSETS,
    COPYRIGHT, DESCRIPTION, INSTALL_ID, PUBLISHER, SUPPORT_URL, WEBSITE,
)

STEM = f"AdaptiveResourceMonitor-{VERSION}-windows-x64"
EXE = "AdaptiveResourceMonitor.exe"
ICON = ROOT / APPLICATION_ICON
VERSION_FILE = """
VSVersionInfo(
  ffi=FixedFileInfo(filevers={numbers}, prodvers={numbers}, mask=0x3f,
    flags=0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0,0)),
  kids=[StringFileInfo([StringTable('040904B0',[
    StringStruct('CompanyName', {publisher!r}),
    StringStruct('FileDescription', {name!r}),
    StringStruct('FileVersion', {version!r}),
    StringStruct('InternalName', 'AdaptiveResourceMonitor'),
    StringStruct('LegalCopyright', {copyright!r}),
    StringStruct('OriginalFilename', {exe!r}),
    StringStruct('ProductName', {name!r}),
    StringStruct('ProductVersion', {version!r})
  ])]),VarFileInfo([VarStruct('Translation',[1033,1200])])]
)
"""


def run(args):
    result = subprocess.run(args, cwd=ROOT, check=False)
    print(f"{Path(args[0]).name} exit code {result.returncode}", flush=True)
    result.check_returncode()


def copy_notices(payload):
    notices = payload / "Third-party notices"
    notices.mkdir()
    for package in ("PySide6", "PySide6-Essentials", "PySide6-Addons", "shiboken6", "psutil",
                    "paramiko", "cryptography", "cffi", "bcrypt", "PyNaCl", "PyInstaller",
                    "setuptools", "nvidia-ml-py", "invoke", "pycparser"):
        try:
            distribution = metadata.distribution(package)
        except metadata.PackageNotFoundError:
            continue
        files = [entry for entry in (distribution.files or ())
                 if ".dist-info" in str(entry) and any(
                     token in entry.name.lower() for token in ("license", "copying", "notice"))]
        for index, entry in enumerate(files):
            shutil.copyfile(entry.locate(), notices / f"{package}-{index}-{entry.name}")
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        shutil.copyfile(python_license, notices / "Python-LICENSE.txt")
    shutil.copyfile(ROOT / "packaging" / "THIRD_PARTY.md", notices / "README.md")


def digest(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def build_info():
    data = {"built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "version": VERSION}
    try:
        for key, args in (("source_revision", ("rev-parse", "HEAD")),
                          ("source_modified", ("status", "--porcelain"))):
            result = subprocess.run(("git", *args), cwd=ROOT, text=True, capture_output=True)
            if result.returncode == 0:
                value = result.stdout.strip()
                data[key] = bool(value) if key == "source_modified" else value
    except FileNotFoundError:
        pass
    return data


def build(compiler, output):
    if platform.system() != "Windows" or struct.calcsize("P") != 8 or platform.machine().lower() not in ("amd64", "x86_64"):
        raise RuntimeError("Use native x64 Windows Python")
    match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)\.(\d+)_([a-z]+)", VERSION)
    if not match:
        raise ValueError("Unexpected ARM version format")
    numbers = tuple(int(value) for value in match.groups()[:4])
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="arm-release-") as temporary:
        temporary = Path(temporary)
        print(f"Build staging {temporary}", flush=True)
        version_file = temporary / "version.txt"
        version_file.write_text(
            VERSION_FILE.format(numbers=numbers, version=VERSION, name=NAME, exe=EXE,
                                publisher=PUBLISHER, copyright=COPYRIGHT),
            encoding="utf-8",
        )
        assets = [part for asset in BUNDLED_ASSETS for part in ("--add-data", f"{ROOT / asset};branding")]
        run([
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--noupx", "--windowed",
            "--name", "AdaptiveResourceMonitor", "--paths", str(ROOT),
            "--workpath", str(temporary / "work"), "--distpath", str(temporary / "dist"),
            "--specpath", str(temporary), "--version-file", str(version_file),
            "--manifest", str(ROOT / "packaging" / "windows.manifest"),
            "--icon", str(ICON),
            *assets,
            "--add-data", f"{ROOT / 'arm' / 'providers' / 'linux_probe.sh'};arm/providers",
            "--hidden-import", "pynvml", "--exclude-module", "tkinter",
            str(ROOT / "monitor.pyw"),
        ])
        payload = temporary / "dist" / "AdaptiveResourceMonitor"
        (payload / "VERSION.txt").write_text(VERSION + "\n", encoding="utf-8")
        (payload / "BUILD.json").write_text(json.dumps(build_info(), indent=2) + "\n", encoding="utf-8")
        for name in ("README.md", "SECURITY.md", "REMOTE_MONITORING.md", "CHANGELOG.md"):
            shutil.copyfile(ROOT / name, payload / name)
        if (ROOT / "LICENSE.md").is_file():
            shutil.copyfile(ROOT / "LICENSE.md", payload / "LICENSE.md")
        copy_notices(payload)
        setup_id = INSTALL_ID.replace("{", "{{", 1)
        run([
            str(compiler), "-qp", f"-O{temporary}", f"-DPayload={payload}",
            f"-DAppVersion={VERSION}", f"-DFileVersion={'.'.join(map(str, numbers))}",
            f"-DProduct={NAME}", f"-DExecutable={EXE}", f"-DAppIcon={ICON}",
            f"-DSetupId={setup_id}", f"-DArmPublisher={PUBLISHER}", f"-DArmCopyright={COPYRIGHT}",
            f"-DAppWebsite={WEBSITE}", f"-DAppSupport={SUPPORT_URL}", f"-DAppModelId={APP_MODEL_ID}",
            f"-DAppDescription={DESCRIPTION}", f"-DWizardImage={ROOT / APPLICATION_IMAGE}",
            f"-DWizardEmblem={ROOT / APPLICATION_LOGO}",
            str(ROOT / "packaging" / "setup.iss"),
        ])
        zip_path = temporary / f"{STEM}-portable.zip"
        with ZipFile(zip_path, "w", ZIP_DEFLATED, compresslevel=6) as package:
            for path in sorted(payload.rglob("*")):
                if path.is_file():
                    package.write(path, Path("AdaptiveResourceMonitor") / path.relative_to(payload))
        with ZipFile(zip_path) as package:
            if package.testzip() is not None:
                raise RuntimeError("Portable ZIP integrity check failed")
        checksums = []
        for source in (temporary / f"{STEM}-setup.exe", zip_path):
            expected = digest(source)
            destination = output / source.name
            copied = destination.with_suffix(destination.suffix + ".tmp")
            try:
                shutil.copyfile(source, copied)
                if digest(copied) != expected:
                    raise RuntimeError(f"Artifact copy failed verification for {source.name}")
                copied.replace(destination)
            finally:
                copied.unlink(missing_ok=True)
            checksums.append(f"{expected}  {source.name}")
        (output / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", encoding="ascii")
        for line in checksums:
            print(line)
        staged_bytes = sum(path.stat().st_size for path in temporary.rglob("*") if path.is_file())
    print(f"Removed build staging ({staged_bytes:,} bytes)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iscc", required=True, type=Path, help="Path to Inno Setup 7 ISCC.exe")
    parser.add_argument("--output", default=ROOT / "release", type=Path)
    args = parser.parse_args()
    build(args.iscc.resolve(strict=True), args.output.resolve())
