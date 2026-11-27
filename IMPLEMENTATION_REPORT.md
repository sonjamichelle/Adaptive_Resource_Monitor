# Adaptive Resource Monitor implementation report

## v0.8.4.4_beta — Settings, changelog and licensed release

The Minor and Bug-Fix counters each advance once from v0.8.3.3_beta.
This release includes the offline DC-ANCSA v1.0 viewer and Setup agreement,
local and remote uptime, full machine card sorting, and button-only pinning.
The main window and tray share the same Settings page, including pending edits.
View Changelog restores a minimized monitor, opens the changelog and clears
both success banners while leaving the update receipt available.

The production update runs directly from v0.8.2.3_beta. That updater invokes
Setup in unattended mode, so the production user reviews and accepts the
exact signed-release license separately before authorizing installation in
the existing About controls.

## v0.8.3.3_beta — Software license and monitor refinements

This Minor milestone bundles the supplied DC-ANCSA v1.0 text byte for byte,
adds original source attribution, presents the complete license in a themed
offline About dialog with saved geometry, and adds a license agreement to
interactive Windows Setup. Signed release information identifies the
license hash. Later changes require verified text and explicit acceptance
before the updater shuts down the application.

The update success banner dismisses when its changelog opens. Any
non-interactive part of a machine card can start a drag, including a graph.
The hover monitor's own button controls pinning.
Windows and Linux machine headers report uptime from the existing local
sampling worker and SSH telemetry stream.

The supplied root license and the anonymous Gitea copy match SHA-256
`d5dde5498f5a81b4cc9ca1db3a1b53d6cc343053a080ceaefcf20a423984f215`.
Gitea's description identifies the current source as DC-ANCSA v1.0. The
repository retained its existing visibility and prior release tags.

The dependency review preserved the Qt, PySide, CPython, Paramiko and
other wheel notices. It added the BSD notice from the NVIDIA wrapper
source header and the OpenSSL and Tcl notices. The applications' own
license governs original material. Separate upstream terms for bundled
libraries are documented in the third-party notices.

The 39 regressions and final private native Windows suite passed. The
suite checked the offline license viewer and restored window placement,
the banner and completion marker, graph-body dragging, tray click and
pin behavior, and Windows uptime and Linux SSH fixture uptime. The
Linux probe passed Bash syntax validation in the existing Ubuntu WSL
environment.

