# Remote monitoring

In Manage Remote Targets, add a Linux target with its real hostname, port and
username. Choose Password or Private key and enter a password or key
passphrase when required. New targets start disabled. Use Test connection to
request the key and run a single telemetry sample. Compare the SHA-256
fingerprint to one obtained directly from the system or its administrator,
then use Approve SSH host key and enable the target.

Each target owns its own SSH connection, sampling interval, timeout and retry
schedule. Transient failures retry with exponential backoff when enabled.
Authentication failures, new keys and changed keys require user action.
The monitor labels the last valid sample stale when its provider goes offline.
Linux requires Bash, procfs and readable sysfs. NVIDIA telemetry additionally
uses an installed nvidia-smi and timeout when available. AMD and Intel use
available sysfs attributes. Root access and package installation are unnecessary.

Windows targets can be stored as profiles. Their provider reports Unsupported
in this alpha. Microsoft's remote performance counter APIs depend on RPC or
Remote Registry in some cases. CIM over WinRM has an authenticated transport
and can expose Windows performance classes with appropriate per-host rights.
A later optional agent should expose a small versioned telemetry schema
over mutually authenticated TLS and restrict requests to metrics and sampling
configuration. These routes have no deployed implementation in this version.
See [remote performance counter access](https://learn.microsoft.com/en-gb/windows/win32/perfctrs/accessing-remote-counter-data)
and [WinRM authentication](https://learn.microsoft.com/en-us/windows/win32/winrm/authentication-for-remote-connections).
