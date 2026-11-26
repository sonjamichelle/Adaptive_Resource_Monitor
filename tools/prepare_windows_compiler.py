"""Stage the pinned Windows compiler without changing the agent's execution policy."""
from hashlib import file_digest
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.request import urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from windows_gui import start_isolated

NAME = "innosetup-7.1.1-x64.exe"
ORIGIN = f"https://github.com/jrsoftware/issrc/releases/download/is-7_1_1/{NAME}"
SHA256 = "8a5a6711c3766a6e5fb74f280ba0e3551e719ce94538d901fdbd1f8f9920b3f0"


def main():
    scratch = ROOT / ".ci"
    installer = scratch / NAME
    destination = scratch / "inno"
    with urlopen(ORIGIN, timeout=60) as response, installer.open("xb") as output:
        shutil.copyfileobj(response, output)
    with installer.open("rb") as source:
        if file_digest(source, "sha256").hexdigest() != SHA256:
            raise RuntimeError("Inno Setup download SHA-256 mismatch")
    signature = subprocess.check_output(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command",
         f"(Get-AuthenticodeSignature -LiteralPath '{NAME}').Status.ToString()"],
        cwd=scratch, text=True,
    ).strip()
    if signature != "Valid":
        raise RuntimeError(f"Inno Setup Authenticode verification failed: {signature}")
    code = start_isolated(
        [str(installer), "/PORTABLE=1", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", f"/DIR={destination}"],
        f"ARM_Compiler_{uuid4().hex[:10]}", timeout=90,
    )
    if code or not (destination / "ISCC.exe").is_file():
        raise RuntimeError(f"Portable Inno Setup staging failed: exit {code}")
    print("Inno Setup 7.1.1 x64 hash, Authenticode and native portable staging verified.")


if __name__ == "__main__":
    main()
