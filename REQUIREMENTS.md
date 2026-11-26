# Initial Windows alpha requirements

## Simultaneous monitoring and visualization

All Systems shows six independent resource graphs for each enabled monitored
machine. The hover and expanded monitors offer Local Machine, configured
remote machines and All Systems. The hover machine and history range
persist immediately and survive a disconnected target. The primary tray
icon has an independent machine setting and defaults to Local Machine.
Optional individual tray icons and the Overlay, Stacked and Composite
visualizations use data from one machine per icon.

Network plots show independent green receive and red transmit series by
default and share one automatic or fixed throughput scale. Historical
combined readings remain available in detailed measurements.

The initial version is `v0.1.0.0_alpha`. The local application is a Windows 10/11 x64 system tray utility with live CPU, GPU, RAM, VRAM, disk and network history. The default icon overlays all six resources. Stacked and Composite views, configurable sampling, a native hover monitor, expanded and per-device views, and optional retained history are part of the milestone.

Remote targets have independent state and schedules. Linux uses password or key SSH authentication, explicit host-key trust, Windows Credential Manager and read-only telemetry. Configured targets can be monitored individually or viewed alongside one another in All Systems. Remote Windows design is documented separately from verified support.

Deliver a frozen portable ZIP, a native installer, checksums, automated tests and native Windows validation. See [implementation report](IMPLEMENTATION_REPORT.md) for the requirement matrix, evidence and acceptance limits.
