# Emulator Specification — BSP Diagnostic Skill Training Environment

This document is the authoritative record of every emulator environment used to
generate the training and validation logs for the BSP Diagnostic Agent skill set.

When an end-user's agent encounters a log pattern that is not recognised by the
built-in skills, this document tells them which emulator produced the training data
and where the gap lies — so they can use `suggest_pattern_improvement` to extend
the skill for their specific hardware. See `docs/skill-extension-guide.md` for the
extension workflow.

---

## 1. Host System Requirements

| Requirement | Minimum | Tested on |
|---|---|---|
| OS | Ubuntu 22.04 LTS (x86_64) | Ubuntu 22.04 / 24.04 |
| CPU | x86_64, 4 cores | Intel/AMD, any generation |
| RAM | 8 GB | 16 GB recommended |
| Disk | 20 GB free | SSD strongly recommended |
| KVM | Optional for LK/Alpine (TCG) | Required for fast Android AVD |
| Kernel | 5.15+ | 6.8.x tested |

> **AArch64 targets run in TCG (software emulation)** on an x86_64 host.
> KVM cannot be used because the host ISA does not match the guest ISA.
> Android AVD benefits from KVM (`kvm_intel` or `kvm_amd` kernel module).

---

## 2. Software Package Versions

### 2.1 QEMU

| Item | Value |
|---|---|
| Package | `qemu-system-aarch64`, `qemu-utils` |
| Source | Ubuntu `apt` repository |
| Ubuntu 22.04 version | 1:6.2+dfsg-2ubuntu6.x |
| Ubuntu 24.04 version | 1:8.2.x+dfsg-…  |
| Minimum required | 6.0 (virtio-scsi, `cortex-a72` TCG support) |
| Key flags used | `-machine virt`, `-bios none`, `-nographic`, `-serial stdio/file:` |

Verify installed version:
```bash
qemu-system-aarch64 --version
```

### 2.2 Little Kernel (LK)

| Item | Value |
|---|---|
| Repository | `https://github.com/littlekernel/lk.git` |
| Clone depth | `--depth=1` (latest HEAD of `main`) |
| Build target | `qemu-virt-arm64-test` |
| Output | `build-qemu-virt-arm64-test/lk.elf` |
| Cross-compiler | `gcc-aarch64-linux-gnu` (Ubuntu package) |
| GCC version (22.04) | 12.x (`aarch64-linux-gnu-gcc --version`) |
| ARCH flag | `ARCH=arm64` |
| TOOLCHAIN_PREFIX | `aarch64-linux-gnu-` |

**Pinning LK to a reproducible commit** (recommended for production validation):
```bash
git clone https://github.com/littlekernel/lk.git
git -C lk log --oneline -1   # record this hash
```
Store the hash in your environment's `VERSION.lock` alongside this spec.

The `setup.sh` currently does a floating `--depth=1` clone. End users who need
exact reproducibility should pin the LK commit and rebuild.

### 2.3 Alpine Linux (AArch64 guest)

| Item | Value |
|---|---|
| Version | 3.19.1 |
| Architecture | aarch64 |
| ISO filename | `alpine-virt-3.19.1-aarch64.iso` |
| Download URL template | `https://dl-cdn.alpinelinux.org/alpine/v3.19/releases/aarch64/alpine-virt-3.19.1-aarch64.iso` |
| Linux kernel version | 6.6.x LTS (shipped with Alpine 3.19) |
| Init system | BusyBox init |
| Disk image | qcow2, 4 GB (`qemu-img create -f qcow2 … 4G`) |

The Linux kernel version determines which kernel log formats the skills are
trained on. Alpine 3.19 ships kernel **6.6.x LTS**. If your production kernel
is older (e.g. 4.14 GKI or 5.10 GKI), log-format differences may require
pattern extensions — especially for watchdog and Oops headers.

### 2.4 Android SDK / AVD

| Item | Value |
|---|---|
| cmdline-tools zip | `commandlinetools-linux-11076708_latest.zip` |
| SDK root | `$HOME/android-sdk` |
| Platform API level | android-34 (Android 14) |
| System image | `system-images;android-34;google_apis;x86_64` |
| AVD name | `boot_log_avd` |
| AVD device profile | `pixel_6` |
| AVD RAM (normal) | 2048 MB |
| AVD RAM (slow-boot) | 1024 MB |
| Emulator renderer | `swiftshader_indirect` (no GPU required) |

Verify installed SDK components:
```bash
sdkmanager --list_installed --sdk_root=$HOME/android-sdk
```

### 2.5 Support Tools

| Tool | Package | Purpose |
|---|---|---|
| `expect` | `expect` (apt) | LK UART interaction in `run-linux-qemu.sh` |
| `socat` | `socat` (apt) | QEMU monitor socket commands |
| `adb` | `android-tools-adb` (apt) or SDK platform-tools | Android log capture |
| `avdmanager` | Android cmdline-tools | AVD lifecycle management |
| Python | `python3` ≥ 3.10 | `cli.py`, `tools/validate_logs.py` |

