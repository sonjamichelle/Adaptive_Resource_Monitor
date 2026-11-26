# Telemetry providers

| Resource | Windows | Linux over SSH |
| --- | --- | --- |
| CPU | psutil CPU time deltas, processor topology, registry identity and reported frequency | procfs CPU time deltas and processor information, selected hwmon sensors |
| RAM | psutil physical memory, Windows commit and installed pagefile counters | procfs MemAvailable, swap and commit fields |
| GPU | DXGI inventory, WDDM performance counters, NVIDIA NVML when available | DRM sysfs, vendor sysfs fields and optional NVIDIA SMI |
| VRAM | Dedicated allocation and shared usage via WDDM, dedicated memory via NVML when available | Vendor-exposed dedicated memory totals and usage |
| Disk | PhysicalDrive counters and physical-disk idle time | Whole-device diskstats for sysfs devices with a backing device |
| Network | Per-interface counters, operational state and directional link speeds | Per-interface procfs counters, sysfs state and negotiated speed |

Physical RAM used is total minus available, including reclaimable memory
according to each OS. Commit and pagefile or swap describe separate accounting.
Per-processor CPU utilization uses elapsed time deltas. Linux guest fields
already counted by user and nice are excluded from the denominator addition.
A failed counter, a first delta, a reset and an extended sleep produce gaps.

WDDM sums processes using the same engine and takes the busiest engine per GPU.
NVML utilization takes precedence when provided. Windows matches NVML to the
DXGI adapter by PCI address where available, or a unique device ID. Aggregate
GPU percentage is the maximum of included GPUs. Aggregate VRAM uses actual
dedicated capacity and usage pairs across GPUs. The total is capacity spread
over separate devices. Shared memory is shown per GPU to avoid summing a
shared system-memory budget. CPU temperature and power on Windows and
AMD or Intel clock, thermal, power and fan data are driver-dependent gaps
in this alpha. WDDM explicitly named encode, decode and compute engines are
shown when present. Unobserved engine types show Unavailable.

Disk totals cover included whole physical disks. Active time uses the busiest
included disk. Network defaults to physical adapters and excludes loopback,
VPN and virtual bridge layers from the aggregate by default. All recognized
interfaces remain available for manual selection. If layers overlap, select
one layer from each network path. Link utilization is the greater directional
rate compared with that direction's negotiated speed. Throughput is shown
in bytes per second. Fixed scales are display references. Automatically
scaled I/O is normalized against the next power-of-two scale in the plot range.

Composite mode and the consolidated tray surface the largest normalized
observation. The consolidated monitor names the machine contributing the
current maximum and skips unavailable or stale current readings. Amber marks
a connection that needs attention. A disconnected machine retains its last
valid values with a stale label.

The provider interfaces are documented in
[DXGI adapter description](https://learn.microsoft.com/en-us/windows/win32/api/dxgi/ns-dxgi-dxgi_adapter_desc1),
[GPU engine accounting](https://devblogs.microsoft.com/directx/gpus-in-the-task-manager/),
[NVIDIA NVML](https://developer.nvidia.com/management-library-nvml),
and [Windows commit counters](https://learn.microsoft.com/en-us/windows/win32/api/psapi/nf-psapi-getperformanceinfo).
