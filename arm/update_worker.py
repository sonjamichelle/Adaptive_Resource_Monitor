"""Independent Windows updater. Transaction data never includes the ARM user profile."""
import argparse
import json
import logging
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
from time import monotonic, sleep
from uuid import uuid4
import winreg
from zipfile import ZipFile

import pefile
import psutil

from .branding import INSTALL_ID, PUBLISHER
from .config import data_path
from .update_client import write_atomic
from .update_release import MANIFEST, UpdateError, eligible, source_config, verify_file, verify_manifest
from .version import VERSION, read_version, version_key

EXE = "AdaptiveResourceMonitor.exe"
WORKER = "AdaptiveResourceMonitorMaintenance.exe"
MANAGED = {EXE, WORKER, "_internal", "Third-party notices", "VERSION.md", "VERSION.txt", "BUILD.json",
           "README.md", "SECURITY.md", "REMOTE_MONITORING.md", "CHANGELOG.md", "LICENSE.md"}
UNINSTALL_KEY = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{INSTALL_ID}_is1"
RUN_ONCE = r"Software\Microsoft\Windows\CurrentVersion\RunOnce"
UNINSTALLER = re.compile(r"unins[0-9]{3}\.(?:exe|dat|msg)", re.I)
ACK = "ARM_UPDATE_READY"
LOG = logging.getLogger(__name__)


def safe_entry(path):
    if path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise UpdateError(f"Update cannot replace the link or junction {path.name}")


def registered_view(target):
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY, 0, winreg.KEY_READ | view) as key:
                location = winreg.QueryValueEx(key, "InstallLocation")[0]
                if location and Path(location).resolve() == target:
                    return view
        except FileNotFoundError:
            continue
    return None


def verify_executable(path, version):
    pe = pefile.PE(str(path), fast_load=True)
    try:
        pe.parse_data_directories([pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]])
        table = next(node.StringTable[0].entries for group in pe.FileInfo for node in group if hasattr(node, "StringTable"))
        numeric = version_key(version)[:4]
        fixed = pe.VS_FIXEDFILEINFO[0]
        product = (fixed.ProductVersionMS >> 16, fixed.ProductVersionMS & 65535,
                   fixed.ProductVersionLS >> 16, fixed.ProductVersionLS & 65535)
        file = (fixed.FileVersionMS >> 16, fixed.FileVersionMS & 65535,
                fixed.FileVersionLS >> 16, fixed.FileVersionLS & 65535)
        if (pe.FILE_HEADER.Machine != 0x8664 or table[b"ProductVersion"].decode().strip() != version
                or table[b"FileVersion"].decode().strip() != version
                or table[b"CompanyName"].decode().strip() != PUBLISHER or product != numeric or file != numeric):
            raise UpdateError(f"Executable identity or version is inconsistent: {path.name}")
    finally:
        pe.close()


def managed_entries(target, installed):
    return sorted(entry.name for entry in target.iterdir()
                  if entry.name in MANAGED or (installed and UNINSTALLER.fullmatch(entry.name)))


def unpack_portable(artifact, output, version):
    seen, total = set(), 0
    with ZipFile(artifact) as archive:
        if len(archive.infolist()) > 10_000:
            raise UpdateError("Portable package contains too many entries")
        for member in archive.infolist():
            path = PurePosixPath(member.filename)
            parts = path.parts
            if (len(parts) < 2 or path.is_absolute() or parts[0] != "AdaptiveResourceMonitor"
                    or parts[1] not in MANAGED or any(not part or part in (".", "..") or part.endswith((".", " "))
                    or re.search(r'[<>:"\\|?*\x00-\x1f]', part) or Path(part).is_reserved() for part in parts)
                    or stat.S_ISLNK(member.external_attr >> 16)):
                raise UpdateError("Portable package contains an unexpected or unsafe path")
            key = str(path).casefold()
            total += member.file_size
            if key in seen or total > 2 * 1024**3:
                raise UpdateError("Portable package exceeds extraction limits or duplicates a path")
            seen.add(key)
            destination = output.joinpath(*parts[1:])
            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, destination.open("xb") as target:
                    shutil.copyfileobj(source, target, 256 * 1024)
    verify_payload(output, version)


def verify_payload(directory, version):
    verify_executable(directory / EXE, version)
    verify_executable(directory / WORKER, version)
    if any(read_version(path) != version for path in (
        directory / "VERSION.md", directory / "VERSION.txt", directory / "_internal" / "VERSION.md"
    )):
        raise UpdateError("Packaged version documents are inconsistent")
    if json.loads((directory / "BUILD.json").read_bytes()).get("version") != version:
        raise UpdateError("Packaged build metadata is inconsistent")


