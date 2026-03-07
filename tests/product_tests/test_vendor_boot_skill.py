"""
Tests for skills/bsp_diagnostics/vendor_boot.py — check_vendor_boot_ufs_driver.

All tests are deterministic: no LLM calls, no network, no I/O.
"""
import pytest

from skills.bsp_diagnostics.vendor_boot import (
    VendorBootUFSInput,
    VendorBootUFSOutput,
    check_vendor_boot_ufs_driver,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

CLEAN_BOOT_LOG = """\
[    0.123456] init: starting version 1
[    0.234567] ufshcd-hisi ff3c0000.ufs: ufshcd_hba_execute_hce: HCE enable timeout
[    1.000000] ufshcd-hisi ff3c0000.ufs: ufshcd_hba_enable: HCE enable completed
[    1.100000] ufshcd-hisi ff3c0000.ufs: ufshcd_host_power_up: UFS device is ready
[    2.000000] android: start services
"""

UFS_PROBE_FAIL_LOG = """\
[    0.100000] ufshcd-hisi ff3c0000.ufs: ufshcd_probe_hba failed
[    0.101000] ufshcd-hisi ff3c0000.ufs: Initialization failed
[    0.200000] Kernel panic - not syncing: ufshcd probe error -19
"""

UFS_LINK_STARTUP_FAIL_LOG = """\
[    0.500000] PM: Restoring system
[    0.600000] ufshcd-hisi ff3c0000.ufs: ufshcd_link_startup failed -110
[    0.601000] ufshcd-hisi ff3c0000.ufs: UFS link startup failed
[    0.700000] PM: STD restore failed
"""

UFS_RESUME_FAIL_LOG = """\
[    1.000000] PM: Restoring system from disk
[    1.100000] ufshcd-hisi ff3c0000.ufs: ufshcd_host_reset_and_restore failed -110
[    1.101000] ufshcd-hisi ff3c0000.ufs: ufshcd_eh_host_reset_handler failed
[    1.200000] PM: Failed to resume device
"""

UFS_GENERIC_ERROR_LOG = """\
[    0.300000] ufs_qcom 1d84000.ufshc: error -5
[    0.301000] ufs_qcom 1d84000.ufshc: Reset failed, giving up
"""


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestSchemas:
    def test_input_schema_fields(self):
        inp = VendorBootUFSInput(dmesg_log="test log")
        assert inp.dmesg_log == "test log"

    def test_output_fields_present(self):
        out = check_vendor_boot_ufs_driver("no errors here")
        assert isinstance(out, VendorBootUFSOutput)
        assert hasattr(out, "failure_detected")
        assert hasattr(out, "error_lines")
        assert hasattr(out, "failure_phase")
        assert hasattr(out, "root_cause")
        assert hasattr(out, "recommended_action")
        assert hasattr(out, "confidence")

    def test_confidence_in_range(self):
        out = check_vendor_boot_ufs_driver("no errors here")
        assert 0.0 <= out.confidence <= 1.0

    def test_output_is_serialisable(self):
        out = check_vendor_boot_ufs_driver(UFS_PROBE_FAIL_LOG)
        d = out.model_dump()
        assert isinstance(d, dict)
        assert isinstance(d["error_lines"], list)


# ---------------------------------------------------------------------------
# No-failure path
# ---------------------------------------------------------------------------

class TestNoFailure:
    def test_no_failure_detected(self):
        out = check_vendor_boot_ufs_driver("[ 0.1] normal boot sequence")
        assert out.failure_detected is False

    def test_no_error_lines_on_clean_log(self):
        out = check_vendor_boot_ufs_driver("[ 0.1] normal boot sequence")
        assert out.error_lines == []

    def test_failure_phase_none_on_clean_log(self):
        out = check_vendor_boot_ufs_driver("[ 0.1] normal boot sequence")
        assert out.failure_phase is None

    def test_high_confidence_on_clean_log(self):
        out = check_vendor_boot_ufs_driver("[ 0.1] normal boot sequence")
        assert out.confidence >= 0.8


# ---------------------------------------------------------------------------
# Probe failure
# ---------------------------------------------------------------------------

class TestProbeFailure:
    def setup_method(self):
        self.out = check_vendor_boot_ufs_driver(UFS_PROBE_FAIL_LOG)

    def test_failure_detected(self):
        assert self.out.failure_detected is True

    def test_phase_is_probe(self):
        assert self.out.failure_phase == "probe"

    def test_error_lines_not_empty(self):
        assert len(self.out.error_lines) >= 1

    def test_error_lines_contain_probe_text(self):
        assert any("ufshcd_probe_hba" in line for line in self.out.error_lines)

    def test_reasonable_confidence(self):
        assert self.out.confidence >= 0.5


# ---------------------------------------------------------------------------
# Link startup failure
# ---------------------------------------------------------------------------

class TestLinkStartupFailure:
    def setup_method(self):
        self.out = check_vendor_boot_ufs_driver(UFS_LINK_STARTUP_FAIL_LOG)

    def test_failure_detected(self):
        assert self.out.failure_detected is True

    def test_phase_is_link_startup(self):
        assert self.out.failure_phase == "link_startup"

    def test_error_lines_not_empty(self):
        assert len(self.out.error_lines) >= 1

    def test_reasonable_confidence(self):
        assert self.out.confidence >= 0.5


# ---------------------------------------------------------------------------
# Resume failure (STD context → higher confidence)
# ---------------------------------------------------------------------------

class TestResumeFailure:
    def setup_method(self):
        self.out = check_vendor_boot_ufs_driver(UFS_RESUME_FAIL_LOG)

    def test_failure_detected(self):
        assert self.out.failure_detected is True

    def test_phase_is_resume(self):
        assert self.out.failure_phase == "resume"

    def test_higher_confidence_in_std_context(self):
        # Log contains "Restoring" — STD context flag raises confidence
        assert self.out.confidence >= 0.85

    def test_error_lines_contain_reset_restore(self):
        assert any("reset_and_restore" in line or "eh_host_reset" in line
                   for line in self.out.error_lines)


# ---------------------------------------------------------------------------
# Generic UFS error (no specific phase)
# ---------------------------------------------------------------------------

class TestGenericError:
    def setup_method(self):
        self.out = check_vendor_boot_ufs_driver(UFS_GENERIC_ERROR_LOG)

    def test_failure_detected(self):
        assert self.out.failure_detected is True

    def test_has_error_lines(self):
        assert len(self.out.error_lines) >= 1

    def test_confidence_lower_without_phase(self):
        # phase is 'unknown', so confidence should be moderate
        assert self.out.confidence >= 0.3


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_log(self):
        out = check_vendor_boot_ufs_driver("")
        assert out.failure_detected is False
        assert out.error_lines == []

    def test_error_lines_capped_at_20(self):
        # Repeat the error line 30 times
        log = "\n".join(
            f"[{i}.000000] ufshcd-hisi ff3c0000.ufs: ufshcd_link_startup failed"
            for i in range(30)
        )
        out = check_vendor_boot_ufs_driver(log)
        assert len(out.error_lines) <= 20

    def test_non_ufs_error_not_flagged(self):
        log = "[ 0.100] mmc0: error -110 during read\n[ 0.200] ext4: filesystem error"
        out = check_vendor_boot_ufs_driver(log)
        assert out.failure_detected is False

    def test_recommended_action_is_nonempty(self):
        out = check_vendor_boot_ufs_driver(UFS_PROBE_FAIL_LOG)
        assert len(out.recommended_action) > 10
