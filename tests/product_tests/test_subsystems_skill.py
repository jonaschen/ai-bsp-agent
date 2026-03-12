"""
Tests for skills/bsp_diagnostics/subsystems.py — Phase 7 Subsystem Diagnostics.

Covers:
  check_clock_dependencies    — CCF probe-defer / clk_get failures
  diagnose_vfs_mount_failure  — VFS mount errors
  analyze_firmware_load_error — firmware request failures
  analyze_early_oom_killer    — early OOM kill events

All tests are deterministic: no LLM calls, no network, no I/O.
"""
import pytest

from skills.bsp_diagnostics.subsystems import (
    ClockDepsInput,
    ClockDepsOutput,
    VFSMountInput,
    VFSMountOutput,
    FirmwareLoadInput,
    FirmwareLoadOutput,
    EarlyOOMInput,
    EarlyOOMOutput,
    check_clock_dependencies,
    diagnose_vfs_mount_failure,
    analyze_firmware_load_error,
    analyze_early_oom_killer,
)


# ---------------------------------------------------------------------------
# Fixtures — clock dependencies
# ---------------------------------------------------------------------------

CLEAN_LOG = """\
[    0.100000] init: starting
[    1.000000] Boot completed
"""

CLOCK_DEFER_LOG = """\
[    1.123456] platform adreno_gpu: deferred_probe_pending
[    1.234567] clk: failed to get clk 'gcc_gpu_cfg_ahb_clk' for adreno_gpu
[    1.345678] adreno_gpu: probe deferred due to missing clock
"""

CLOCK_PARENT_LOG = """\
[    2.000000] clk_get: cannot get parent clock 'pll_video0' for 'mdss_dsi_clk'
[    2.001000] mdss_dsi: probe with driver failed with error -517
"""

CLOCK_MULTI_LOG = """\
[    1.000000] platform sdhci@7c4000: deferred_probe_pending
[    1.001000] clk: failed to get clk 'sdhci_clk' for sdhci@7c4000
[    1.002000] platform i2c@7880000: deferred_probe_pending
[    1.003000] clk: failed to get clk 'i2c_core_clk' for i2c@7880000
"""


# ---------------------------------------------------------------------------
# Fixtures — VFS mount failure
# ---------------------------------------------------------------------------

VFS_MOUNT_FAIL_LOG = """\
[    5.123456] EXT4-fs (mmcblk0p14): unable to read superblock
[    5.234567] VFS: Cannot open root device "mmcblk0p14" or unknown-block(0,0): error -6
[    5.345678] Please append a correct "root=" boot option
[    5.456789] Kernel panic - not syncing: VFS: Unable to mount root fs on unknown-block(0,0)
"""

VFS_EINVAL_LOG = """\
[    4.000000] FAT-fs (mmcblk0p1): bogus logical sector size 0
[    4.001000] VFS: Cannot open root device "mmcblk0p1" or unknown-block(179,1): error -22
"""

VFS_CLEAN_LOG = """\
[    5.000000] EXT4-fs (mmcblk0p14): mounted filesystem with ordered data mode
[    5.001000] VFS: Mounted root (ext4 filesystem) on device 179:14.
"""


# ---------------------------------------------------------------------------
# Fixtures — firmware load error
# ---------------------------------------------------------------------------

FW_LOAD_FAIL_LOG = """\
[   10.123456] platform ath10k: Direct firmware load for ath10k/QCA9984/hw1.0/firmware-5.bin failed with error -2
[   10.234567] ath10k_pci 0000:01:00.0: failed to fetch firmware: -2
[   10.345678] ath10k_pci 0000:01:00.0: could not load firmware
"""

FW_TIMEOUT_LOG = """\
[   15.000000] wifi_drv: request_firmware timed out for 'wifi_drv/fw.bin'
[   15.001000] wifi_drv: firmware load failed: -110
"""

FW_CLEAN_LOG = """\
[   10.000000] platform ath10k: Loaded firmware version 10.4.1.00030
[   10.001000] ath10k_pci 0000:01:00.0: firmware booted
"""


# ---------------------------------------------------------------------------
# Fixtures — early OOM killer
# ---------------------------------------------------------------------------

OOM_LOG = """\
[    8.123456] oom_reaper: reaped process 1234 (cameraserver), now anon-rss:0kB, file-rss:0kB, shmem-rss:0kB
[    8.234567] Out of memory: Killed process 1234 (cameraserver) total-vm:512000kB, anon-rss:480000kB, file-rss:3200kB, oom_score_adj:500
[    8.345678] oom_kill_process: OOM victim: 1234 (cameraserver)
"""

OOM_EARLY_LOG = """\
[    3.000000] Out of memory: Killed process 500 (zygote) total-vm:1024000kB, anon-rss:900000kB, file-rss:8000kB, oom_score_adj:0
"""