def set_status(plan_dir, state, message):
    write_atomic(plan_dir / "status.json", json.dumps({"state": state, "message": message}).encode())
    LOG.info("%s. %s", state, message)


def prepare(release, artifact, target, kind, root):
    config = source_config()
    signed = verify_manifest(release.envelope, config["public_key"], release.version)
    if not eligible(signed.version, VERSION) or signed.version == VERSION:
        raise UpdateError("Maintenance supports eligible upgrades only")
    verify_file(artifact, signed.packages[kind])
    plan_dir = root / "transactions" / uuid4().hex
    plan_dir.mkdir(parents=True)
    plan = plan_dir / "plan.json"
    parent = psutil.Process()
    data = {"target": str(target), "artifact": str(Path(artifact).resolve()), "kind": kind,
            "old": VERSION, "new": signed.version, "parent": parent.pid, "created": parent.create_time()}
    write_atomic(plan, json.dumps(data).encode())
    write_atomic(plan_dir / MANIFEST, signed.envelope)
    worker = plan_dir / WORKER
    shutil.copy2(target / WORKER, worker)
    verify_executable(worker, VERSION)
    subprocess.Popen([str(worker), str(plan)], cwd=plan_dir, creationflags=subprocess.CREATE_NO_WINDOW)
    return plan_dir


def snapshot_registry(view):
    if view is None:
        return []
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY, 0, winreg.KEY_READ | view) as key:
        return [winreg.EnumValue(key, index) for index in range(winreg.QueryInfoKey(key)[1])]


def restore_registry(view, previous):
    if view is None:
        return
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY, 0, winreg.KEY_WRITE | winreg.KEY_READ | view) as key:
        names = [winreg.EnumValue(key, index)[0] for index in range(winreg.QueryInfoKey(key)[1])]
        keep = {name.casefold() for name, _, _ in previous}
        for name in names:
            if name.casefold() not in keep:
                winreg.DeleteValue(key, name)
        for name, value, kind in previous:
            winreg.SetValueEx(key, name, 0, kind, value)


def recovery_entry(plan_dir, add):
    name = "*ARMUpdate-" + plan_dir.name
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_ONCE) as key:
        if add:
            command = subprocess.list2cmdline([str(plan_dir / WORKER), str(plan_dir / "plan.json"), "--recover"])
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass


def copy_managed(source, target):
    safe_entry(source)
    if source.is_dir():
        for item in source.rglob("*"):
            safe_entry(item)
        shutil.copytree(source, target)
    else:
        shutil.copy2(source, target)


def remove_managed(path):
    if path.exists():
        safe_entry(path)
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def wait_parent(data, target, plan_dir):
    limit = monotonic() + 75
    while monotonic() < limit:
        try:
            parent = psutil.Process(data["parent"])
            if abs(parent.create_time() - data["created"]) > 0.01:
                return
            if Path(parent.exe()).resolve() != target / EXE:
                raise UpdateError("The requesting process is not this ARM executable")
        except psutil.NoSuchProcess:
            return
        if (plan_dir / "abort").exists():
            raise UpdateError("Installation canceled before touching the application")
        sleep(.25)
    raise UpdateError("The application did not exit. Installation was deferred.")


def restart(target, version, plan_dir):
    ready = plan_dir / "ready.json"
    child = subprocess.Popen([str(target / EXE)], cwd=target, env=dict(os.environ, **{ACK: str(ready)}))
    try:
        deadline = monotonic() + 35
        while monotonic() < deadline and child.poll() is None:
            if ready.is_file():
                if json.loads(ready.read_bytes()) == {"version": version, "pid": child.pid}:
                    return
                raise UpdateError("The restarted application reported a different version")
            sleep(.2)
        raise UpdateError("The restarted application did not confirm initialization")
    except BaseException:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=15)
        raise


def rollback(target, work, journal):
    originals = set(journal["originals"])
    backup = work / "previous"
    for name in managed_entries(target, journal["view"] is not None):
        if name not in originals or (backup / name).exists():
            remove_managed(target / name)
    for original in backup.iterdir():
        original.replace(target / original.name)
    restore_registry(journal["view"], journal["registration"])
    verify_executable(target / EXE, journal["old"])


