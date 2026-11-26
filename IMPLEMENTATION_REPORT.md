# Adaptive Resource Monitor implementation report

## v0.2.0.0_alpha — Design Creations branding

The Feature counter advanced from 1 to 2 for the new About tab and selectable
tray display. The About tab and tray menu use the same authoritative version
source as the executable and installer.

The About design follows the inspected Ink & Iron Workshop About screen and
installed UI components, including the application and company graphics
flanking a centered serif title, compact information group, View Details
control and inline changelog. Patch Studio and Adaptive Maintenance source
provided additional read-only references for document navigation, attribution
and Windows application identity. Adaptive File Transfer corroborated the
attribution. The Workshop source checkout was unavailable locally. The
inspected Workshop UI and peer references did not expose a tray menu to mirror,
so ARM applies their palette and menu spacing to the requested commands.

ARM uses the supplied 1040 × 1069 application image, transparent emblem,
Design Creations logo and nine-size ICO as its canonical runtime assets.
The original compact icon variants remain source artwork. The Windows
executable, installer and shortcut definitions share the branded icon and
application identity. About includes the bundled Project Guide and a verified
public contact link. The configured Git origin's web view returned HTTP 404
to an anonymous request. ARM has no declared software license or update
channel. Dependency notices remain available. [Design Creations](https://www.designcreations.us/) · [Contact & Support](https://www.designcreations.us/contact/index.php)

### Branding validation

All 13 automated tests passed. Native Qt runs on a private Windows desktop
passed at 100% and 150% scale. They checked the About tab, its document and
details controls, website and support URL routing, tray menu navigation,
monitor pinning, local and remote target selection, and all four tray
displays. The runs observed live local telemetry and loopback SSH telemetry.
The normal graph replaced the branded startup fallback when data arrived.
All nine ICO frames had transparent and opaque pixels, with effectively
transparent corners. The visible artwork and installer wizard were reviewed
from private-desktop captures.

Both x64 packages passed their SHA-256 checks. The embedded icon groups
contained all nine sizes. The portable app and installed app opened with
the branded native window icon and shut down cleanly. A disposable
v0.1.0.0_alpha installation was upgraded to v0.2.0.0_alpha, reinstalled
and uninstalled. The checks verified the company name, support and website
entries in the installed application registry and preserved sample
settings, a machine profile with its credential reference, and history.
Shortcut definitions share the executable icon and AppUserModelID.
Visual verification in the active Explorer notification area, taskbar,
Task Manager and desktop shortcut was outside the isolated test.

| Final release file | Bytes | SHA-256 |
| --- | ---: | --- |
| Windows x64 installer | 44,498,649 | `804f6c3d594a71a01d7b44137758095e42f65f5ec2e062695db48a2f1e2b59e2` |
| Windows x64 portable ZIP | 58,353,462 | `3e441381516a223516b778a306ee1e881deed4b9b343197d04d769b7364a76ea` |

Cleanup removed the temporary installer and dependency staging, four build
staging directories, disposable Windows installs, temporary profiles and
SSH fixtures, private-desktop captures and superseded packages. Measured
file sizes reclaimed totaled 1,979,949,758 bytes (1.84 GiB), excluding
short-lived unit-test scratch files. The project retains the current
installer, portable ZIP and checksum manifest as release deliverables,
along with the source, supplied artwork, documentation and maintained tests.

## v0.1.0.0_alpha — Initial implementation

## Implementation matrix

| Requirement | Implementation | Automated evidence | Native or live evidence and limits |
| --- | --- | --- | --- |
| Dynamic Windows tray and Overlay, Stacked, Composite | Implemented using QSystemTrayIcon and QPainter | Resource normalization and peak aggregation tests | Native Qt builds distinct icon images for all three modes. Explorer registration and recovery need a live taskbar. |
| Custom popup, sizing, dismissal and pinning | Implemented with Windows cursor position and Qt's native notification-area rectangle | Hover state, dismissal, placement and negative-coordinate tests | Popup, six graphs and pinning exercised on a private desktop. Actual pointer movement over an Explorer icon, desktop sleep/resume, and physical mixed-DPI taskbars remain open. |
| Expanded monitor, ranges and multiple machines | Implemented with resource charts, per-device detail, current and history statistics, connection state and timestamps | History and machine-peak tests | Expanded window, live values and device selection exercised. Archived statistics use retained plot observations for long selections. |
| Windows CPU and memory | Implemented using timed CPU deltas, physical and logical topology, memory, commit and pagefile | First-sample and native provider tests | Verified workstation telemetry. Windows CPU temperature and power are unsupported in this alpha. |
| AMD, Intel, NVIDIA and dedicated VRAM | Implemented with DXGI PCI identity, native WDDM engine and memory counters and NVIDIA NVML sensors | Engine aggregation, valid zero, matched capacity and sampled provider tests | AMD Radeon 780M and NVIDIA RTX 5050 Laptop GPU detected with native readings. No Intel GPU was available. AMD and Intel use WDDM counters on Windows and expose only the features supplied by those counters. Vendor clock, thermal, fan and power readings for these two vendors on Windows are deferred. |
| Storage and network | Implemented with whole physical disk counters, mode selection, directional network data and default physical-adapter inclusion | Counter reset and network-selection fixtures | Two physical drives and active network throughput verified. No live 10 GbE, VPN or storage pool validation. |
| SSH Linux and connection management | Implemented with one persistent channel per target, password and key authentication, host verification, reconnect and status | Loopback password and encrypted private-key tests, unknown and changed keys, reconnect after loss, and Linux counter fixtures | Windows loopback sessions exercised. Live Linux validation on Linux target A and Linux target B requires authorized connection details. Their hosts and credentials were neither inferred nor accessed. |
| Credentials and settings | Implemented with Windows Credential Manager references and atomic per-user settings | Credential round trip, namespace validation and settings persistence | Settings and target operations exercised on the isolated Windows desktop. |
| Independent collection and optional history | Implemented with collector and SQLite workers, in-memory rings, gap detection, batching, retention and clear | Worker stop, ring, SQLite flush/read/clear tests | Tested locally and with the loopback targets. Maximum database size is enforced periodically. SQLite working files can temporarily exceed the target. |
| Startup and shutdown | Implemented with a per-user startup toggle, clean exit and independent monitor window | Worker shutdown and SQLite drain tests | Native startup and shutdown exercised. Windows sign-in autostart remains a live acceptance check. |
| Windows x64 distribution | Implemented with a PyInstaller payload, Inno Setup installer and portable ZIP | Build verifies archive integrity and artifact hashes | See package validation below. Windows 10 and ARM64 were outside workstation validation. |
| Remote Windows and optional agent | Provider interface and profile status implemented. Transport and agent deferred. | Unsupported status surfaced by the UI | No remote Windows telemetry claim or deployment. |

## Workstation evidence

Native validation uses a private Windows desktop without switching the author’s
desktop or sending it input. The workstation is Windows 11 x64 build 26300.
The application registered Qt tray objects. The private desktop has no Explorer
notification area and returned no icon rectangle. Qt’s Windows backend calls
Shell_NotifyIconGetRect and handles the shell's TaskbarCreated message. These
source paths do not constitute a live shell-restart result. [Qt Windows tray backend](https://github.com/qt/qtbase/blob/v6.11.2/src/plugins/platforms/windows/qwindowssystemtrayicon.cpp)

The automated suite passed 13 tests on November 26, 2026. A Windows Bash
protocol check produced two delimited responses from one process. Live
procfs, sysfs and hardware validation is represented separately in the matrix.

The native Windows GUI suite passed at 100% scale and its smoke run passed at
150% scale. The full run produced distinct Overlay, Stacked and Composite
icon images and exercised separate and consolidated tray objects, popup
pinning, expanded graphs, settings and target management. The two concurrent
SSH fixtures delivered 13 and 7 readings. The AMD Radeon 780M and NVIDIA
GeForce RTX 5050 Laptop GPU both supplied dedicated memory readings. The
full run also observed AMD engine activity and NVIDIA temperature and power.

## Resource consumption

Measurements use process CPU time and resident memory in the native private
desktop. Total-machine CPU is normalized by 16 logical processors. Loopback
targets use an authenticated test server on the same workstation and supply
fixture frames. These results cover the application and same-process loopback
fixture threads in the remote scenarios.

| Scenario | CPU, entire workstation | CPU, one logical processor | Working set |
| --- | ---: | ---: | ---: |
| Local tray only | 0.106% | 1.693% | 138.53 MiB |
| Pinned popup | 0.220% | 3.516% | 140.16 MiB |
| Expanded window | 0.342% | 5.469% | 143.12 MiB |
| One SSH loopback target | 0.155% | 2.474% | 146.64 MiB |
| Two SSH loopback targets | 0.146% | 2.344% | 147.08 MiB |
| Two manually disconnected targets | 0.098% | 1.562% | 148.02 MiB |

Each row is a 12-second observation. Local tray-only collection ran at one
second and measured below 1% of total workstation CPU capacity. Explorer's
work and long-duration memory growth require separate measurement.

## Distribution and cleanup

The original release contained the x64 installer, the portable ZIP and their
SHA-256 manifest. The alpha artifacts were unsigned. Signing, live Explorer
validation, real remote Linux validation and extended-duration performance
characterization are outstanding production acceptance items.

PyInstaller 6.22.3 froze the application with its Python and Qt runtime.
Inno Setup 7.1.1 compiled the installer. Both PE headers identify x64.
The portable archive passed its CRC check and contains the Qt Windows plugin
and Linux telemetry program. The supplied ARM icon is in the application
and installer resources.

The final portable and installed builds each opened twice on an isolated
Windows desktop. Closing the monitor window left the tray process running.
Both processes exited cleanly when their private message loops were told to
quit. A silent installation, same-version reinstall and uninstall each
returned code 0. Their temporary profile, settings and history test files
were preserved through reinstall and uninstall. Launching on a
Python-free Windows system and a version-to-version upgrade remain untested.

| Final release file | Bytes | SHA-256 |
| --- | ---: | --- |
| Windows x64 installer | 40,558,009 | `b6d0a56975311b8c26eb1a67542dbb88cb6f566232bdef5bbbd669b8a9e8c239` |
| Windows x64 portable ZIP | 56,159,793 | `6b39ccac9db4f4dfb46f8904723967724b0405b986db6d508d9b6fc2249da41f` |

Cleanup removed the disposable installation and uninstall registration,
portable extractions, private-desktop test profiles and logs, SQLite fixtures,
SSH fixtures and test credentials, compiler and dependency staging, failed
and successful build intermediates, and superseded packages. Measured file
sizes reclaimed total 1,142,127,048 bytes (1.06 GiB). This excludes short-lived
unit-test fixtures and the automatically deleted build attempt whose size
was unmeasured. That milestone retained the verified installer, portable
ZIP and SHA-256 manifest until the branding release superseded them.