OOM_CLEAN_LOG = """\
[    8.000000] init: starting service 'zygote'...
[    8.100000] zygote: boot complete
"""


# ===========================================================================
# check_clock_dependencies
# ===========================================================================

class TestClockDepsSchemas:
    def test_input_schema(self):
        inp = ClockDepsInput(dmesg_log="test")
        assert inp.dmesg_log == "test"

    def test_output_fields_present(self):
        out = check_clock_dependencies(CLEAN_LOG)
        assert isinstance(out, ClockDepsOutput)
        assert hasattr(out, "failure_detected")
        assert hasattr(out, "deferred_devices")
        assert hasattr(out, "missing_clocks")
        assert hasattr(out, "root_cause")
        assert hasattr(out, "recommended_action")
        assert hasattr(out, "confidence")

    def test_output_serialisable(self):
        out = check_clock_dependencies(CLOCK_DEFER_LOG)
        d = out.model_dump()
        assert isinstance(d["deferred_devices"], list)
        assert isinstance(d["missing_clocks"], list)


class TestClockDepsNoFailure:
    def test_clean_log(self):
        out = check_clock_dependencies(CLEAN_LOG)
        assert out.failure_detected is False

    def test_empty_log(self):
        out = check_clock_dependencies("")
        assert out.failure_detected is False

    def test_high_confidence_on_clean(self):
        out = check_clock_dependencies(CLEAN_LOG)
        assert out.confidence >= 0.85


class TestClockDeferDetection:
    def setup_method(self):
        self.out = check_clock_dependencies(CLOCK_DEFER_LOG)

    def test_failure_detected(self):
        assert self.out.failure_detected is True

    def test_deferred_device_extracted(self):
        assert any("adreno_gpu" in d for d in self.out.deferred_devices)

    def test_missing_clock_extracted(self):
        assert any("gcc_gpu_cfg_ahb_clk" in c for c in self.out.missing_clocks)

    def test_root_cause_mentions_probe_defer(self):
        assert "defer" in self.out.root_cause.lower() or "clock" in self.out.root_cause.lower()

    def test_reasonable_confidence(self):
        assert self.out.confidence >= 0.75


class TestClockParentMissing:
    def setup_method(self):
        self.out = check_clock_dependencies(CLOCK_PARENT_LOG)

    def test_failure_detected(self):
        assert self.out.failure_detected is True

    def test_missing_clock_extracted(self):
        assert any("pll_video0" in c for c in self.out.missing_clocks)


class TestClockMultiDevice:
    def test_multiple_deferred_devices(self):
        out = check_clock_dependencies(CLOCK_MULTI_LOG)
        assert out.failure_detected is True
        assert len(out.deferred_devices) >= 2

    def test_multiple_missing_clocks(self):
        out = check_clock_dependencies(CLOCK_MULTI_LOG)
        assert len(out.missing_clocks) >= 2


# ===========================================================================
# diagnose_vfs_mount_failure
# ===========================================================================

class TestVFSSchemas:
    def test_input_schema(self):
        inp = VFSMountInput(dmesg_log="test")
        assert inp.dmesg_log == "test"

    def test_output_fields_present(self):
        out = diagnose_vfs_mount_failure(CLEAN_LOG)
        assert isinstance(out, VFSMountOutput)
        assert hasattr(out, "failure_detected")
        assert hasattr(out, "device")
        assert hasattr(out, "error_code")
        assert hasattr(out, "fs_type")
        assert hasattr(out, "root_cause")
        assert hasattr(out, "recommended_action")
        assert hasattr(out, "confidence")

    def test_output_serialisable(self):
        out = diagnose_vfs_mount_failure(VFS_MOUNT_FAIL_LOG)
        d = out.model_dump()
        assert isinstance(d, dict)


class TestVFSNoFailure:
    def test_clean_log(self):
        out = diagnose_vfs_mount_failure(VFS_CLEAN_LOG)
        assert out.failure_detected is False

    def test_empty_log(self):
        out = diagnose_vfs_mount_failure("")
        assert out.failure_detected is False

    def test_high_confidence_on_clean(self):
        out = diagnose_vfs_mount_failure(VFS_CLEAN_LOG)
        assert out.confidence >= 0.85


class TestVFSMountDetection:
    def setup_method(self):
        self.out = diagnose_vfs_mount_failure(VFS_MOUNT_FAIL_LOG)

    def test_failure_detected(self):
        assert self.out.failure_detected is True

    def test_device_extracted(self):
        assert self.out.device is not None
        assert "mmcblk0p14" in self.out.device

    def test_error_code_extracted(self):
        assert self.out.error_code is not None

    def test_reasonable_confidence(self):
        assert self.out.confidence >= 0.75


