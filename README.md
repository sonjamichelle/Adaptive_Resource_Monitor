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

Monitor Machine selects the history shown in the hover and expanded
monitors. All Systems shows six independent graphs for every enabled
machine. Changing the monitor selection leaves the tray icon source as
configured in Settings. Hover machine and history selections save as you
change them. Network IN and OUT have configurable colors and share one
throughput scale per machine.

Open the About tab from the monitor
window or tray menu for build information, version history and support links.

The application version is defined in [VERSION.md](VERSION.md). Open **About →
Check for Updates** to check the public ARM Releases page. Downloading and
installing are separate actions. Settings can enable startup or periodic checks.
Both Windows x64 distributions use signed update metadata. See
[Update mechanism](UPDATE_MECHANISM.md) and [Release process](RELEASE_PROCESS.md).
See [BUILD.md](BUILD.md) for Windows build and verification commands,
[TELEMETRY_PROVIDERS.md](TELEMETRY_PROVIDERS.md) for metric definitions,
[REMOTE_MONITORING.md](REMOTE_MONITORING.md) for SSH setup, and
[IMPLEMENTATION_REPORT.md](IMPLEMENTATION_REPORT.md) for verification status.

