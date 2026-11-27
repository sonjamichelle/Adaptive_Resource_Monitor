# Application updates

In About, **Check for Updates** reads ARM's public Releases index. The panel
shows the highest published tag, the highest eligible verified version,
the time of the last successful check in the local timezone, package type and
size, verification status, progress and signed release notes. ARM defaults to
manual checks. Settings offers a startup check and periodic checks every
4 hours, 12 hours, day or week. A verified update uses the existing tray icon
for its Windows notification once per verified version, including across
restarts. **Show Windows update notifications** controls these transient
messages. Verified releases also appear below the hover monitor's machine
and connection controls, in the expanded window and below the tray menu's
version. These entries open the About tab. No row appears when there is no
eligible verified update. Checks and downloads run separately from collection.

**Download Update** stores the signed envelope and verified package in the
application's per-user updates directory. Cancel leaves a partial file. A retry
requests a byte range and validates the server's response. If the server
returns a complete response, ARM starts the file over. **Install Later**
keeps the package and its ready-to-install notice. **Install Update** asks for
approval.

Starting with v0.8.3.3_beta, the signed release notes include the SHA-256
of the exact source license. When that hash matches the installed license,
the usual install confirmation opens. When the license differs, ARM
retrieves the file from the version's Gitea tag, verifies the signed hash
and shows the complete terms for explicit acceptance before shutdown.
Cancel leaves the verified package available. Earlier clients retain their
existing signed update confirmation when first upgrading to this version.

## Release contract

The configured source is the [ARM Releases page](https://phantom.zapto.org/gitea/sonja/Adaptive_Resource_Monitor/releases).
Each release provides arm-update-windows-x64.json with a canonical UTF-8
JSON manifest and a base64 Ed25519 signature. Protocol 1 includes the
application ID, Windows x64 architecture, exact VERSION.md value, Git commit,
Jenkins build number and release notes. Its installed and portable package
records carry the exact filename, byte count and SHA-256. The trusted public
key is embedded in both executables.

Starting with v0.6.2.2_alpha, a client accepts its own release channel and more
mature channels. Supported channels in order are Alpha, Beta, Release
Candidate (`rc`) and Stable. The numerical version must be at least as high
as the installed version. Maturity breaks ties at identical numerical
versions. A verified identical release can confirm that ARM is current.
Downloading and installing require a strictly newer version. About reports
version and channel exclusions separately from verification failures.

## Installed and portable applications

The installed variant is identified from Windows' uninstall registration.
The maintenance launcher verifies the download, starts from a staged copy
outside the installed directory. It verifies the requesting process's
executable path, PID and creation time. ARM saves its presentation, removes
its tray icons, stops workers and drains pending history writes. The launcher
requires ARM's shutdown acknowledgement and waits for the process to exit
before replacing files. It reports progress in its own branded window.
A directly launched installer asks the user to close ARM if the destination
executable is in use. The launcher
uses the native installer for an installed copy. For portable copies it
verifies and extracts the ZIP into staging on the same volume and replaces
only distribution-owned entries. Existing files outside those entries stay
in place. Before restarting ARM, the launcher verifies the new executable,
version and build metadata. The launcher restarts ARM in the invoking user
session with the previous tray-only or expanded presentation. The restarted
process signals readiness before ARM reports success and offers the changelog.
Opening the changelog clears the transient success banner and retains the
completion receipt.
An upgrade initiated by v0.6.1.1 uses that version's launcher and progress
behavior. The newer application still reads its completion receipt.

## Recovery

The launcher creates a transaction journal before replacing files and retains
the prior application files until the new process confirms readiness. It
restores the previous executable and installer registration on failure. An
interrupted transaction can recover from the independently staged launcher
through the per-user Windows RunOnce entry. If a file is still locked, the
transaction and its backup remain available. The About panel reads the most
recent update result. Details are in maintenance.log and, for Setup,
installer.log under the transaction directory. If an automated restore fails,
close ARM and use the previous verified installer or restore the previous
portable payload. Keep the ARM profile and transaction logs. Profiles, the Credential Manager, SSH trust and
telemetry history are outside the file-replacement transaction.
