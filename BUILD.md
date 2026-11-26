# Windows x64 build

Use native x64 Python 3.12 and Inno Setup 7. From the repository in PowerShell:

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tests\windows_gui.py
.\.venv\Scripts\python.exe tools\build_windows.py --iscc 'C:\Program Files\Inno Setup 7\ISCC.exe'
.\.venv\Scripts\python.exe tests\windows_gui.py --package .\release
Get-FileHash .\release\*.zip, .\release\*.exe -Algorithm SHA256
~~~

The build script uses a disposable staging directory. It generates the product
version resource and invokes PyInstaller and Inno Setup. The final ZIP, installer
and SHA-256 manifest are written to release. Remove a one-off virtual environment
after validation when it is no longer needed.
The executable, installer, shortcuts, window and fallback tray icon share
the supplied ARM_Application.ico. Both distributions carry the app image,
emblem, Design Creations logo, change log, third-party notices and build
identity used by the About tab.

The installer is per user and permits choosing the install directory. Desktop
shortcut and autostart are optional. The Start Menu shortcut is installed.
Settings and history stay under the user's local app data across upgrades and
uninstall. Extract the portable ZIP before running AdaptiveResourceMonitor.exe.
Both packages contain their Python and Qt runtime.

The alpha artifacts are unsigned. An Authenticode signing and distribution
workflow requires the publisher's certificate and publication authorization.
