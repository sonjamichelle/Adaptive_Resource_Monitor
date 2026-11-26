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
