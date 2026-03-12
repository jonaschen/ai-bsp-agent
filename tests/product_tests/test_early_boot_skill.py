"""
Tests for skills/bsp_diagnostics/early_boot.py

Covers:
  - parse_early_boot_uart_log(): stage detection, error classification,
    last_successful_step, first_error_line, no-failure path, empty input.
  - analyze_lk_panic(): assert detection (with/without file:line),
    DDR failure, image load failure, PMIC failure, generic panic,
    register dump extraction, no-panic path.
"""
import pytest

from skills.bsp_diagnostics.early_boot import (
    EarlyBootUARTOutput,
    LKPanicOutput,
    analyze_lk_panic,
    parse_early_boot_uart_log,
)


# ---------------------------------------------------------------------------
# Fixtures — UART log snippets
# ---------------------------------------------------------------------------

AUTH_FAIL_LOG = """\
NOTICE:  BL1: v2.9(release):v2.9.0
NOTICE:  BL1: Booting BL2 image
NOTICE:  BL2: v2.9(release)
ERROR:   Authentication failed for image id=3
"""

IMAGE_LOAD_LOG = """\
NOTICE:  BL1: v2.9
NOTICE:  BL2: v2.9
NOTICE:  BL2: Loading image id 3
ERROR:   BL2: Failed to load image id 3
"""

DDR_FAIL_LOG = """\
NOTICE:  BL1: v2.9
BL2: DDR init fail - training timeout
ERROR:   DRAM initialisation error
"""

PMIC_FAIL_LOG = """\
NOTICE:  BL1: v2.9
ERROR:   PMIC not respond during early init
VDD not ready
"""

GENERIC_ERROR_LOG = """\
NOTICE:  BL1: v2.9
NOTICE:  BL2: Loading BL31
ERROR:   Unclassified error occurred
"""

CLEAN_BOOT_LOG = """\
NOTICE:  BL1: v2.9(release)
NOTICE:  BL1: Booting BL2 image
NOTICE:  BL2: v2.9(release)
NOTICE:  BL2: Booting BL31
NOTICE:  BL31: v2.9(release)
NOTICE:  BL31: Booting BL33
U-Boot 2023.10 (Jan 01 2024 - 09:00:00 +0000)
DRAM:  4 GiB
"""

LK_ASSERT_LOG = """\
[00000] target_init(
[00000] ASSERT FAILED at [target/msm8996/init.c:247]
r0 = 0x00000000
r1 = 0xdeadbeef
"""

LK_ASSERT_NO_FILE_LOG = """\
ASSERT: NULL pointer dereference in smem_init
"""

LK_DDR_LOG = """\
[00000] ddr_init(
DDR init fail - training timeout error
"""

UBOOT_IMAGE_LOG = """\
U-Boot 2023.10
Loading kernel...
Bad Linux ARM64 Image magic!
"""

LK_PMIC_LOG = """\
[00000] pmic_init(
PMIC fail during LK init
"""

LK_GENERIC_PANIC_LOG = """\
[00000] platform_init(
panic("Unrecoverable error in platform_init")
"""

AARCH64_REG_LOG = """\
[00000] ASSERT FAILED at [lib/debug.c:12]
x0  = 0x0000000000000000
x1  = 0xdeadbeef00000001
sp  = 0xffff800008003f80
elr = 0xffff800008001234
"""

CLEAN_LK_LOG = """\
[00000] platform_init(
[00000] target_init(
DRAM:  4 GiB
Booting Linux...
"""


# ===========================================================================
# parse_early_boot_uart_log tests
# ===========================================================================