---

## 3. Emulation Targets

### 3.1 LK AArch64 (Little Kernel)

**Purpose:** Validate `parse_early_boot_uart_log` and `analyze_lk_panic` skills.
Produces real bootloader-stage UART output without an OS.

| Parameter | Value |
|---|---|
| Machine | `virt` |
| CPU | `cortex-a53` |
| RAM | `256M` |
| SMP | 1 vCPU |
| BIOS | none (`-bios none`) |
| Kernel image | `lk.elf` (ELF loaded directly via `-kernel`) |
| Console | `-nographic -serial stdio` |
| Acceleration | TCG only (no KVM) |
| Boot time | < 5 s to shell prompt |

**What this target produces:**
- LK initialisation sequence (GIC, timer, memory, display stub)
- LK shell prompt `] ` or `> `
- AArch64 crash dump on `crash` command: registers `x0`–`x29`, `elr`, `spsr`,
  ESR `0x96000044` (level-0 DABT, write), stack trace

**What this target cannot produce:**
- Qualcomm / MediaTek / Samsung vendor bootloader messages
- Real DDR PHY training output (LK virt target skips DDR)
- TF-A BL1/BL2/BL31 stage transitions (LK is loaded directly, no TF-A stack)

### 3.2 Alpine Linux AArch64 (Full Kernel)

**Purpose:** Validate all `kernel_pathologist` and `hardware_advisor` skills with
real Linux kernel output.

| Parameter | Value |
|---|---|
| Machine | `virt` |
| CPU | `cortex-a72` |
| RAM | `512M` |
| SMP | 2 vCPUs |
| Drive 0 | qcow2 overlay of `alpine-aarch64-disk.qcow2` |
| Drive 1 | Alpine ISO (cdrom, virtio-scsi, read-only) |
| Boot order | `dc` (disk, then cdrom) |
| Console | `-nographic -serial file:<logfile>` |
| Monitor | UNIX socket `/tmp/qemu-aarch64-monitor.sock` |
| Acceleration | TCG only |
| Network | virtio-net, user-mode (SLIRP) |
| Boot time | 60–120 s (TCG is slow) |

**What this target produces:**
- Full Linux 6.6.x kernel init: `[    0.000000]` timestamps, subsystem init
- Panic via sysrq-c: `Kernel panic - not syncing: sysrq triggered crash`
- AppArmor / audit denial lines (augmented post-boot in `augment_logs_with_errors`)
- Hardware error injections (added via `cat >>` in `augment_logs_with_errors`):
  - `mmc0: Timeout waiting for hardware interrupt`
  - `ata1: SRST failed (errno=-16)`
  - `thermal thermal_zone0: failed to read out thermal zone (-61)`

**Injected patterns** (synthetic, not from live kernel):
All log lines in `logs/validation/d2_*`, `logs/validation/d3_*` that reference
UFS, PMIC, watchdog, AArch64 Oops, or cache coherency are **injected** into the
Alpine serial output by post-processing scripts or crafted as standalone fixture
files. The Alpine kernel does not natively generate these messages.

**What this target cannot produce without injection:**
- UFS driver errors (no UFS controller on QEMU virt)
- PMIC rail voltage messages (no PMIC on QEMU virt)
- AArch64 Oops with real ESR/FAR from a kernel crash (sysrq-c produces an x86-
  style panic on the host kernel's x86_64 format when cross-emulated;
  AArch64 Oops format requires running inside the AArch64 guest, which Alpine's
  sysrq-c does produce correctly in TCG)
- Vendor-specific kernel module messages (Qualcomm, MediaTek, Samsung)
- watchdog timeouts from real hardware interrupt contention

### 3.3 Android AVD (x86_64)

**Purpose:** Validate `segment_boot_log` (android_init stage) and provide
SELinux AVC denial samples for Phase 6 (`android_init_advisor`).

| Parameter | Value |
|---|---|
| AVD API level | Android 14 (API 34) |
| ABI | x86_64 |
| Device | Pixel 6 (hardware profile) |
| Renderer | SwiftShader (software, no GPU) |
| RAM (normal) | 2048 MB |
| RAM (slow boot) | 1024 MB |
| Emulator flags | `-no-window -no-audio -no-snapshot -wipe-data` |
| ADB transport | `localhost:5554` (default emulator port) |

**Log artifacts captured per cycle:**
- `dmesg_*.txt` — kernel dmesg via `adb shell dmesg`
- `logcat_*.txt` — full logcat (`adb logcat -d -b all`)
- `last_kmsg_*.txt` — previous boot panic log (`/proc/last_kmsg`)
- `boot_events_*.txt` — filtered logcat events (`boot_|am_|wm_`)
- `getprop_*.txt` — full system properties snapshot
- `selinux_*.txt` — AVC lines from dmesg

