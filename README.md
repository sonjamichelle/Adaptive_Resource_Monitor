# Adaptive_Resource_Monitor

Adaptive Resource Monitor is a native Windows tray utility for CPU, GPU,
RAM, VRAM, storage and network history. It combines the six resources into
one dynamic icon by default. Click the icon to pin the monitor or open the
expanded window from its context menu. Windows may initially place the icon
in the taskbar overflow. Move it into the visible notification area for
continuous access.

Use Settings to switch between Overlay, Stacked and Composite, choose devices,
set sampling and graph options, or enable SQLite history. Use Manage Remote Targets
to add a Linux machine. A confirmed SSH key and working authentication are
required. The default configuration monitors only the local machine and keeps
history in memory.

The tray menu also offers an Application Icon display. The branded fallback
appears while monitoring initializes. In Settings → Tray Icon, choose the
machine for the primary icon. It defaults to Local Machine. Enable Separate
machine icons to also show icons for Local Machine and remote targets with
their tray option enabled.

Use the machine dropdown in either monitor or the tray's **Monitor Machine**
submenu to check the systems you want to display. The **All Systems** checkbox
selects or clears all enabled machines. With several machines selected, the
monitor shows separate graph sections in your saved order. Hidden machines
continue collecting telemetry. The primary tray icon keeps its configured
machine.

Drag machine headers in either monitor or rows in **Manage Remote Targets**
to change the shared order. Press Escape to cancel a drag. ARM saves each
drop and checkbox change immediately. Network IN and OUT have configurable
colors and share one throughput scale per machine.

Open the About tab from the monitor
window or tray menu for build information, version history and support links.

Signed update discovery supports gaining release maturity from v0.6.2.2_alpha
onward. Production acceptance and promotion status are recorded in the
implementation report. [Public releases](https://phantom.zapto.org/gitea/sonja/Adaptive_Resource_Monitor/releases)

The first Beta covers the original Windows monitoring scope, including
remote Linux monitoring. Beta development prioritizes stability, performance,
hardware and remote compatibility, security, and update and installer
reliability.

The application version is defined in [VERSION.md](VERSION.md). Open **About →
Check for Updates** to check the public ARM Releases page. Downloading and
installing are separate actions. Under **Settings → General**, enable
**Check for updates at startup** or use **Check for updates periodically**
to choose Off, every 4 hours, every 12 hours, daily, or weekly.
Both Windows x64 distributions use signed update metadata. See
[Update mechanism](UPDATE_MECHANISM.md) and [Release process](RELEASE_PROCESS.md).
See [BUILD.md](BUILD.md) for Windows build and verification commands,
[TELEMETRY_PROVIDERS.md](TELEMETRY_PROVIDERS.md) for metric definitions,
[REMOTE_MONITORING.md](REMOTE_MONITORING.md) for SSH setup, and
[IMPLEMENTATION_REPORT.md](IMPLEMENTATION_REPORT.md) for verification status.