class TestParseEarlyBootUARTLog:

    # --- Auth failure ---
    def test_auth_failure_detected(self):
        out = parse_early_boot_uart_log(AUTH_FAIL_LOG)
        assert out.failure_detected is True
        assert out.error_type == "auth_failure"

    def test_auth_failure_of_image_format(self):
        # Real TF-A format: "Authentication of BL31 image failed"
        log = (
            "NOTICE:  BL1: v2.7\n"
            "INFO:    BL2: Verifying image id=5\n"
            "ERROR:   BL2: Failed to load image id=5 (-2)\n"
            "ERROR:   Authentication of BL31 image failed\n"
            "ERROR:   BL2: Failed to boot next image. Aborting.\n"
        )
        out = parse_early_boot_uart_log(log)
        assert out.error_type == "auth_failure"

    def test_auth_failure_confidence(self):
        out = parse_early_boot_uart_log(AUTH_FAIL_LOG)
        assert out.confidence >= 0.90

    def test_auth_failure_first_error_line(self):
        out = parse_early_boot_uart_log(AUTH_FAIL_LOG)
        assert out.first_error_line is not None
        assert "Authentication" in out.first_error_line

    # --- Image load failure ---
    def test_image_load_failure_detected(self):
        out = parse_early_boot_uart_log(IMAGE_LOAD_LOG)
        assert out.failure_detected is True
        assert out.error_type == "image_load_failure"

    def test_image_load_confidence(self):
        out = parse_early_boot_uart_log(IMAGE_LOAD_LOG)
        assert out.confidence >= 0.85

    # --- DDR init failure ---
    def test_ddr_failure_detected(self):
        out = parse_early_boot_uart_log(DDR_FAIL_LOG)
        assert out.failure_detected is True
        assert out.error_type == "ddr_init_failure"

    def test_ddr_failure_confidence(self):
        out = parse_early_boot_uart_log(DDR_FAIL_LOG)
        assert out.confidence >= 0.88

    # --- PMIC failure ---
    def test_pmic_failure_detected(self):
        out = parse_early_boot_uart_log(PMIC_FAIL_LOG)
        assert out.failure_detected is True
        assert out.error_type == "pmic_failure"

    def test_pmic_regulator_not_ready_format(self):
        # Real TF-A format: "PMIC: regulator not ready"
        log = (
            "NOTICE:  BL1: v2.7\n"
            "INFO:    BL31: Initializing power domains\n"
            "ERROR:   BL31: PMIC: regulator not ready\n"
            "ERROR:   BL31: Failed to enable vdd_gpu rail, status=-1\n"
        )
        out = parse_early_boot_uart_log(log)
        assert out.error_type == "pmic_failure"
        assert out.confidence >= 0.75

    # --- Generic error ---
    def test_generic_error_detected(self):
        out = parse_early_boot_uart_log(GENERIC_ERROR_LOG)
        assert out.failure_detected is True
        assert out.error_type == "generic_error"

    def test_generic_error_lower_confidence(self):
        out = parse_early_boot_uart_log(GENERIC_ERROR_LOG)
        assert out.confidence < 0.70

    # --- Stage detection ---
    def test_bl2_stage_detected(self):
        out = parse_early_boot_uart_log(AUTH_FAIL_LOG)
        # BL2 is latest stage in this log
        assert out.detected_bl_stage == "BL2"

    def test_clean_log_latest_stage_uboot(self):
        out = parse_early_boot_uart_log(CLEAN_BOOT_LOG)
        assert out.detected_bl_stage == "U-Boot"

    # --- Last successful step ---
    def test_last_handoff_bl1_to_bl2(self):
        out = parse_early_boot_uart_log(AUTH_FAIL_LOG)
        assert out.last_successful_step is not None
        assert "BL1" in out.last_successful_step or "BL2" in out.last_successful_step

    def test_last_handoff_bl31_to_bl33(self):
        out = parse_early_boot_uart_log(CLEAN_BOOT_LOG)
        assert out.last_successful_step is not None

    # --- No failure ---
    def test_clean_log_no_failure(self):
        out = parse_early_boot_uart_log(CLEAN_BOOT_LOG)
        assert out.failure_detected is False
        assert out.error_type == "none"

    def test_clean_log_no_first_error(self):
        out = parse_early_boot_uart_log(CLEAN_BOOT_LOG)
        assert out.first_error_line is None

    # --- Empty log ---
    def test_empty_log_returns_no_failure(self):
        out = parse_early_boot_uart_log("")
        assert out.failure_detected is False
        assert out.error_type == "none"

    def test_empty_log_root_cause_message(self):
        out = parse_early_boot_uart_log("")
        assert "Empty" in out.root_cause

    # --- Output schema ---
    def test_returns_correct_type(self):
        out = parse_early_boot_uart_log(AUTH_FAIL_LOG)
        assert isinstance(out, EarlyBootUARTOutput)

    def test_confidence_in_range(self):
        for log in [AUTH_FAIL_LOG, IMAGE_LOAD_LOG, DDR_FAIL_LOG, CLEAN_BOOT_LOG]:
            out = parse_early_boot_uart_log(log)
            assert 0.0 <= out.confidence <= 1.0


# ===========================================================================
# analyze_lk_panic tests
# ===========================================================================