Build and Archive #17 built and signed commit
`8079bf0ca626c7643e5cf3e928651f9c8e63c96a`. The Windows x64 installer,
portable package, Ed25519 signature, exact bundled license and signed
build identity verified. This internal candidate was superseded by
v0.8.4.4_beta.
[Build #17](https://phantom.zapto.org:8080/jenkins/job/Adaptive-Resource-Monitor/job/Build-and-Archive/17/)

| Windows x64 package | Bytes | SHA-256 |
| --- | ---: | --- |
| Installer | 60,120,801 | `4360334e1c8123664bada615a57cdbed4b319cb0948ebd1040a3b74d0320a881` |
| Portable ZIP | 74,566,298 | `bec0c3656e65e0da8f12faebb585b27a186feca10b2981c090083904fa288a09` |

The disposable Inno Setup wizard displayed the complete agreement from
the archived payload. Declining disabled Next and canceling preserved the
prior executable and data. Accepting advanced Setup. The separate unattended
update-mode install and uninstall both returned 0. The installed license
matched its source, and the fixture profile, saved display preferences and
history remained identical. The wizard screenshot is retained in
`evidence/v0.8.3.3_beta-native/installer-license-agreement.png`.

The final private application check removed 242,695 bytes of test data.
The disposable Setup check removed 278,016,814 bytes of compiler staging,
test installers, installation files and fixture settings. The signed
candidate and evidence are retained.

A failed early disposable compiler stage left
`%TEMP%\arm-qa-upgrade-i_uxybxg`. Windows denied access to the child
compiler directory. Automatic command review rejected ownership and
cleanup operations for that path.

## v0.8.2.3_beta — Machine ordering and display selection

Two Feature increments combine drag-and-drop machine ordering and checkbox
selection in one Beta. The machine order and selection use stable profile
identifiers and one immediately saved file in the ARM settings directory.
The file is flushed before atomic replacement. A Windows write-through move
commits the new file. It remains available if an earlier application version
rewrites its settings during rollback. The original single-machine or All
Systems preference supplies the initial selection and order.

The hover and expanded monitors and tray submenu share the same checkbox
selection. Remote Targets and both monitors share the same order. Sorting a
subset changes its visible slots and preserves the positions of hidden
machines. The save completes before a new selection or order is displayed.
Sorting and visibility changes leave telemetry providers, SSH sessions,
history and the primary tray source in place.

Package inspection found a Qt Virtual Keyboard plugin brought in by the
freezer and missing LGPL v3 and GPL v3 license texts. The build excludes the
optional plugin and includes the upstream notices and versioned sources for
the dynamically linked Qt and PySide runtime. The native package test checks
both notice files and the absence of the plugin.

### Release verification

All 38 automated regressions passed. The private native Windows tests
exercised every requested machine combination at effective 100% and 150%
Qt scaling, drag-and-drop in all three interfaces, Escape cancellation,
autoscroll, failed-write recovery, hidden-machine history, and restoration
after the isolated Windows process was forcibly terminated. Four loopback
SSH fixtures carried the production profile names in those tests. The
reordered windows and six display combinations are recorded in
`evidence/v0.8.2.3_beta-native/`.

A separate native installer identifier and disposable settings root enabled
an upgrade, rollback and re-upgrade check beside the running production
instance. All four Setup operations and uninstall returned 0. The profile,
saved display order and selection, and history fixture stayed intact.

Build and Archive #16 built commit
`d2f8550111c85ae3fc12c3ed47fc511acce25733`. Publish Release #12
published all seven archived assets. Anonymous size and SHA-256 comparison
matched the same archive. The Ed25519 signature, package architecture,
version, release notes, and source commit were verified.
[Build #16](https://phantom.zapto.org:8080/jenkins/job/Adaptive-Resource-Monitor/job/Build-and-Archive/16/)
[Publication #12](https://phantom.zapto.org:8080/jenkins/job/Adaptive-Resource-Monitor/job/Publish-Release/12/)
[Public release](https://phantom.zapto.org/gitea/sonja/Adaptive_Resource_Monitor/releases/tag/v0.8.2.3_beta)

| Windows x64 package | Bytes | SHA-256 |
| --- | ---: | --- |
| Installer | 60,102,728 | `fad639b044a0bce65e25b98abe83accf4697df2b08e944edfb92ed08320a49a9` |
| Portable ZIP | 74,550,214 | `185c9ce82e09bb6b2b1e44d2236548989f18749c8fa095e57a81919329d759a5` |

### Production acceptance

The installed updater discovered and verified the package in About.
Transaction `830e1c4a2a814638a1450cb32499db7c` recorded shutdown,
exit code 0 before installer startup, visible installation progress,
verification, and an automatic restart in the same Windows user session
at the original privilege level. The transaction and completion receipt are
retained in `evidence/v0.8.2.3_beta-production/`. The sole running
instance matched all 298 archived payload files, and the launcher exited.

The five machines resumed monitoring. The production Explorer hover
recorded a deliberately changed order, the visible version label, and the
Rain and Phantom checkbox selection. All four remote SSH sessions remained
connected while only two machines were displayed. The settings and SSH
host key files retained their hashes. Credentials and startup settings were
preserved. Persistent recording and automatic update checks remained off.
The installed updater verified v0.8.2.3_beta as current.

The disposable installer test reclaimed 496,926,848 bytes and the
independent public verification reclaimed 134,655,353 bytes. Redundant
local screenshots totaling 1,139,355 bytes were removed. The 20 feature
screenshots and production receipts remain as evidence.

## v0.6.2.3_beta — Hover monitor version and window placement

Production v0.6.2.2_beta was built from `5e8ea74be3fd94156bdc7a0810cfcc8eaac739f0`.
The earlier hover label and expanded-window geometry corrections were
committed afterward in `d40be62478eb45f572a1555ce22491e4a2cc5eb8`. The
published Beta and its installed executable therefore lacked both changes.

This Bug-Fix increments only the last numerical counter. The hover monitor
reads VERSION.md through the shared version module and renders it above the
selectors and Pin and Details controls. A shared geometry handler preserves
the existing main-window state file and remembers Settings, Remote Targets,
Remote Machine and Application Details placement. The About layout remains
the same as the previous release.

The 34 regressions passed. Native Windows checks exercised individual and
All Systems, pinned and unpinned, and a popup anchored to a separate machine
icon. Both themes were checked at effective 100% and 150% scaling using
Qt's per-process scale factor on private Windows desktops. A native geometry
check confirmed exact positioning on reopening and recovery of an off-screen
About window on the current display.

Build and Archive #13 built commit
`31f0b430fbe05eafcbef87a7f6cf39c07aa9030e`. The native package checks
and Ed25519 verification passed. Publish Release #11 published the pinned
archive. All seven anonymous downloads matched the archive by size and
SHA-256. The signed manifest, exact version, x64 packages, Gitea tag, and
release notes were independently verified. The installed v0.6.2.2_beta
updater code found the release eligible without a verification error.
[Build #13](https://phantom.zapto.org:8080/jenkins/job/Adaptive-Resource-Monitor/job/Build-and-Archive/13/)
[Publication #11](https://phantom.zapto.org:8080/jenkins/job/Adaptive-Resource-Monitor/job/Publish-Release/11/)
[Public release](https://phantom.zapto.org/gitea/sonja/Adaptive_Resource_Monitor/releases/tag/v0.6.2.3_beta)

| Windows x64 package | Bytes | SHA-256 |
| --- | ---: | --- |
| Installer | 60,172,627 | `ef64b5a98194c35a4dac15b733dcf1206ad680dfb37a3e3963667da4a9a14c46` |
| Portable ZIP | 74,687,810 | `7e7cfe7bfd0752896da4216d2a1ed02539e636e01529b27541ada446a9a3dbe1` |

### Production acceptance

The installed updater reported the verified release and downloaded the
60,172,627-byte installer with the expected SHA-256. Transaction
`ec8569b9bdf0454aa9229283796e6d1a` captured independent preparation and
installation progress. ARM acknowledged shutdown, exited with code 0
before the installer log was created, and automatically restarted in the
same Windows user session and privilege level. The completion receipt and
success notification were saved. One ARM instance remained and the updater
exited. All 298 installed files matched the archived build.

Local Machine, Rain, Phantom, LAMP and PhantomNet resumed monitoring.
The production Explorer hover screenshot shows all five systems,
independent network IN and OUT graphs, and `v0.6.2.3_beta` at the upper
right. Settings and pinned SSH host keys matched their pre-upgrade hashes.
Saved credentials remained accessible and automatic checks remained off.
Persistent disk recording was already off. The shipped client verified
that the public release matched the installed version.

The signed packages remain available from Jenkins and Gitea. The two
superseded local binaries totaling 134,860,437 bytes were removed after
the feature release passed. Native screenshots are under
`evidence/v0.6.2.3_beta-native/`. The live screenshot,
installer log, process verification and completion receipt are retained
under `evidence/v0.6.2.3_beta-production/`. The independent anonymous
verification removed 134,862,477 bytes of temporary downloads. Jenkins
removed its staging and package-test data and cleaned both job workspaces.

## v0.6.2.2_beta — Beta promotion

Alpha production acceptance and the signed same-number compatibility
check passed before the Beta build. The promotion kept the four numerical
counters at `0.6.2.2`. All 34 regression tests and the isolated native
Windows verification passed. Build and Archive #10 used commit
`5e8ea74be3fd94156bdc7a0810cfcc8eaac739f0`. Publish Release #10 published
its artifacts as a separate Gitea prerelease. The earlier Alpha releases
remain public.
[Build #10](https://phantom.zapto.org:8080/jenkins/job/Adaptive-Resource-Monitor/job/Build-and-Archive/10/)
[Publication #10](https://phantom.zapto.org:8080/jenkins/job/Adaptive-Resource-Monitor/job/Publish-Release/10/)
[Public Beta](https://phantom.zapto.org/gitea/sonja/Adaptive_Resource_Monitor/releases/tag/v0.6.2.2_beta)

All seven Beta attachments matched anonymously by size and SHA-256. The
Ed25519 signature, version, x64 PE metadata, portable package and build
receipt verified. The installed corrective Alpha client verified this
public Beta as eligible.

| Windows x64 package | Bytes | SHA-256 |
| --- | ---: | --- |
| Installer | 60,165,231 | `305cd316547245eaf0d77703f1b4be93404f7762fa4839b4b4a693c13d3bd78f` |
| Portable ZIP | 74,682,861 | `e1ee75e4218594feb7c1735cf1853739f18e5560df37666e25b186216077657a` |

### Production Beta acceptance

The installed corrective Alpha displayed the signed Beta as available, then
ready to install after the package download. ARM recorded one availability
notification for the Beta. Install Later kept the same verified bytes and
timestamp. Installation began through the installed application's controls.

Transaction `04ef6d0d8a3745bd8629d8945a6f2349` recorded the old process
acknowledging shutdown and exiting at 8:34:40.683 PM CST with exit code 0.
The installer log was created at 8:34:41.896 PM. The independent progress
window was visible during installation. The same Windows user, session and
non-elevated privilege level were retained. The automatic restart reported
v0.6.2.2_beta, persisted its completion receipt and displayed the success
confirmation. Windows registration and About reported Beta. The 298
installed payload files matched build #10. The restarted process remained
the sole ARM instance and the maintenance launcher exited.

The production settings and SSH host key files matched their pre-update
hashes. All credential references remained accessible, and startup,
Windows notification and automatic update-check preferences were preserved.
Persistent recording was off before both updates. All Systems displayed
four independent histories with fresh Local Machine, Rain, Phantom and
LAMP samples and distinct network IN and OUT readings. All four sample
timestamps advanced during a 20-second observation. Explorer returned a
live tray icon with six distinct rendered frames. The installed About
check verified Beta as current. The acceptance checks covered 169 seconds
after the automatic Beta restart.

Both production self-updates passed. Adaptive Resource Monitor is publicly
released and running in production as v0.6.2.2_beta. The production
screenshots, shutdown acknowledgement, installer log and completion
receipts are retained locally under `evidence/v0.6.2.2_alpha-production`
and `evidence/v0.6.2.2_beta-production`.

### Separate window changes and cleanup

The local hover monitor shows the installed version on the status row below
the controls. The expanded window keeps the existing About layout, fits
inside the monitor's work area, and restores its saved size and position.
Private native Windows checks verified the hover label at 300 and 500 pixels
and verified exact geometry restoration, oversized window handling, and
off-screen placement recovery. These are separate source changes after
the pinned Beta commit.

Anonymous Beta readback removed 134,850,358 bytes of duplicate downloads.
The two isolated window checks removed 6,220 bytes of temporary data.
A final isolated GUI regression passed and removed 55,800 bytes of test
data. A 719-byte incomplete capture was discarded. Jenkins cleared its build
and publication workspaces. The verified local release archives, selected
production screenshots and actual updater logs were retained.

## v0.6.2.2_alpha — Update channel correction

Windows Program Compatibility Assistant recorded the archived
`release/v0.6.2.1_alpha/AdaptiveResourceMonitor-v0.6.2.1_alpha-windows-x64-setup.exe`
launching at 7:44:03 PM CST on November 26. The installed uninstaller was
written in the same second and its data was written at 7:44:12 PM. The
new application started at 7:44:13 PM. Gitea published build #7 at 7:48:46
PM. The installer was launched from the release archive, outside the
disposable test paths and before the update was available publicly.
A production updater transaction or receipt for this launch was absent.
The available audit and session records do not identify the launcher.
Jenkins build #7 compiled and archived the files, and publication #8
handled Gitea publication. The recorded isolated installer tests used
disposable targets. Production fingerprints now bracket development
validation, and the release procedure requires the installed UI and a
complete updater receipt for live acceptance.

The corrective version changes only the Bug-Fix counter. Discovery,
download and installation now share a policy that allows the installed
channel and more mature channels while rejecting lower numerical versions.
The release index distinguishes channel and version exclusions from
signature or metadata failures. There was no explicit channel preference
in the existing settings. All 34 regression tests passed, including signed
same-number Alpha-to-Beta discovery and the full channel matrix.

### Corrective Alpha release

The native Windows agent's Build and Archive #8 succeeded at commit
`363c29fcdc3766c0e28558a0a0ede76308b7405f`. Publish Release #9 reused that
archive. All seven public attachments passed independent anonymous size
and SHA-256 verification, including a fresh signature, PE metadata and
portable package check. The old Alpha releases remain public.
[Build #8](https://phantom.zapto.org:8080/jenkins/job/Adaptive-Resource-Monitor/job/Build-and-Archive/8/)
[Publication #9](https://phantom.zapto.org:8080/jenkins/job/Adaptive-Resource-Monitor/job/Publish-Release/9/)
[Public corrective Alpha](https://phantom.zapto.org/gitea/sonja/Adaptive_Resource_Monitor/releases/tag/v0.6.2.2_alpha)

| Windows x64 package | Bytes | SHA-256 |
| --- | ---: | --- |
| Installer | 60,156,586 | `266b7aeb525a963f05605152e5be0bb7d41ac86537d5dbdf18d9ae6e1e91efa6` |
| Portable ZIP | 74,683,844 | `fc6074018fd04a60a7b8c9c5d671dcec991cec8cde5435c5774c2e04a29c57b2` |

The live v0.6.2.1_alpha executable, maintenance launcher, build receipt,
settings, SSH host keys and process identity matched the recorded start
of development. Existing update-check and startup preferences and all
three credential references also matched. Persistent history was off.
The installed executable's released update client verified the public
v0.6.2.2_alpha as eligible. The corrective archive's frozen updater also
selected the correctly signed v0.6.2.2_beta fixture with identical
numerical counters. This test used a temporary fixture outside production.

### Corrective Alpha production self-update

The installed ARM controls discovered v0.6.2.2_alpha, displayed the
available notice and downloaded the verified Windows x64 installer.
The hover and tray menu notices were confirmed at the workstation and
captured, along with About, the expanded banner and the ready state.
Two checks kept a single Windows notification record for the release.
Install Later preserved the verified package and its file timestamp.

Transaction `1cfe7ea68d16460198509fcb49ff4382` recorded the normal update
controls handing off to the independent launcher. The main process
acknowledged closure and exited successfully at 8:18:31.284 PM CST.
The installer log was created at 8:18:32.712 PM. The independent progress
window was visible during installation. The launcher restarted ARM in
the same user session and at the same elevation. The restarted process
wrote the v0.6.2.2_alpha completion receipt and the GUI displayed success.
The maintenance processes exited. All 298 installed payload files
matched the archived build.
The operator confirmed a separate reopen after seeing the successful
automatic restart. Explorer was the parent of that later launch. The
automatic restart receipt and success capture were already present.

The settings and SSH key files were byte-identical after the update.
Startup, automatic update checks and Windows notification preferences
were preserved. All three credential entries were accessible. ARM
reestablished SSH connections to Rain, Phantom and LAMP. The installed
corrective Alpha also selected the correctly signed same-number Beta
fixture in a read-only test of the shipped code.
Explorer registered the Local Machine tray icon, and six passive samples
showed six distinct live frames. The periodic check option remains under
Settings → General with the production interval set to Off.

All Systems reported four connected machines with fresh Local Machine, Rain,
Phantom and LAMP samples and separate network IN and OUT readings. The live
Explorer hover window displayed the same independent histories. Production
Alpha acceptance passed, including discovery of the signed same-number
Beta fixture by the installed corrective updater.

Publication readback removed 134,842,388 bytes of duplicate downloads.
The isolated frozen-client check removed 4,148,335 bytes, and the private
Windows UI validation removed 59,841 bytes. Package verifiers and Jenkins
removed their staging. The verified release archive and prepublication
fingerprints are retained as evidence.

## v0.6.2.1_alpha publication and production assessment — 2026-11-26

### Publication and anonymous verification

Publish Release #8 succeeded using the seven artifacts from Build and
Archive #7 at commit `035fb8ddc918337fdf6cf9743082aacae940b9db`. No build
was run for publication. Gitea published the Alpha prerelease at 7:48:46 PM
CST. Its version tag resolves to the pinned commit, and the public release
notes match the tagged changelog and signed manifest.
[Public release](https://phantom.zapto.org/gitea/sonja/Adaptive_Resource_Monitor/releases/tag/v0.6.2.1_alpha)
[Publish Release #8](https://phantom.zapto.org:8080/jenkins/job/Adaptive-Resource-Monitor/job/Publish-Release/8/)

Jenkins and an independent anonymous download verified all seven attachments
against the archived bytes. The Ed25519 signature, Windows x64 architecture,
package types, executable versions, package lengths, SHA-256 checksums and
build identity passed. The earlier v0.6.1.1_alpha release is still public.

| Windows x64 package | Bytes | SHA-256 |
| --- | ---: | --- |
| Installer | 60,163,795 | `7d79e692b88819298c6ae00bf6041cdcea77c2171965a784f39fd2961179080a` |
| Portable ZIP | 74,681,911 | `966edc69169ab607f810e67af0def5ac1ad86360bfcd3996e884104b4ae32b98` |

### Production Alpha acceptance

The first production inspection found v0.6.2.1_alpha already installed and
running. ARM logged the earlier instance stopping at 7:43:48 PM CST and the
new version starting at 7:44:15 PM, before the target release became public.
The production profile had no staged updater download, transaction plan or
completion receipt. The required production self-update from v0.6.1.1_alpha
could not be performed or established from that starting state. Automatic
shutdown, installation, restart and the success notification for that
transition remain unverified. The working installation was preserved.

- Windows registration, the installed executable and the build receipt report
  v0.6.2.1_alpha from build #7. All 298 installed payload files matched the
  verified archive. One ARM process was running in the console session with
  no orphaned ARM installer or maintenance process observed.
- Rain, Phantom and LAMP had established SSH connections owned by ARM, and
  Windows Credential Manager returned entries for all three saved references.
  The production settings and pinned host-key file stayed byte-identical
  during this assessment. A pre-upgrade data comparison for the earlier
  version change was unavailable. Persistent recording is disabled, and
  startup and periodic update checks remain disabled.
- Explorer returned one registered tray icon for ARM. Six passive samples
  showed six different rendered frames. Foreground hover, tray-menu and
  All Systems interactions were outside this passive production check.
- The frozen v0.6.1.1_alpha release client discovered and verified the
  published Alpha as an eligible upgrade. The frozen client from the production
  v0.6.2.1_alpha executable verified the same release as current. Both checks
  used the actual public endpoint and no Gitea authentication.

**Alpha production self-update acceptance did not pass.**

### Beta promotion blocked

The version comparison and discovery test used updater code read from the
installed v0.6.2.1_alpha executable. Numeric counters sort before maturity,
and the supported tags sort `alpha < beta < rc < stable`. Same-number Beta
has a higher version key, but the shipped client only considers its current
prerelease channel and eligible stable releases. It skipped the signed Beta
fixture before requesting its manifest and selected the signed Alpha fixture
as current. The fixture's Beta signature independently verified. The tests
also confirmed same-version installation rejection, Beta-to-Alpha downgrade
rejection, eligible numeric progression and malformed-version rejection.

Production remains on v0.6.2.1_alpha. VERSION.md and the numerical version
counters are unchanged. No Beta build, tag, publication, production
notification exercise or installation was performed. An updater
compatibility change would require a separately authorized corrective release.

### Publication cleanup

Removed 138,981,356 measured bytes of temporary anonymous downloads and
previous-updater test files. The verifier removed its temporary payload
extractions, and Jenkins deleted its publication workspace. The published
releases, their archived packages and the existing validation evidence
were retained.

## v0.6.2.1_alpha — Update notifications and installation lifecycle

The Minor counter advanced. The hover monitor, expanded window and tray menu
use the About updater's verified-release state. Install Later retains the
download and its ready notice. A Windows notification preference controls
one-time notifications. The maintenance launcher waits for a clean ARM
shutdown and process exit, shows independent installation progress and
checks the restarted version before reporting success. The release uses
the existing Jenkins build and authorized publication jobs.

### Native Windows validation

- The 28-test regression suite passed. The private desktop suite passed on
  native Windows, including update availability, rejected signatures,
  downloading, install readiness, deferral and notification deduplication.
  Both Design Creations themes and the confirmation's View Changelog action
  passed. The notification also appeared in the separate remote tray menu
  and the pinned remote and All Systems popup. Live telemetry, individual
  tray sources and separate network IN and OUT remained operational.
- Disposable installed and portable x64 copies updated to a signed local
  fixture. The installer exited with code 7 when its destination executable
  was running. The updater waited for the original process and its clean
  shutdown acknowledgement. An exit without acknowledgement left the
  payload untouched. The independent helper displayed progress while the
  installer installed the verified update.
- The installed upgrade restored the expanded window and the portable
  upgrade restored tray-only mode. The restarted process ran as the same
  user in the same Windows session at the same elevation. A second launch
  exited without creating another instance. Settings, Windows Credential
  Manager references, saved fixture credentials, the SSH trust file and
  existing SQLite samples survived. Each lifecycle test exited with code 0.
- A fixture with a signed commit mismatch exercised rollback after
  replacement. The previous portable executable was restored byte for byte
  and restarted. A separate interrupted replacement recovered from the
  persisted journal and cleared its RunOnce entry.
- The previous v0.6.1.1_alpha frozen launcher applied the exact signed
  portable archive from Jenkins #7 on a private desktop. It restarted
  v0.6.2.1_alpha, the new application displayed confirmation from the legacy
  receipt and the fixture profile remained identical. The installed
  lifecycle tests used a disposable installer AppId.

### Jenkins release candidate

Build and Archive #7 completed on the native Windows agent after an SCM
change. The pinned source
commit is `035fb8ddc918337fdf6cf9743082aacae940b9db`. Jenkins validated PE
metadata, installer and portable package identity, ZIP integrity and two
portable launches. All seven archived files were retrieved and verified
locally against the same commit and build. The ARM Ed25519 verification key,
signature, package version, architecture, filenames, sizes and SHA-256
hashes passed. The archive includes the checksums, signed manifest, public
key, release notes and build receipt alongside the two packages.
[Jenkins build record](https://phantom.zapto.org:8080/jenkins/job/Adaptive-Resource-Monitor/job/Build-and-Archive/7/)

| Windows x64 artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| AdaptiveResourceMonitor-v0.6.2.1_alpha-windows-x64-setup.exe | 60,163,795 | `7d79e692b88819298c6ae00bf6041cdcea77c2171965a784f39fd2961179080a` |
| AdaptiveResourceMonitor-v0.6.2.1_alpha-windows-x64-portable.zip | 74,681,911 | `966edc69169ab607f810e67af0def5ac1ad86360bfcd3996e884104b4ae32b98` |

The verified archive is in `release/v0.6.2.1_alpha`. Six captures of the
hover, expanded window, tray menu, About tab, installation progress and
successful update are in `evidence/v0.6.2.1_alpha`. The availability captures
show the signed local fixture version.

### Production status before publication

At the end of prepublication validation, production and the public release
index still reported v0.6.1.1_alpha. The executable, settings and pinned SSH
host-key file matched the before-test hashes. The new progress window
applies to updates started from v0.6.2.1_alpha onward.

### Validation cleanup

Removed the staged compiler, private test key, test-only builds, profiles,
QA scripts, temporary extractions and two superseded captures. Manual
cleanup removed 2,536,086,381 bytes by logical file size. The two local
package builds automatically removed another 686,018,471 bytes of build
staging. The disposable Windows apps and their recovery entries were
cleared. Jenkins cleaned its build workspace. The verified #7 archive
and six requested captures are retained as release and validation evidence.

## Initial public release and production upgrade — 2026-11-26

[Adaptive Resource Monitor v0.6.1.1_alpha](https://phantom.zapto.org/gitea/sonja/Adaptive_Resource_Monitor/releases/tag/v0.6.1.1_alpha)
was published by [Publish Release #6](https://192.168.1.164:8080/jenkins/job/Adaptive-Resource-Monitor/job/Publish-Release/6/).
The job used [Build and Archive #3](https://192.168.1.164:8080/jenkins/job/Adaptive-Resource-Monitor/job/Build-and-Archive/3/)
at 6b333b6e930399c73873911197ce1e63d567c034, the archive previously verified by
[Publish Release #4](https://192.168.1.164:8080/jenkins/job/Adaptive-Resource-Monitor/job/Publish-Release/4/).
The build job remained at #4 and its H/5 main-branch SCM trigger was
still configured. Build #4 had an SCM-trigger cause. Publication #5
records the prior rejection without authorization. Publication #6 recorded
explicit authorization and archive #3 as its selected build.

### Public readback

The release tag resolves to the pinned commit. All seven files were downloaded
over anonymous HTTPS and matched the pinned archive by byte count and SHA-256.
The signed manifest matched the exact bytes in Jenkins build #3. Its Ed25519
signature, application ID, version, build number, commit, package types and
Windows x64 architecture verified. Native PE and ZIP payload checks passed.
The release body and attached notes match the signed notes. The complete
changelog is in both distributions and at the
[public version tag](https://phantom.zapto.org/gitea/sonja/Adaptive_Resource_Monitor/src/tag/v0.6.1.1_alpha/CHANGELOG.md).

| Anonymous attachment | Bytes | SHA-256 |
| --- | ---: | --- |
| AdaptiveResourceMonitor-v0.6.1.1_alpha-windows-x64-setup.exe | 57,131,180 | c4aad237a9e92668c278d08b7887f1bea16a72850c25e7c01e7aea85e6692474 |
| AdaptiveResourceMonitor-v0.6.1.1_alpha-windows-x64-portable.zip | 71,478,426 | d7fe934beb75cf96f7aad70012a31bc958a7657f8a04fc82717111d305da9d53 |
| SHA256SUMS.txt | 257 | 537884b587d76e13a7ccaab0fd2c30bf38f010cc5e13acc803969830f624e1de |
| arm-update-windows-x64.json | 935 | 33ee001c4a4c6154cfb185ea381cf3e975ff3c10b780dc01b0e58c841c86f498 |
| arm-ed25519.pub | 45 | 6127dc67b0f49479fe8a7924b1dc2fc5597da2e4c066f246925fce1c8097ba17 |
| release-build.json | 561 | b953ec28642b906b43f7af1ed01637c63d7029186cf400a0162b1c4e019769e2 |
| RELEASE_NOTES.md | 250 | fd25e23c01bc35099c1686ef9370024cf57f5d24b3e7c0ed643e38f0d3872734 |

### Production upgrade and checks

- The v0.4.1.1_alpha process closed cleanly. The anonymously downloaded
  and verified Setup performed the in-place upgrade and completed without
  a Windows restart. The production registry and running binary report
  v0.6.1.1_alpha. All 297 installed payload files matched build #3.
  The first launch logged a clean exit. A subsequent instance stayed
  running through validation.
- The settings file and pinned SSH host-key file matched byte for byte.
  The three Windows Credential Manager entries and their references
  matched, as did the Start with Windows registration. Saved machine
  selections, graph colors, display mode, hover range, popup dimensions and
  theme were preserved. ARM positions the popup from the live tray icon.
  Recording was off and the configured profile had no retained SQLite
  history. In-memory graph history began again at restart.
- The production process had established SSH sessions to Rain, Phantom
  and LAMP. In a private native Windows desktop, the same profiles
  produced fresh samples for all three remotes and Local Machine.
  Both All Systems views showed six per-machine graphs, with separate
  plotted network IN and OUT traces. Explorer returned an on-screen
  rectangle for the installed tray icon, and six passive samples showed
  six distinct rendered images. The hover path passed in
  isolation using that rectangle, and the user confirmed the popup
  appeared when hovering over the real Explorer icon.
- Both Check for Updates controls were invoked in the actual installed
  executable on a private Windows desktop using a disposable profile.
  Each queried the live public repository, verified the release and
  displayed “This is the latest verified version.” The production
  profile's startup and periodic update checking remained off.

### Production validation cleanup

Removed the duplicate anonymous downloads, expanded verification payload,
temporary installer log, private desktop profiles and diagnostic scripts.
Manual cleanup removed 283,979,051 bytes by logical file size, and the
package verifier removed another 155,163,584 bytes of temporary extraction.
Jenkins reported that it cleared the publication workspace. The installed
application, user profile, public release, pinned local candidate and
historical releases were kept. The local report is the only worktree edit.

## v0.6.1.1_alpha — Signed updates and release automation

The Feature counter advanced twice for the updater and the build and
release infrastructure. The accepted v0.4.1.1_alpha monitoring behavior
carries forward. VERSION.md now supplies the application and package
version. The build number is a separate part of the Jenkins receipt.

The About and tray actions check the public ARM Releases index on a
background thread. Startup and periodic checking are opt-in. Downloads
can be paused and resumed, and the verified installer or portable ZIP can
be used later. Install requires confirmation. An independent Windows
launcher waits for the monitor to save history and exit, verifies the
package again, applies the update and waits for the new process to report
readiness. Its transaction journal supports recovery and rollback.

### Repository access

The existing ARM repository serves the source and release endpoint. Before
making it anonymously accessible, the three historical commits were
sanitized to remove monitoring screenshots, identifying machine labels and
personal commit email. The prior objects were pruned from the ARM repository
on the server. Old commit and screenshot requests returned 404. The owner
account now permits anonymous ARM access, while all 55 other repositories
under that owner returned 404 anonymously. The original local screenshots
remain with the user. The unused temporary binary repository was removed.

### Validation

- Twenty-five automated tests passed. Update fixtures covered valid and
  invalid signatures, missing signatures, release selection, downgrade
  rejection, server failure, package size and hash checks, interrupted
  downloads, cancel and resume, and unsafe portable archive paths.
- Native tests on a private Windows desktop exercised the About and tray
  check actions, the startup policy, periodic scheduling and continuing
  resource collection during a pending check. The live tray graph, separate
  machine views, networking directions and branding passed regression checks.
- The native About controls showed signed release notes and live progress.
  Telemetry continued while a download was blocked. Install Later kept the
  verified package across a fresh application instance. A separate loopback
  HTTPS test downloaded and verified a package anonymously with certificate
  validation enabled.
- Controlled installed and portable updates ran on private Windows desktops
  using disposable builds and profiles. Both restarted the updated executable
  and received its readiness acknowledgement. An injected mismatch after
  replacement restored the previous portable files. An interrupted journal
  restored the previous executable. The test settings, saved Windows
  credential, SSH trust file and existing SQLite row survived. The native
  installer used a disposable AppId. An independent frozen maintenance
  launcher also performed a signed portable update, restarted the monitor
  and cleared its temporary recovery registration.
- ARM's production release index was anonymously reachable and empty.
  The accepted installation was outside the test runs. Public production
  artifact retrieval awaits release authorization.

### Jenkins release candidate

[Build and Archive #3](https://192.168.1.164:8080/jenkins/job/Adaptive-Resource-Monitor/job/Build-and-Archive/3/)
was triggered by an SCM change and completed successfully on inkiron-windows.
It built commit 6b333b6e930399c73873911197ce1e63d567c034 and archived seven
files. Native validation verified x64 PE resources, installer metadata, ZIP
integrity and two portable launches. The archived manifest signature matched
the trusted ARM-specific key. The downloaded archive passed offline revalidation.
An attempted verification with an incorrect build number was rejected.
[Publish Release #4](https://192.168.1.164:8080/jenkins/job/Adaptive-Resource-Monitor/job/Publish-Release/4/)
copied all seven files from build #3 and verified its exact version, commit,
signature and hashes. The public upload stage was skipped in verification-only
mode. A disposable Inno upgrade installed all 297 files from the archived
payload byte for byte. Its native wizard, frozen startup, shutdown and
uninstall passed. The production registration still showed v0.4.1.1_alpha.
[Publish Release #5](https://192.168.1.164:8080/jenkins/job/Adaptive-Resource-Monitor/job/Publish-Release/5/)
deliberately requested publication without authorization. Jenkins rejected
it before retrieving the archive or entering the publishing stage.
The anonymous Gitea endpoint has zero releases and zero tags.
[Build and Archive #4](https://192.168.1.164:8080/jenkins/job/Adaptive-Resource-Monitor/job/Build-and-Archive/4/)
also succeeded after the publication job permission change at
48beab46711ffc9b25a7643f46ab9a578cf43fee. Build #3 remains the selected
candidate and is the archive copied during publication verification.

| Candidate file | Bytes | SHA-256 |
| --- | ---: | --- |
| [Windows installer](release/v0.6.1.1_alpha/AdaptiveResourceMonitor-v0.6.1.1_alpha-windows-x64-setup.exe) | 57,131,180 | c4aad237a9e92668c278d08b7887f1bea16a72850c25e7c01e7aea85e6692474 |
| [Portable ZIP](release/v0.6.1.1_alpha/AdaptiveResourceMonitor-v0.6.1.1_alpha-windows-x64-portable.zip) | 71,478,426 | d7fe934beb75cf96f7aad70012a31bc958a7657f8a04fc82717111d305da9d53 |

The release directory also contains SHA256SUMS.txt, the Ed25519 manifest,
public key, release notes and build receipt. The signature authenticates
the package bytes through the manifest. The executables would require
separate Authenticode signing for Windows publisher verification.

### Cleanup and remaining authorization

Removed the disposable Windows installations, temporary profiles and
credentials, staged compiler and Python dependencies, extracted payloads,
test TLS certificates and keys, Git sanitization checkout, failed build
output and local diagnostics. The local build and QA cleanup accounted for
**2,463,578,942 bytes** measured by logical file size. Build #3 independently
reported **482,337,392 bytes** removed from its measured packaging and native
QA directories. Build #4 reported another **482,329,896 bytes** of measured
cleanup. Both Jenkins pipelines cleaned their workspaces after
execution. The selected packages and verification metadata are retained
locally and in the Jenkins archive. Earlier accepted releases and original
local screenshots are retained as user data.

Public release publication and any in-place production installation
require separate authorization. The production index can be read anonymously.
Anonymous downloads were tested using an isolated signed update fixture.
Interrupted-installation recovery was exercised with a saved journal. The
Windows sign-in path following an actual reboot was outside that test.

## v0.4.1.1_alpha — Independent tray machine

The Minor counter advanced from 0 to 1. The existing Major, Feature and
Bugfix counters and alpha classification carry forward from v0.4.0.1_alpha.

The hover monitor, expanded window and Monitor Machine menu offer Local
Machine, individual configured remotes and All Systems. All Systems shows
six independent resource charts for each enabled machine, including separate
network IN and OUT traces. The primary icon reads one source chosen under
Settings → Tray Icon → Tray icon machine. Local Machine is the default.
Optional individual icons honor each remote's tray setting. Overlay, Stacked
and Composite use resources from the icon's machine. The branded Application
Icon is still available in Settings and during initialization.

Saved legacy Aggregate - Peak monitor selections load as All Systems. Legacy
explicit tray remotes and the separate-icon preference carry forward. If the
legacy consolidated setting supplied the implicit monitor scope, the monitor
opens in All Systems and the tray icon uses Local Machine. The next settings
save writes the current fields. The migration leaves the telemetry and history
formats intact.

### Acceptance checks

- All 18 automated model and provider tests passed, including legacy settings,
  persisted monitor and tray selections, archived history, directional network
  rates and independent collectors.
- Native application checks passed on private Windows desktops at 100% and 150%
  Qt scaling. The local computer and two loopback SSH targets each had six
  independent All Systems charts. Both remote network charts drew IN and OUT
  from their own samples. The test switched the monitor among All Systems,
  Local Machine and a different remote while the primary icon continued to
  draw from the same configured remote. Separate icons drew from all three
  individual sources. New and legacy settings restored the monitor and tray
  selections on fresh application instances.
- Verified the portable ZIP CRC and both release-file hashes, x64 executable
  headers, embedded icons and brand metadata. The portable executable opened
  and shut down twice on a private Windows desktop.
- Tested the installer recipe with the release payload and a disposable AppId.
  Installation of v0.4.0.1_alpha, upgrade to v0.4.1.1_alpha and uninstall
  each returned 0. The native wizard displayed the release version. All 292
  installed files matched the release payload. The upgraded executable opened
  and shut down twice. The test settings, credential reference, trust file and
  history fixture survived. The existing installation, startup value, settings
  and SSH trust matched their pre-test values.
- Actual Explorer notification-area hover and an in-place production upgrade
  remain unverified for this version. The private desktops supplied no Explorer
  tray rectangle. Remote validation for this revision used loopback SSH targets.

### Windows x64 release

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| [Installer](release/v0.4.1.1_alpha/AdaptiveResourceMonitor-v0.4.1.1_alpha-windows-x64-setup.exe) | 44,507,774 | 5f82d702cb44318c72a2e4bd7053b42f7387785d2978f9ed5ee6915b6b554900 |
| [Portable ZIP](release/v0.4.1.1_alpha/AdaptiveResourceMonitor-v0.4.1.1_alpha-windows-x64-portable.zip) | 58,360,489 | 841b67a14d593f26369983e78f271b550f4a221de7de695adefb0f7567532b95 |

The [checksum manifest](release/v0.4.1.1_alpha/SHA256SUMS.txt) accompanies both
files. Removed the test installation, staged dependencies and compiler, test
installers and extracted payloads, build intermediates, isolated profiles,
test data and diagnostics. Build and QA staging accounted for **847,063,485
bytes** of removed files by logical size. Retained the two release packages
and their manifest as deliverables. Earlier releases and historical evidence
remain available.

## v0.4.0.1_alpha — Simultaneous monitoring

The Feature counter advanced twice for simultaneous monitoring and
bidirectional network visualization. The Bugfix counter advanced once
for hover selection persistence. The existing collector architecture,
About tab and branding remain in use.

The production feedback for v0.2.0.0_alpha established native installation,
Explorer hover activation, popup pinning, local telemetry and remote
connections to Linux target A, Linux target B and Linux target C. The checks below cover the new
behavior on a private native Windows desktop.

| Requirement | Implementation and verification |
| --- | --- |
| Independent simultaneous views | All Systems renders one row of six resource plots per enabled machine in the hover and expanded monitors. Expanded rows have a Measurements control. The private desktop showed Local Machine, Linux target A, Linux target B and Linux target C together, and a smaller popup viewport exercised both scrollbars. |
| Tray modes | Overlay, Stacked, Composite and Application Icon passed native regression checks. |
| Persistent hover selections | The shared machine selection and hover history range write immediately. Native tests covered dismiss and reopen, pin and unpin, opening and closing the expanded window, minimize and restore, an SSH disconnect and reconnect, and a fresh application process restoring All Systems and the five-minute interval. |
| Independent sampling | The collectors already own separate workers and intervals. An automated stalled-SSH test verified a second worker continued collecting. Live checks observed three distinct SSH workers and separate per-machine histories, with a one-second local interval and two-second remote intervals. |
| Network directions | IN is green and OUT is red by default. Both colors are configurable. A network chart uses one throughput scale across both directions, including the individual interface and archived-data views. Tests covered shared auto and fixed spans, Windows interface replacement, Linux interface replacement, reset and reboot, and legacy combined records. Linux target C produced 20 nonzero live samples in each direction during the run. |
| Existing data | Native monitoring used temporary copies of the existing settings and known-hosts files with the existing credential references. Original files passed before-and-after verification. The existing selected local interfaces reported zero traffic during this run. Linux target C showed unavailable GPU and VRAM values. |

### Resource use with four connected machines

| View | Sample time | CPU, whole workstation | CPU, one logical processor | Working set |
| --- | ---: | ---: | ---: | ---: |
| Tray | 12 s | 0.269% | 4.297% | 152.11 MiB |
| All Systems hover | 12 s | 0.358% | 5.729% | 159.46 MiB |
| All Systems expanded | 12 s | 0.260% | 4.167% | 162.32 MiB |

### Release verification and cleanup

All 17 automated tests passed. Native tray and About regression checks also
passed at 150% Qt scaling. The final portable executable opened and shut
down twice on the private desktop. The final setup and executable passed
x64 and embedded icon checks.

The disposable upgrade used the v0.2.0.0_alpha and v0.4.0.1_alpha frozen
payloads with the release installer recipe and a separate test AppId.
Installation, upgrade and uninstall returned 0. The upgraded installed
executable opened and shut down twice. The settings and original
credential references remained byte-for-byte intact. The copied database
retained its legacy combined reading and received new IN and OUT records.
The production installation and its profile and trust files passed
before-and-after verification. The in-place upgrade and new live Explorer
hover on the active desktop remain production acceptance checks.

| Final release file | Bytes | SHA-256 |
| --- | ---: | --- |
| Windows x64 installer | 44,510,942 | 14df73209ad422e5a7075a75a03cebbedbc41d5a3f72a26a17382734ccccf571 |
| Windows x64 portable ZIP | 58,362,591 | 753ee08ba4c8b452c56cbc560efd3c19e6cef5e583564f165e8d3269ab28f4a6 |

Cleanup removed build staging, the compiler and dependencies, test profile
copies, portable extractions, disposable installs and installers, and
interim screenshots. Measured files reclaimed totaled 1,215,378,958 bytes
(1.13 GiB), excluding short-lived unit-test scratch files. The six requested
screenshots, current release and checksum manifest remain. The previous
release packages were retained because v0.2.0.0_alpha is still the
production installation.

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
| Dynamic Windows tray and Overlay, Stacked, Composite | Implemented using QSystemTrayIcon and QPainter | Resource normalization and per-machine Composite tests | Native Qt builds distinct icon images for all three modes. Explorer registration and recovery need a live taskbar. |
| Custom popup, sizing, dismissal and pinning | Implemented with Windows cursor position and Qt's native notification-area rectangle | Hover state, dismissal, placement and negative-coordinate tests | Popup, six graphs and pinning exercised on a private desktop. Actual pointer movement over an Explorer icon, desktop sleep/resume, and physical mixed-DPI taskbars remain open. |
| Expanded monitor, ranges and multiple machines | Implemented with resource charts, per-device detail, current and history statistics, connection state and timestamps | History and independent machine tests | Expanded window, live values and device selection exercised. Archived statistics use retained plot observations for long selections. |
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
icon images and exercised single and separate tray objects, popup
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
