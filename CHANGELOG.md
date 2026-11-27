# Changelog

## v0.6.2.2_beta — 2026-11-26

- Promote Adaptive Resource Monitor to Beta after verifying the production self-update, restoration of local and remote monitoring, and signed same-number Beta discovery.
- The first Beta marks the completion of the original Windows monitoring scope. Beta development focuses on operational stability, monitoring accuracy, compatibility, and update reliability.

## v0.6.2.2_alpha — 2026-11-26

- Allow signed updates to the same or a more mature release channel, including Beta at the same numerical version as Alpha.
- Report when a release is excluded because of its numerical version or channel.

## v0.6.2.1_alpha — 2026-11-26

- Show verified update availability and installation readiness in the hover monitor, main window, and tray menu. Windows notifications can be turned off and repeat checks do not repeat them.
- Wait for ARM to finish saving settings and history and exit before replacing any application files. Show independent installation progress and report restart or recovery results.
- Restore the prior tray-only or expanded presentation after an update and let users open the changelog from the success confirmation.
- Published the signed Windows x64 installer and portable ZIP from Jenkins build #7.

## v0.6.1.1_alpha — 2026-11-26

- Added signed update discovery, verified downloads and authorized installation for installed and portable Windows x64 editions.
- Added Jenkins build, signing and archive automation and an explicitly invoked publication workflow for Gitea releases.

## v0.4.1.1_alpha — 2026-11-26

- Removed Aggregate - Peak and migrated saved selections to All Systems.
- Added an independent Tray icon machine setting, with Local Machine as the default and optional separate icons for individual machines.
- Preserved six independent resource graphs per monitored machine in All Systems, including network IN and OUT.

## v0.4.0.1_alpha — 2026-11-26

- Added independent machine sections in All Systems.
- Added independent network IN and OUT traces, readings and color preferences with a shared throughput scale.
- Fixed immediate persistence of the hover machine and history range across reopen, reconnect and restart.

## v0.2.0.0_alpha — 2026-11-26

- Added the Design Creations About tab with application and build details, version history, project links and third-party notices.
- Organized the tray menu around monitoring targets, visualization modes and application controls. The live history display remains the default, with a selectable branded icon.
- Applied the supplied ARM artwork to the Windows application, installer wizard, shortcuts and installed application metadata.

## v0.1.0.0_alpha

- Added the native Windows tray monitor, GPU-aware local telemetry, hover
  panel, expanded monitor, device selection, settings and resource history.
- Added independent Linux SSH targets with Windows Credential Manager,
  host key approval and reconnection.
- Added Windows x64 installer and portable build support and Windows validation.
