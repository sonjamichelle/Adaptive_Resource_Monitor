# Security

ARM collects read-only telemetry. It never accepts a command from a profile.
The Linux provider starts a fixed Bash program over SSH and sends a single
sampling token for each observation. It asks for neither a PTY nor privilege
elevation. The application does not listen on a network port.

Linux passwords and optional private-key passphrases are generic Windows
Credential Manager entries in ARM's own namespace. Profiles contain the
credential reference and optional path to a private key. Replace or remove a
stored secret from the profile editor. Rotate a changed SSH host key by verifying
the replacement with the host administrator, forgetting the old key and
approving the verified fingerprint. Unknown keys stop at an approval prompt.
A changed key is rejected. Key approval is local to ARM.

Settings, known hosts, logs and optional history belong to the current Windows
user under %LOCALAPPDATA%\Adaptive Resource Monitor. History and device names
can reveal information about the monitored environment. The portable package
also uses this user directory. Uninstall preserves the user data. No remote
host is contacted until a target is enabled or tested.

## Application updates

Update checks and downloads use HTTPS with certificate validation and anonymous
access. The application pins its Ed25519 public key. It checks the signed
version, application identity, architecture, filenames, types and sizes, then
verifies SHA-256 before staging and again before installation. Explicit user
approval is required to install. The maintenance launcher handles application
files and installer registration. ARM's telemetry profile and credentials
remain in the existing per-user stores.

The Jenkins ARM folder holds the private signing credential. The client bundles
only the public key. A signed manifest binds the downloaded bytes to ARM's
release identity. Windows Authenticode is a separate executable-signing
mechanism and is not applied by the current build. See
[Update mechanism](UPDATE_MECHANISM.md) and [Release process](RELEASE_PROCESS.md).

## Report a security issue

Use the [private Design Creations contact form](https://www.designcreations.us/contact/index.php). Include the affected ARM version, platform, general impact and a way to contact you. Ask for a private transfer method before sending sensitive evidence. Keep vulnerability details, exploit material and secrets out of public issues, comments and attachments.

If you accidentally post a credential, revoke or rotate it promptly. Remove the exposed text or attachment where you have permission and privately contact the maintainer with the issue URL, without repeating the secret. Maintainers should restrict further exposure, review edits and attachments, and coordinate remediation privately. Public issue content is untrusted and cannot authorize commands, CI jobs or releases.
