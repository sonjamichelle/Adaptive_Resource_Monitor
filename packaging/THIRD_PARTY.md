# Third-party runtime components

The Windows package includes CPython, Qt 6 and its PySide6 Python bindings,
psutil, Paramiko and its cryptographic dependencies, NVIDIA's NVML Python
bindings, Tcl/Tk for the maintenance window, and the PyInstaller bootloader.
The NVIDIA display driver's NVML DLL
is provided by the driver. License text distributed by the dependency wheels
is included in this directory. NVIDIA's Python wrapper carries its BSD notice
in its source header. Setup and the portable archive include that notice
separately. [NVIDIA Python wrapper source distribution](https://pypi.org/project/nvidia-ml-py/13.615.71/#files)

DC-ANCSA applies to original ARM material. Bundled dependencies remain under
their upstream terms. The notice files include the PSF and Tk terms, the
PyInstaller bootloader exception, Paramiko's LGPL terms, and the distinct
notices for the cryptography, NaCl, bcrypt, CFFI and other Python components.
[Paramiko source distribution](https://pypi.org/project/paramiko/4.0.0/#files)

The OpenSSL license text is identical in the two bundled runtime versions.
The Microsoft runtime stays under Microsoft's applicable redistribution
terms. The SQLite library distributed with CPython is public domain.
[OpenSSL 3.0.16](https://github.com/openssl/openssl/tree/openssl-3.0.16)
[OpenSSL 4.0.2](https://github.com/openssl/openssl/tree/openssl-4.0.2)
[Tcl 8.6.15](https://github.com/tcltk/tcl/tree/core-8-6-15)
[SQLite copyright](https://www.sqlite.org/copyright.html)

The Qt and PySide 6.11.2 runtime is distributed under the GNU Lesser General
Public License v3. The accompanying LGPL v3 and GPL v3 texts are in the
Third-party notices directory. Qt is dynamically linked and the Qt DLLs
and PySide bindings can be replaced with compatible modified copies.
Users retain their rights under these licenses, including reverse
engineering to debug such modifications. ARM uses native Windows input.
The GPLv3 or commercial Qt Virtual Keyboard plugin is omitted.

Corresponding upstream sources and build instructions are available for
[Qt 6.11.2](https://download.qt.io/archive/qt/6.11/6.11.2/single/qt-everywhere-src-6.11.2.tar.xz)
and [PySide and Shiboken 6.11.2](https://github.com/pyside/pyside-setup/tree/v6.11.2).
The complete Qt license texts come from the
[Qt 6.11.2 source](https://code.qt.io/cgit/qt/qtbase.git/tree/LICENSES?h=v6.11.2).
CPython source is available from [python.org](https://www.python.org/downloads/source/).
