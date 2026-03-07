---
scope: hardware_advisor
trigger: STD hibernation failure, Error -12, SUnreclaim, SwapFree, memory allocation
skill: analyze_std_hibernation_error
---

# Memory Reclamation & STD Hibernation Failures

## Overview

Android STD (Suspend-to-Disk) hibernation requires the kernel to allocate a contiguous
memory region large enough to hold a snapshot of all RAM in use. If allocation fails,
the kernel returns `-ENOMEM` (errno 12), logged as:

```
Error -12 creating hibernation image
```

Two primary causes account for the majority of field failures:

1. **High SUnreclaim** — unreclaimable slab memory occupying too much physical RAM
2. **Insufficient Swap** — no swap space for the kernel to relocate pages before snapshot

---

## Key `/proc/meminfo` Fields

| Field | Description | Diagnostic Use |
|---|---|---|
| `MemTotal` | Total physical RAM (kB) | Denominator for SUnreclaim ratio |
| `MemFree` | Immediately available RAM | Low value increases hibernation pressure |
| `SUnreclaim` | Slab memory that cannot be reclaimed | Primary failure indicator when > 10% of MemTotal |
| `SReclaimable` | Slab memory that CAN be reclaimed | `echo 3 > drop_caches` frees this |
| `SwapTotal` | Total swap space | 0 means hibernation cannot relocate pages |
| `SwapFree` | Free swap space | 0 kB = no room for hibernation image |

---

## Diagnostic Logic

### Root Cause 1: High SUnreclaim

**Threshold:** `SUnreclaim / MemTotal > 10%`

SUnreclaim comes primarily from:
- **dentry/inode caches** that are pinned (e.g., by open file descriptors)
- **Kernel module data structures** that are not freed on suspend
- **Filesystem journal buffers** under heavy I/O load

**Remediation:**
```bash
echo 3 > /proc/sys/vm/drop_caches   # drops pagecache, dentries, inodes
```
Note: This releases `SReclaimable` slab memory first. If `SUnreclaim` itself is high,
the root cause is kernel data structures that cannot be dropped — investigate with:
```bash
cat /proc/slabinfo | sort -k3 -rn | head -20
```

### Root Cause 2: Insufficient Swap

**Threshold:** `SwapFree == 0 kB`

The hibernation image requires swap space equal to the compressed image size
(typically 40–60% of RAM in use). If `SwapTotal == 0`, no swap partition is configured.

**Remediation (permanent):**
```
# In device tree or fstab, ensure a swap partition of at least MemTotal size exists.
# Minimum recommended: SwapTotal >= MemTotal
```

**Remediation (temporary, for debugging):**
```bash
dd if=/dev/zero of=/swap bs=1M count=2048
mkswap /swap && swapon /swap
```

---

## STD Phase Sequence

```
Freeze user processes
    → Freeze kernel threads
        → Checkpoint 1: Allocate hibernation memory
        → Checkpoint 2: Create hibernation image  ← Error -12 occurs here
            → Write image to swap/disk
                → Poweroff
```

If `Error -12` appears at Checkpoint 2, the allocation at the start of image creation
failed. Capturing `/proc/meminfo` **at the moment of failure** (via a crash notifier or
`kmsg` dump) is essential for accurate diagnosis.

---

## Wearable Device Specifics

Wearable devices (e.g., smartwatches) typically have:
- **512 MB – 2 GB RAM** — very tight headroom for slab growth
- **eMMC / UFS swap** — limited write endurance; swap may be disabled to protect flash
- **Vendor suspend hooks** — custom `dev_pm_ops` callbacks that may pin memory

When swap is intentionally disabled (to protect flash), the vendor BSP must ensure
the hibernation image fits entirely within free RAM after slab reclamation.

---

## References

- Linux kernel: `mm/hibernate.c` — `hibernate_preallocate_memory()`
- Linux kernel: `mm/slab_common.c` — slab accounting
- Android Power HAL: `vendor/qcom/proprietary/android-perf/`