def transact(plan_dir, recover=False):
    data = json.loads((plan_dir / "plan.json").read_bytes())
    target = Path(data["target"]).resolve(strict=True)
    work = target / (".arm-update-" + plan_dir.name)
    checkpoint = plan_dir / "journal.json"
    if not eligible(data["new"], VERSION) or data["old"] != VERSION or data["new"] == VERSION:
        raise UpdateError("Update plan does not describe an upgrade from this maintenance version")
    safe_entry(target)
    if recover:
        journal = json.loads(checkpoint.read_bytes())
        if journal.get("committed"):
            remove_managed(work)
            recovery_entry(plan_dir, False)
            return
        rollback(target, work, journal)
        remove_managed(work)
        recovery_entry(plan_dir, False)
        set_status(plan_dir, "rolled_back", "Restored the previous application after an interrupted installation.")
        restart(target, data["old"], plan_dir)
        return
    release = verify_manifest((plan_dir / MANIFEST).read_bytes(), source_config()["public_key"], data["new"])
    view = registered_view(target)
    kind = "installed" if view is not None else "portable"
    if data["kind"] != kind:
        raise UpdateError("The Windows installation type has changed")
    artifact = Path(data["artifact"])
    package = release.packages[kind]
    verify_file(artifact, package)
    verify_executable(target / EXE, data["old"])
    work.mkdir()
    previous = work / "previous"
    previous.mkdir()
    try:
        payload = work / "next"
        payload.mkdir()
        if kind == "portable":
            unpack_portable(artifact, payload, release.version)
        else:
            shutil.copy2(artifact, payload / package.name)
            verify_file(payload / package.name, package)
            verify_executable(payload / package.name, release.version)
        set_status(plan_dir, "waiting", "Verified the update. Waiting for the monitor to close and save its history.")
        wait_parent(data, target, plan_dir)
        verify_file(artifact, package)
        for name in managed_entries(target, view is not None):
            safe_entry(target / name)
        originals = managed_entries(target, view is not None)
        journal = {"originals": originals, "view": view, "registration": snapshot_registry(view), "old": data["old"]}
        if kind == "installed":
            for name in originals:
                copy_managed(target / name, previous / name)
        write_atomic(checkpoint, json.dumps(journal).encode())
        recovery_entry(plan_dir, True)
        set_status(plan_dir, "installing", "Installing the verified update.")
        try:
            if kind == "portable":
                for name in originals:
                    (target / name).replace(previous / name)
                for entry in payload.iterdir():
                    entry.replace(target / entry.name)
            else:
                setup = payload / package.name
                verify_file(setup, package)
                subprocess.run([str(setup), "/ARMUPDATE=1", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                                "/NOCLOSEAPPLICATIONS", "/NOICONS", "/TASKS=", f"/DIR={target}",
                                f"/LOG={plan_dir / 'installer.log'}"], cwd=payload, check=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY, 0, winreg.KEY_READ | view) as key:
                    if winreg.QueryValueEx(key, "DisplayVersion")[0] != release.version:
                        raise UpdateError("Windows installer registration did not report the expected version")
            verify_payload(target, release.version)
            build = json.loads((target / "BUILD.json").read_bytes())
            if (build.get("source_revision"), build.get("jenkins_build")) != (release.commit, release.build):
                raise UpdateError("Installed build identity does not match the signed manifest")
            restart(target, release.version, plan_dir)
        except Exception as exc:
            rollback(target, work, journal)
            set_status(plan_dir, "rolled_back", f"Installed update failed. Restored the previous application. {exc}")
            recovery_entry(plan_dir, False)
            restart(target, data["old"], plan_dir)
            return
        journal["committed"] = True
        write_atomic(checkpoint, json.dumps(journal).encode())
        recovery_entry(plan_dir, False)
        set_status(plan_dir, "complete", f"Updated and restarted Adaptive Resource Monitor {release.version}.")
    finally:
        if not checkpoint.exists() or json.loads(checkpoint.read_bytes()).get("committed") or (
            (plan_dir / "status.json").exists() and json.loads((plan_dir / "status.json").read_bytes())["state"] == "rolled_back"
        ):
            remove_managed(work)


def signal_ready():
    if value := os.environ.pop(ACK, None):
        path = Path(value)
        transactions = data_path() / "updates" / "transactions"
        if path.name == "ready.json" and path.parent.parent.resolve() == transactions.resolve():
            write_atomic(path, json.dumps({"version": VERSION, "pid": os.getpid()}).encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--recover", action="store_true")
    args = parser.parse_args()
    plan_dir = args.plan.resolve().parent
    expected = (data_path() / "updates" / "transactions").resolve()
    if args.plan.name != "plan.json" or plan_dir.parent != expected or not re.fullmatch(r"[0-9a-f]{32}", plan_dir.name):
        return 2
    logging.basicConfig(filename=plan_dir / "maintenance.log", level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(message)s")
    try:
        transact(plan_dir, args.recover)
    except Exception as exc:
        LOG.exception("Maintenance failed")
        set_status(plan_dir, "failed", str(exc))
        return 1
    return 0