class TestAnalyzeLKPanic:

    # --- Assert with file:line ---
    def test_assert_detected(self):
        out = analyze_lk_panic(LK_ASSERT_LOG)
        assert out.panic_detected is True
        assert out.panic_type == "assert"

    def test_assert_file_extracted(self):
        out = analyze_lk_panic(LK_ASSERT_LOG)
        assert out.assert_file == "target/msm8996/init.c"

    def test_assert_line_extracted(self):
        out = analyze_lk_panic(LK_ASSERT_LOG)
        assert out.assert_line == 247

    def test_assert_confidence_high(self):
        out = analyze_lk_panic(LK_ASSERT_LOG)
        assert out.confidence >= 0.80

    # --- Assert without file:line ---
    def test_assert_no_file_detected(self):
        out = analyze_lk_panic(LK_ASSERT_NO_FILE_LOG)
        assert out.panic_detected is True
        assert out.panic_type == "assert"

    def test_assert_no_file_fields_none(self):
        out = analyze_lk_panic(LK_ASSERT_NO_FILE_LOG)
        assert out.assert_file is None
        assert out.assert_line is None

    # --- DDR failure ---
    def test_ddr_failure_detected(self):
        out = analyze_lk_panic(LK_DDR_LOG)
        assert out.panic_detected is True
        assert out.panic_type == "ddr_failure"

    def test_ddr_confidence(self):
        out = analyze_lk_panic(LK_DDR_LOG)
        assert out.confidence >= 0.85

    # --- U-Boot image load failure ---
    def test_image_load_detected(self):
        out = analyze_lk_panic(UBOOT_IMAGE_LOG)
        assert out.panic_detected is True
        assert out.panic_type == "image_load"

    def test_image_load_confidence(self):
        out = analyze_lk_panic(UBOOT_IMAGE_LOG)
        assert out.confidence >= 0.88

    # --- PMIC failure ---
    def test_pmic_failure_detected(self):
        out = analyze_lk_panic(LK_PMIC_LOG)
        assert out.panic_detected is True
        assert out.panic_type == "pmic_failure"

    # --- Generic panic ---
    def test_generic_panic_detected(self):
        out = analyze_lk_panic(LK_GENERIC_PANIC_LOG)
        assert out.panic_detected is True
        assert out.panic_type == "generic"

    def test_generic_panic_lower_confidence(self):
        out = analyze_lk_panic(LK_GENERIC_PANIC_LOG)
        assert out.confidence < 0.70

    # --- Register dump extraction ---
    def test_arm32_register_dump_extracted(self):
        out = analyze_lk_panic(LK_ASSERT_LOG)
        assert len(out.register_dump) >= 1
        assert any("r0" in line or "r1" in line for line in out.register_dump)

    def test_aarch64_register_dump_extracted(self):
        out = analyze_lk_panic(AARCH64_REG_LOG)
        assert len(out.register_dump) >= 1
        assert any("x0" in line or "elr" in line or "sp" in line for line in out.register_dump)

    def test_lk_aarch64_space_delimited_registers(self):
        # LK AArch64 panic: registers with spaces (no = or :), multiple per line
        log = (
            "data fault: Write access from PC 0xffff00000011cff0, FAR 0x1, iss 0x44\n"
            "ESR 0x96000044: ec 0x25, il 0x2000000, iss 0x44\n"
            "iframe 0xffff000000496b50:\n"
            "x0  0xffff000000160000 x1  0x               1 x2  0xffff00000011cfe0 x3  0x               1\n"
            "x4  0x              63 x5  0x        696f6820 x6  0xffff000000497960 x7  0x               0\n"
            "x29 0xffff000000496c60 lr  0xffff00000013abe0 usp 0x               0\n"
            "elr 0xffff00000011cff0\n"
            "spsr 0x        60000305\n"
            "panic (caller 0xffff000000102870): die\n"
        )
        out = analyze_lk_panic(log)
        assert out.panic_detected is True
        assert len(out.register_dump) >= 4

    def test_register_dump_capped_at_20(self):
        # Generate a log with 30 register lines
        regs = "\n".join([f"x{i} = 0x{'0' * 16}" for i in range(30)])
        log = f"ASSERT FAILED at [lib/test.c:1]\n{regs}\n"
        out = analyze_lk_panic(log)
        assert len(out.register_dump) <= 20

    # --- No panic ---
    def test_clean_log_no_panic(self):
        out = analyze_lk_panic(CLEAN_LK_LOG)
        assert out.panic_detected is False
        assert out.panic_type == "none"

    def test_clean_log_empty_register_dump(self):
        out = analyze_lk_panic(CLEAN_LK_LOG)
        assert out.register_dump == []

    # --- Output schema ---
    def test_returns_correct_type(self):
        out = analyze_lk_panic(LK_ASSERT_LOG)
        assert isinstance(out, LKPanicOutput)

    def test_confidence_in_range(self):
        for log in [LK_ASSERT_LOG, LK_DDR_LOG, UBOOT_IMAGE_LOG, CLEAN_LK_LOG]:
            out = analyze_lk_panic(log)
            assert 0.0 <= out.confidence <= 1.0

    def test_register_dump_is_list(self):
        out = analyze_lk_panic(LK_ASSERT_LOG)
        assert isinstance(out.register_dump, list)
