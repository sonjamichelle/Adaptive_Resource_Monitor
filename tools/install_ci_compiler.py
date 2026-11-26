"""Extract the signed Inno compiler through its native portable installer."""
from pathlib import Path
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from windows_gui import start_isolated


if __name__ == "__main__":
    installer, destination = (Path(value).resolve() for value in sys.argv[1:])
    raise SystemExit(start_isolated(
        [str(installer), "/PORTABLE=1", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", f"/DIR={destination}"],
        f"ARM_Compiler_{uuid4().hex[:10]}", timeout=90,
    ))
