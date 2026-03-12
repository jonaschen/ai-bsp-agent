---
scope: kernel_pathologist,hardware_advisor
skills:
  - check_clock_dependencies
  - diagnose_vfs_mount_failure
  - analyze_firmware_load_error
  - analyze_early_oom_killer
---

# Subsystem Boot Reference

This document is the knowledge base for Phase 7 subsystem diagnostic skills.
It covers the four most common non-panic kernel/hardware failure patterns
detected during Android BSP bring-up.

---

## 1. Clock Framework (CCF) Probe Defer

### 1.1 How Linux Probe Defer Works

Linux defers device probe when a dependency (clock, regulator, GPIO, IRQ) is
not yet available. The driver calls `clk_get()` (or `devm_clk_get()`), which
returns `-ENOENT` if the provider is not yet registered. The driver propagates
`-EPROBE_DEFER` (-517) up to the bus layer, which reschedules the probe.

Key log signatures:

```
[    1.123456] platform adreno_gpu: deferred_probe_pending
[    1.234567] clk: failed to get clk 'gcc_gpu_cfg_ahb_clk' for adreno_gpu
```

```
[    2.000000] clk_get: cannot get parent clock 'pll_video0' for 'mdss_dsi_clk'
[    2.001000] mdss_dsi: probe with driver failed with error -517
```

### 1.2 Root Cause Patterns

| Pattern | Root Cause | Fix |
|---|---|---|
| `deferred_probe_pending` → no recovery | Clock provider driver never probes | Check if GCC/CAMCC/DISPCC driver is present and probing |
| `clk_get failed` at early boot | DTS `clock-names` typo | Compare driver's expected name vs DTS `clock-names` array |
| Parent clock missing | PLL provider not initialised | Check `assigned-clocks` / `assigned-clock-rates` in DTS |
| Infinite defer loop | Circular dependency | Enable `CONFIG_DEBUG_DRIVER` and check probe ordering |

### 1.3 Debug Commands

```bash
# Dump the full clock tree (requires CONFIG_COMMON_CLK_DEBUG)
cat /sys/kernel/debug/clk/clk_summary

# Show deferred devices
cat /sys/kernel/debug/devices_deferred

# Check if a specific clock is registered
ls /sys/kernel/debug/clk/ | grep gcc_gpu
```

---

## 2. VFS Mount Failures

### 2.1 Mount Failure Sequence

A VFS mount failure stops the kernel at the earliest stage of userspace
transition. The sequence in dmesg is:

1. Block layer detects partition or filesystem error
2. `VFS: Cannot open root device "X" or unknown-block(M,N): error -E`
3. `Kernel panic - not syncing: VFS: Unable to mount root fs`

### 2.2 errno Reference

| errno | Value | Typical Cause |
|---|---|---|
| `ENOENT` | -2 | Partition label not found in partition table |
| `EIO` | -5 | Read error (bad flash sector, eMMC CRC error) |
| `ENXIO` | -6 | Block device not present (driver not loaded, wrong root= cmdline) |
| `EINVAL` | -22 | Corrupt superblock, wrong filesystem type, misaligned partition |
| `ENOSPC` | -28 | Filesystem full (rare at mount time) |

### 2.3 Common Fixes

```bash
# Check root= cmdline parameter
cat /proc/cmdline | grep -o 'root=[^ ]*'

# Run fsck (from recovery)
e2fsck -f /dev/block/bootdevice/by-name/userdata

# Re-check partition table
parted /dev/block/mmcblk0 print
```

---

## 3. Firmware Load Failures

### 3.1 Firmware Search Path

The kernel tries firmware paths in order:
1. `FW_LOADER_USER_HELPER`: userspace via `/sys/class/firmware/`
2. Built-in firmware (`CONFIG_EXTRA_FIRMWARE`)
3. `/lib/firmware/` (rootfs)
4. `/vendor/firmware/` (Android vendor partition)
5. `FW_LOADER_COMPRESS`: `.zst` / `.xz` compressed variants

### 3.2 Log Signatures

```
# Synchronous failure (file missing):
platform ath10k: Direct firmware load for ath10k/QCA9984/hw1.0/firmware-5.bin failed with error -2

# Timeout (userspace not responding):
wifi_drv: request_firmware timed out for 'wifi_drv/fw.bin'
wifi_drv: firmware load failed: -110
```

### 3.3 Fixes

| Error | Fix |
|---|---|
| `-2` (ENOENT) | Copy firmware to `/vendor/firmware/` or `/lib/firmware/` |
| `-110` (ETIMEDOUT) | Ensure `ueventd` / `udevd` is running; check `ueventd.rc` |
| Wrong path | Check driver source for `request_firmware(dev, "path/file.bin")` |
| Compressed | Try adding `.xz` or `.zst` variant |

---

## 4. Early OOM Killer

### 4.1 oom_score_adj Scale

| Score | Process category | Severity if killed |
|---|---|---|
| -1000 | Never killed (kernel threads) | — |
| -900 to -1 | Protected system services (init, surfaceflinger) | **Critical** — device likely unstable |
| 0 | System services (zygote, system_server) | **Critical** — Android framework dies |
| 1–200 | Foreground apps | High — active app killed |
| 201–800 | Background apps / cached | Medium — normal LMK territory |
| 801–1000 | Empty processes | Low — expected to be killed |

### 4.2 Early OOM Causes

An OOM kill before `boot_completed` is unusual and indicates:

- **CMA over-allocation**: Display or camera reserved too much physically
  contiguous memory (DTS `memory-region` sizes too large).
- **tmpfs runaway**: A service is writing large files to `/tmp` or `/dev/shm`
  before the data partition is mounted.
- **Memory leak in init sequence**: A service started early is leaking memory
  (growing `anon-rss` over time).
- **Insufficient total RAM for the software load**: BSP RAM budget needs review.

### 4.3 Debug Commands

```bash
# Memory snapshot at boot time
cat /proc/meminfo

# Per-process memory (sorted by RSS)
ps -eo pid,comm,rss --sort=-rss | head -20

# CMA allocation summary
cat /sys/kernel/debug/cma/cma-<name>/used

# OOM history (if CONFIG_OOM_SCORE is enabled)
dmesg | grep -E "oom_kill|Out of memory"
```

---

## 5. Emulator Gaps

| Skill | Gap | Note |
|---|---|---|
| `check_clock_dependencies` | QEMU virt uses simple clock model — no CCF defer | Patterns validated against synthetic logs only |
| `diagnose_vfs_mount_failure` | QEMU virt always mounts cleanly | Test via injected error logs |
| `analyze_firmware_load_error` | QEMU virt has no WiFi/modem firmware | Patterns cover standard kernel format only |
| `analyze_early_oom_killer` | QEMU virt has sufficient RAM for basic tests | OOM patterns are stable across kernel versions |
