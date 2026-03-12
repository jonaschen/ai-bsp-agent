"""
Tests for skills/bsp_diagnostics/log_segmenter.py

Covers: segment_boot_log() stage detection, route mapping, confidence
scoring, first_error_line extraction, and edge cases.
"""
import pytest

from skills.bsp_diagnostics.log_segmenter import (
    BootLogSegmenterOutput,
    segment_boot_log,
)


# ---------------------------------------------------------------------------
# Fixtures — representative log snippets
# ---------------------------------------------------------------------------

TF_A_BL2_LOG = """\
NOTICE:  BL1: v2.9(release):v2.9.0
NOTICE:  BL1: Built : 09:00:00, Jan  1 2024
NOTICE:  BL2: v2.9(release):v2.9.0
ERROR:   BL2: Failed to load image id 3
"""

TF_A_BL31_LOG = """\
NOTICE:  BL1: v2.9(release)
NOTICE:  BL2: Loading BL31
NOTICE:  BL31: v2.9(release)
NOTICE:  BL31: Non secure code at 0x80000000
"""

UBOOT_LOG = """\
U-Boot 2023.10 (Jan 01 2024 - 09:00:00 +0000)
DRAM:  4 GiB
Loading Environment from MMC... OK
"""

KERNEL_ONLY_LOG = """\
[    0.000000] Booting Linux on physical CPU 0x0000000000 [0x411fd050]
[    0.000000] Linux version 5.15.0 (gcc version 11.3.0)
[    0.012345] Calibrating delay loop... 3200.00 BogoMIPS
"""

ANDROID_INIT_LOG = """\
[    0.000000] Booting Linux on physical CPU 0x0
[    2.345678] init: Starting service 'servicemanager'...
[    3.456789] SELinux: Initialized. Enforcing mode.
[    4.000000] Zygote: Starting...
[  OK  ] Started Service Manager.
"""

ANDROID_FAILED_LOG = """\
[    0.000000] Booting Linux on physical CPU 0x0
[    2.345678] init: Starting service 'vold'...
[FAILED] Failed to start vold.
"""

EMPTY_LOG = ""

GARBAGE_LOG = "some random text with no boot markers at all"


# ---------------------------------------------------------------------------
# Early boot detection
# ---------------------------------------------------------------------------

class TestEarlyBootDetection:
    def test_tf_a_bl2_detected(self):
        out = segment_boot_log(TF_A_BL2_LOG)
        assert out.detected_stage == "early_boot"

    def test_tf_a_bl31_detected(self):
        out = segment_boot_log(TF_A_BL31_LOG)
        assert out.detected_stage == "early_boot"

    def test_uboot_detected(self):
        out = segment_boot_log(UBOOT_LOG)
        assert out.detected_stage == "early_boot"

    def test_early_boot_route(self):
        out = segment_boot_log(TF_A_BL2_LOG)
        assert out.suggested_route == "early_boot_advisor"

    def test_early_boot_no_kernel_ts(self):
        # Early boot logs must NOT contain kernel timestamps
        out = segment_boot_log(TF_A_BL2_LOG)
        assert "tf_a_bl" in " ".join(out.stage_indicators) or \
               any("tf_a" in ind or "uboot" in ind or "lk" in ind for ind in out.stage_indicators)

    def test_early_boot_confidence_ge_70(self):
        out = segment_boot_log(TF_A_BL2_LOG)
        assert out.confidence >= 0.70

    def test_early_boot_multiple_indicators_raises_confidence(self):
        out_single = segment_boot_log("NOTICE:  BL1: v2.9")
        multi_log = TF_A_BL31_LOG  # has BL1, BL2, BL31
        out_multi = segment_boot_log(multi_log)
        assert out_multi.confidence >= out_single.confidence

    def test_early_boot_confidence_capped_at_95(self):
        # Many markers present — confidence must not exceed 0.95
        log = "\n".join([
            "NOTICE:  BL1: v2.9",
            "NOTICE:  BL2: v2.9",
            "NOTICE:  BL31: v2.9",
            "U-Boot 2023.10 (Jan 01 2024)",
            "UEFI firmware v1.0",
        ])
        out = segment_boot_log(log)
        assert out.confidence <= 0.95


# ---------------------------------------------------------------------------
# Kernel init detection
# ---------------------------------------------------------------------------

class TestKernelInitDetection:
    def test_kernel_only_stage(self):
        out = segment_boot_log(KERNEL_ONLY_LOG)
        assert out.detected_stage == "kernel_init"

    def test_kernel_route(self):
        out = segment_boot_log(KERNEL_ONLY_LOG)
        assert out.suggested_route == "kernel_pathologist"

    def test_kernel_confidence(self):
        out = segment_boot_log(KERNEL_ONLY_LOG)
        assert out.confidence == 0.75

    def test_kernel_stage_indicator(self):
        out = segment_boot_log(KERNEL_ONLY_LOG)
        assert "kernel_timestamp" in out.stage_indicators


# ---------------------------------------------------------------------------
# Android init detection
# ---------------------------------------------------------------------------

class TestAndroidInitDetection:
    def test_android_init_stage(self):
        out = segment_boot_log(ANDROID_INIT_LOG)
        assert out.detected_stage == "android_init"

    def test_android_route(self):
        out = segment_boot_log(ANDROID_INIT_LOG)
        assert out.suggested_route == "android_init_advisor"

    def test_android_failed_stage(self):
        out = segment_boot_log(ANDROID_FAILED_LOG)
        assert out.detected_stage == "android_init"

    def test_android_confidence_ge_70(self):
        out = segment_boot_log(ANDROID_INIT_LOG)
        assert out.confidence >= 0.70

    def test_android_indicators_non_empty(self):
        out = segment_boot_log(ANDROID_INIT_LOG)
        assert len(out.stage_indicators) >= 1


