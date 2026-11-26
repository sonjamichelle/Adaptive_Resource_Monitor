# Initial Windows alpha requirements

The initial version is `v0.1.0.0_alpha`. The local application is a Windows 10/11 x64 system tray utility with live CPU, GPU, RAM, VRAM, disk and network history. The default icon overlays all six resources. Stacked and peak composite views, configurable sampling, a native hover monitor, expanded and per-device views, and optional retained history are part of the milestone.

Remote targets have independent state and schedules. Linux uses password or key SSH authentication, explicit host-key trust, Windows Credential Manager and read-only telemetry. Configured targets can be monitored individually or consolidated. Remote Windows design is documented separately from verified support.

Deliver a frozen portable ZIP, a native installer, checksums, automated tests and native Windows validation. See [implementation report](IMPLEMENTATION_REPORT.md) for the requirement matrix, evidence and acceptance limits.
