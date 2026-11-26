# Application updates

In About, **Check for Updates** reads ARM's public Releases index. The panel
shows the highest published tag, the highest eligible verified version,
the time of the last successful check in the local timezone, package type and
size, verification status, progress and signed release notes. ARM defaults to
manual checks. Settings offers a startup check and periodic checks every
4 hours, 12 hours, day or week. A verified update uses the existing tray icon
for its notification. Checks and downloads run separately from collection.

**Download Update** stores the signed envelope and verified package in the
application's per-user updates directory. Cancel leaves a partial file. A retry
requests a byte range and validates the server's response. If the server
returns a complete response, ARM starts the file over. **Install Later**
keeps the package. **Install Update** asks for approval.

## Release contract

The configured source is the [ARM Releases page](https://phantom.zapto.org/gitea/sonja/Adaptive_Resource_Monitor/releases).
Each release provides arm-update-windows-x64.json with a canonical UTF-8
JSON manifest and a base64 Ed25519 signature. Protocol 1 includes the
application ID, Windows x64 architecture, exact VERSION.md value, Git commit,
Jenkins build number and release notes. Its installed and portable package
records carry the exact filename, byte count and SHA-256. The trusted public
key is embedded in both executables. A client accepts its own release channel
and eligible stable releases. A package for installation must be strictly newer.

## Installed and portable applications

The installed variant is identified from Windows' uninstall registration.
The maintenance launcher verifies the download, starts from a staged copy
outside the installed directory and waits for the monitor to close. The
monitor closes its collectors and drains pending history writes. The launcher
uses the native installer for an installed copy. For portable copies it
verifies and extracts the ZIP into staging on the same volume and replaces
only distribution-owned entries. Existing files outside those entries stay
in place. Before restarting ARM, the launcher verifies the new executable,
version and build metadata. The restarted process signals readiness.

## Recovery

The launcher creates a transaction journal before replacing files and retains
the prior application files until the new process confirms readiness. It
restores the previous executable and installer registration on failure. An
interrupted transaction can recover from the independently staged launcher
through the per-user Windows RunOnce entry. If a file is still locked, the
transaction and its backup remain available. The About panel reads the most
recent update result. Details are in maintenance.log and, for Setup,
installer.log under the transaction directory. Keep transaction files while an
installation is pending. Profiles, the Credential Manager, SSH trust and
telemetry history are outside the file-replacement transaction.