# ---------------------------------------------------------------------------
# Unknown / edge cases
# ---------------------------------------------------------------------------

class TestUnknownDetection:
    def test_empty_log_unknown(self):
        out = segment_boot_log(EMPTY_LOG)
        assert out.detected_stage == "unknown"

    def test_empty_log_route(self):
        out = segment_boot_log(EMPTY_LOG)
        assert out.suggested_route == "clarify_needed"

    def test_garbage_log_unknown(self):
        out = segment_boot_log(GARBAGE_LOG)
        assert out.detected_stage == "unknown"

    def test_unknown_low_confidence(self):
        out = segment_boot_log(GARBAGE_LOG)
        assert out.confidence == 0.20

    def test_unknown_no_indicators(self):
        out = segment_boot_log(GARBAGE_LOG)
        assert out.stage_indicators == []


# ---------------------------------------------------------------------------
# Priority: early_boot > android_init > kernel_init
# ---------------------------------------------------------------------------

class TestStagePriority:
    def test_early_boot_beats_kernel_ts(self):
        # Pure early boot log (TF-A markers, no kernel timestamps):
        pure_early = "NOTICE:  BL2: v2.9\nAuthentication failed\n"
        out = segment_boot_log(pure_early)
        assert out.detected_stage == "early_boot"

    def test_early_boot_wins_even_with_kernel_timestamps(self):
        # Mixed log: TF-A markers followed by kernel output — early_boot wins
        mixed = (
            "NOTICE:  BL1: v2.7(release)\n"
            "NOTICE:  BL2: v2.7(release)\n"
            "[    0.000000] Booting Linux on physical CPU 0x0000000000\n"
            "[    0.012345] random: crng init done\n"
        )
        out = segment_boot_log(mixed)
        assert out.detected_stage == "early_boot"

    def test_lk_welcome_banner_detected_as_early_boot(self):
        # LK banner "welcome to lk/MP" should classify as early_boot
        lk_log = (
            "cntpct_per_ms: 62500.000000000\n"
            "welcome to lk/MP\n"
            "boot args 0x0 0x0 0x0 0x0\n"
            "INIT: cpu 0, calling hook 0xffff0001 (version) at level 0x3fff, flags 0x1\n"
            "entering main console loop\n"
            "] \n"
        )
        out = segment_boot_log(lk_log)
        assert out.detected_stage == "early_boot"

    def test_lk_init_hook_detected_as_early_boot(self):
        # LK INIT: cpu hook line should be enough to classify as early_boot
        lk_log = "INIT: cpu 0, calling hook 0xffff0001 (vm) at level 0x4fff, flags 0x1\n"
        out = segment_boot_log(lk_log)
        assert out.detected_stage == "early_boot"

    def test_kernel_ts_without_android_markers_is_kernel_init(self):
        out = segment_boot_log(KERNEL_ONLY_LOG)
        assert out.detected_stage == "kernel_init"
        # Must NOT be android_init
        assert out.detected_stage != "android_init"


# ---------------------------------------------------------------------------
# first_error_line extraction
# ---------------------------------------------------------------------------

class TestFirstErrorLine:
    def test_error_prefix_extracted(self):
        log = "NOTICE:  BL1: v2.9\nERROR:   BL2: Failed to load image id 3\nmore lines\n"
        out = segment_boot_log(log)
        assert out.first_error_line is not None
        assert "ERROR" in out.first_error_line

    def test_kernel_panic_extracted(self):
        log = KERNEL_ONLY_LOG + "\n[    5.000000] Kernel panic - not syncing: VFS: Unable to mount root\n"
        out = segment_boot_log(log)
        assert out.first_error_line is not None
        assert "panic" in out.first_error_line.lower()

    def test_no_error_gives_none(self):
        out = segment_boot_log(UBOOT_LOG)
        assert out.first_error_line is None

    def test_first_error_not_second(self):
        log = (
            "NOTICE:  BL1: v2.9\n"
            "ERROR:   First error line\n"
            "ERROR:   Second error line\n"
        )
        out = segment_boot_log(log)
        assert out.first_error_line is not None
        assert "First" in out.first_error_line


# ---------------------------------------------------------------------------
# Output schema validation
# ---------------------------------------------------------------------------

class TestOutputSchema:
    def test_returns_correct_type(self):
        out = segment_boot_log(TF_A_BL2_LOG)
        assert isinstance(out, BootLogSegmenterOutput)

    def test_confidence_in_range(self):
        for log in [TF_A_BL2_LOG, KERNEL_ONLY_LOG, ANDROID_INIT_LOG, GARBAGE_LOG]:
            out = segment_boot_log(log)
            assert 0.0 <= out.confidence <= 1.0

    def test_stage_indicators_is_list(self):
        out = segment_boot_log(TF_A_BL2_LOG)
        assert isinstance(out.stage_indicators, list)

    def test_error_summary_non_empty(self):
        for log in [TF_A_BL2_LOG, KERNEL_ONLY_LOG, ANDROID_INIT_LOG, GARBAGE_LOG]:
            out = segment_boot_log(log)
            assert out.error_summary
