# Third-party runtime components

The Windows package includes CPython, Qt 6 and its PySide6 Python bindings,
psutil, Paramiko and its cryptographic dependencies, NVIDIA's NVML Python
bindings, and the PyInstaller bootloader. The NVIDIA display driver's NVML DLL
is provided by the driver. License text distributed by the dependency wheels
is included in this directory.

Qt is dynamically linked. The Qt DLLs and PySide bindings are separately
replaceable under the applicable Qt licenses. The exact tested versions and
rebuild instructions are in the ARM source repository. Qt source is available
from the [Qt source archive](https://download.qt.io/archive/qt/) and PySide
source from the [Qt for Python source archive](https://download.qt.io/official_releases/QtForPython/).
Python source is available from [python.org](https://www.python.org/downloads/source/).