**What this target cannot produce:**
- AArch64 Oops (AVD kernel is x86_64)
- Qualcomm / MediaTek bootloader messages
- Real hardware peripheral errors
- Pre-kernel UART (early_boot stage)

---

## 4. Scenario-to-Skill Mapping

| Script | Scenario | Emulator | Skills Validated | Log IDs |
|---|---|---|---|---|
| `run-linux-qemu.sh` | `lk-normal` | LK AArch64 | `segment_boot_log`, `parse_early_boot_uart_log` (healthy path) | LOG-026 |
| `run-linux-qemu.sh` | `lk-panic` | LK AArch64 | `analyze_lk_panic`, `decode_esr_el1` | LOG-009 |
| `run-linux-qemu.sh` | `linux-panic` | Alpine aarch64 | `extract_kernel_oops_log`, `analyze_watchdog_timeout`, `check_cache_coherency_panic` | LOG-010…LOG-017 |
| `run-linux-qemu.sh` | `linux-audit` | Alpine aarch64 | Phase 6 preview (`analyze_selinux_denial`) | LOG-027 (partial) |
| `run-android-emulator.sh` | `normal` | Android AVD | `segment_boot_log` (android_init) | LOG-001, LOG-028 |
| `run-android-emulator.sh` | `selinux` | Android AVD | Phase 6 (`analyze_selinux_denial`) | LOG-027 |
| `run-android-emulator.sh` | `slow` | Android AVD | `segment_boot_log` (timing baseline) | LOG-028 |
| `run-android-emulator.sh` | `panic` | Android AVD | `extract_kernel_oops_log` (`last_kmsg` post-panic) | LOG-010 |

All logs referenced above are enumerated in `LOG_PENDING_LIST.md`.

---

## 5. Known Emulator Gaps (Requires Real Hardware or Synthetic Injection)

The following patterns appear on real BSP hardware but cannot be generated by
these emulators. They must be added via `suggest_pattern_improvement` when
encountered on target hardware.

| Pattern class | Root cause of gap | Affected skills |
|---|---|---|
| Qualcomm DDR PHY training output | LK virt skips DDR PHY; QC format is vendor-specific | `parse_early_boot_uart_log` |
| MediaTek / Samsung PMIC rail names | Only `qpnp`, `rpm-smd`, and generic formats trained | `check_pmic_rail_voltage` |
| Vendor UFS error codes beyond `-5/-110` | QEMU virt has no UFS controller | `check_vendor_boot_ufs_driver` |
| Pre-kernel secure monitor messages (ATF-proprietary) | TF-A in QEMU uses reference platform messages only | `parse_early_boot_uart_log` |
| Android init.rc service failures on real SoCs | AVD init.rc differs from product init.rc | Phase 6 `check_android_init_rc` |
| GKI 4.14 / 5.10 kernel Oops format | Alpine 3.19 ships 6.6 LTS; older kernels use different Oops headers | `extract_kernel_oops_log` |
| Watchdog on multi-cluster CPU topology | QEMU virt has symmetric SMP only | `analyze_watchdog_timeout` |

---

## 6. Reproducing the Emulator Environment

```bash
# 1. Install all dependencies and build LK
cd emulator_scripts
./setup.sh

# 2. Generate LK + Alpine Linux logs
./run-linux-qemu.sh ./logs/linux 3

# 3. Generate Android AVD logs
./run-android-emulator.sh ./logs/android 3

# 4. Normalize all logs
./collect-logs.sh ./logs/android ./logs/linux ./logs/normalized

# 5. Validate each log file against its expected skill output
python tools/validate_logs.py

# 6. Feed a specific log to the agent
source venv/bin/activate
python cli.py --dmesg logs/normalized/linux/linux-panic.log
```

---

## 7. Version Lock File (Recommended for Production Teams)

End users who deploy this agent on real hardware should maintain a
`VERSION.lock` file in their project root with the following fields:

```json
{
  "bsp_agent_commit": "<git SHA of this repo>",
  "lk_commit": "<git SHA of littlekernel/lk used to build lk.elf>",
  "alpine_version": "3.19.1",
  "alpine_kernel": "6.6.x",
  "android_api": 34,
  "cmdline_tools_build": "11076708",
  "qemu_version": "<output of qemu-system-aarch64 --version>",
  "gcc_cross_version": "<output of aarch64-linux-gnu-gcc --version | head -1>",
  "skill_extensions_file": "~/.bsp-diagnostics/skill_extensions.json",
  "skill_extensions_version": 1
}
```

This allows the team to correlate a diagnostic session's findings with the
exact emulator snapshot that produced the training data.