class TestVFSEINVAL:
    def setup_method(self):
        self.out = diagnose_vfs_mount_failure(VFS_EINVAL_LOG)

    def test_failure_detected(self):
        assert self.out.failure_detected is True

    def test_device_extracted(self):
        assert "mmcblk0p1" in (self.out.device or "")

    def test_error_code_is_einval(self):
        assert self.out.error_code == -22


# ===========================================================================
# analyze_firmware_load_error
# ===========================================================================

class TestFirmwareSchemas:
    def test_input_schema(self):
        inp = FirmwareLoadInput(dmesg_log="test")
        assert inp.dmesg_log == "test"

    def test_output_fields_present(self):
        out = analyze_firmware_load_error(CLEAN_LOG)
        assert isinstance(out, FirmwareLoadOutput)
        assert hasattr(out, "failure_detected")
        assert hasattr(out, "firmware_files")
        assert hasattr(out, "drivers")
        assert hasattr(out, "root_cause")
        assert hasattr(out, "recommended_action")
        assert hasattr(out, "confidence")

    def test_output_serialisable(self):
        out = analyze_firmware_load_error(FW_LOAD_FAIL_LOG)
        d = out.model_dump()
        assert isinstance(d["firmware_files"], list)


class TestFirmwareNoFailure:
    def test_clean_log(self):
        out = analyze_firmware_load_error(FW_CLEAN_LOG)
        assert out.failure_detected is False

    def test_empty_log(self):
        out = analyze_firmware_load_error("")
        assert out.failure_detected is False

    def test_high_confidence_on_clean(self):
        out = analyze_firmware_load_error(FW_CLEAN_LOG)
        assert out.confidence >= 0.85


class TestFirmwareLoadDetection:
    def setup_method(self):
        self.out = analyze_firmware_load_error(FW_LOAD_FAIL_LOG)

    def test_failure_detected(self):
        assert self.out.failure_detected is True

    def test_firmware_file_extracted(self):
        assert any("firmware-5.bin" in f for f in self.out.firmware_files)

    def test_driver_extracted(self):
        assert len(self.out.drivers) >= 1

    def test_reasonable_confidence(self):
        assert self.out.confidence >= 0.75

    def test_root_cause_not_empty(self):
        assert len(self.out.root_cause) > 10


class TestFirmwareTimeout:
    def setup_method(self):
        self.out = analyze_firmware_load_error(FW_TIMEOUT_LOG)

    def test_failure_detected(self):
        assert self.out.failure_detected is True

    def test_firmware_file_extracted(self):
        assert any("fw.bin" in f for f in self.out.firmware_files)


# ===========================================================================
# analyze_early_oom_killer
# ===========================================================================

class TestOOMSchemas:
    def test_input_schema(self):
        inp = EarlyOOMInput(dmesg_log="test")
        assert inp.dmesg_log == "test"

    def test_output_fields_present(self):
        out = analyze_early_oom_killer(CLEAN_LOG)
        assert isinstance(out, EarlyOOMOutput)
        assert hasattr(out, "oom_detected")
        assert hasattr(out, "victims")
        assert hasattr(out, "root_cause")
        assert hasattr(out, "recommended_action")
        assert hasattr(out, "confidence")

    def test_output_serialisable(self):
        out = analyze_early_oom_killer(OOM_LOG)
        d = out.model_dump()
        assert isinstance(d["victims"], list)


class TestOOMNoEvent:
    def test_clean_log(self):
        out = analyze_early_oom_killer(OOM_CLEAN_LOG)
        assert out.oom_detected is False

    def test_empty_log(self):
        out = analyze_early_oom_killer("")
        assert out.oom_detected is False

    def test_high_confidence_on_clean(self):
        out = analyze_early_oom_killer(OOM_CLEAN_LOG)
        assert out.confidence >= 0.85


class TestOOMDetection:
    def setup_method(self):
        self.out = analyze_early_oom_killer(OOM_LOG)

    def test_oom_detected(self):
        assert self.out.oom_detected is True

    def test_victim_extracted(self):
        assert len(self.out.victims) >= 1

    def test_victim_process_name(self):
        assert any(v["process"] == "cameraserver" for v in self.out.victims)

    def test_victim_pid(self):
        assert any(v["pid"] == 1234 for v in self.out.victims)

    def test_victim_oom_score(self):
        assert any(v.get("oom_score_adj") == 500 for v in self.out.victims)

    def test_reasonable_confidence(self):
        assert self.out.confidence >= 0.80

    def test_root_cause_not_empty(self):
        assert len(self.out.root_cause) > 10


class TestOOMEarlyBoot:
    def test_critical_process_oom(self):
        # zygote (oom_score_adj=0) killed is severe
        out = analyze_early_oom_killer(OOM_EARLY_LOG)
        assert out.oom_detected is True
        assert any(v["process"] == "zygote" for v in out.victims)
