"""
Isolated pytest for the STD Hibernation Diagnostic Skill.

These tests exercise the pure Python skill function ONLY.
No LLM is invoked.
"""
import pytest
from skills.bsp_diagnostics.std_hibernation import (
    analyze_std_hibernation_error,
    STDHibernationInput,
    STDHibernationOutput,
    SUNRECLAIM_THRESHOLD_RATIO,
)

# ---------------------------------------------------------------------------
# Fixtures — inline log snippets (no file I/O required)
# ---------------------------------------------------------------------------

DMESG_WITH_ERROR = """\
[  100.000000] PM: Syncing filesystems ... done.
[  100.123456] PM: Creating hibernation image:
[  100.234567] Error -12 creating hibernation image
[  100.345678] PM: Image saving failed, cleaning up.
"""

DMESG_NO_ERROR = """\
[  100.000000] PM: Syncing filesystems ... done.
[  100.123456] PM: Creating hibernation image:
[  100.234567] PM: Wrote 102400 kbytes in 1.20 seconds (85333.33 kbytes/s).
[  100.345678] PM: S|resume|0|0|0|0|0
"""

# MemTotal = 2 GB, SUnreclaim = 300 MB (≈14.6% → exceeds 10%)
MEMINFO_HIGH_SUNRECLAIM = """\
MemTotal:        2097152 kB
MemFree:          512000 kB
MemAvailable:     768000 kB
Buffers:           32000 kB
Cached:           400000 kB
SwapCached:            0 kB
Slab:             450000 kB
SReclaimable:     143848 kB
SUnreclaim:       307200 kB
SwapTotal:       2097152 kB
SwapFree:        1500000 kB
"""

# SUnreclaim = 100 MB (≈4.8% → within threshold)
MEMINFO_LOW_SUNRECLAIM_NO_SWAP = """\
MemTotal:        2097152 kB
MemFree:          512000 kB
MemAvailable:     768000 kB
Buffers:           32000 kB
Cached:           400000 kB
SwapCached:            0 kB
Slab:             250000 kB
SReclaimable:     148576 kB
SUnreclaim:       101376 kB
SwapTotal:       2097152 kB
SwapFree:              0 kB
"""

# SUnreclaim = 100 MB, swap is healthy — unknown root cause
MEMINFO_LOW_SUNRECLAIM_GOOD_SWAP = """\
MemTotal:        2097152 kB
MemFree:          512000 kB
MemAvailable:     768000 kB
Buffers:           32000 kB
Cached:           400000 kB
SwapCached:            0 kB
Slab:             250000 kB
SReclaimable:     148576 kB
SUnreclaim:       101376 kB
SwapTotal:       2097152 kB
SwapFree:        1800000 kB
"""

MEMINFO_EMPTY = ""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestNoError:
    def test_no_hibernation_error_returns_clean_result(self):
        result = analyze_std_hibernation_error(DMESG_NO_ERROR, MEMINFO_HIGH_SUNRECLAIM)

        assert isinstance(result, STDHibernationOutput)
        assert result.error_detected is False
        assert result.root_cause == "No hibernation error detected in dmesg."
        assert result.recommended_action == "No action required."
        assert result.confidence == 1.0

    def test_no_error_still_parses_meminfo(self):
        result = analyze_std_hibernation_error(DMESG_NO_ERROR, MEMINFO_HIGH_SUNRECLAIM)

        assert result.mem_total_kb == 2097152
        assert result.sunreclaim_kb == 307200
        assert result.swap_free_kb == 1500000


class TestHighSUnreclaim:
    def test_error_with_high_sunreclaim_identifies_root_cause(self):
        result = analyze_std_hibernation_error(DMESG_WITH_ERROR, MEMINFO_HIGH_SUNRECLAIM)

        assert result.error_detected is True
        assert result.sunreclaim_exceeds_threshold is True
        assert "SUnreclaim" in result.root_cause
        assert result.recommended_action == "echo 3 > /proc/sys/vm/drop_caches"
        assert result.confidence >= 0.9

    def test_sunreclaim_ratio_calculated_correctly(self):
        result = analyze_std_hibernation_error(DMESG_WITH_ERROR, MEMINFO_HIGH_SUNRECLAIM)

        expected_ratio = 307200 / 2097152
        assert result.sunreclaim_ratio == pytest.approx(expected_ratio, rel=1e-6)
        assert result.sunreclaim_ratio > SUNRECLAIM_THRESHOLD_RATIO

    def test_meminfo_fields_parsed(self):
        result = analyze_std_hibernation_error(DMESG_WITH_ERROR, MEMINFO_HIGH_SUNRECLAIM)

        assert result.mem_total_kb == 2097152
        assert result.sunreclaim_kb == 307200
        assert result.swap_free_kb == 1500000


class TestNoSwap:
    def test_error_with_no_swap_identifies_swap_root_cause(self):
        result = analyze_std_hibernation_error(DMESG_WITH_ERROR, MEMINFO_LOW_SUNRECLAIM_NO_SWAP)

        assert result.error_detected is True
        assert result.sunreclaim_exceeds_threshold is False
        assert result.swap_free_kb == 0
        assert "swap" in result.root_cause.lower()
        assert "swap" in result.recommended_action.lower()
        assert result.confidence >= 0.8

    def test_sunreclaim_below_threshold_for_no_swap_case(self):
        result = analyze_std_hibernation_error(DMESG_WITH_ERROR, MEMINFO_LOW_SUNRECLAIM_NO_SWAP)

        assert result.sunreclaim_ratio < SUNRECLAIM_THRESHOLD_RATIO


class TestUnknownCause:
    def test_error_with_no_clear_cause_returns_low_confidence(self):
        result = analyze_std_hibernation_error(DMESG_WITH_ERROR, MEMINFO_LOW_SUNRECLAIM_GOOD_SWAP)

        assert result.error_detected is True
        assert result.sunreclaim_exceeds_threshold is False
        assert result.swap_free_kb == 1800000
        assert result.confidence < 0.5

    def test_unknown_cause_recommends_further_investigation(self):
        result = analyze_std_hibernation_error(DMESG_WITH_ERROR, MEMINFO_LOW_SUNRECLAIM_GOOD_SWAP)

        assert "fragmentation" in result.recommended_action.lower() or \
               "meminfo" in result.recommended_action.lower()


class TestEdgeCases:
    def test_empty_dmesg_no_error(self):
        result = analyze_std_hibernation_error("", MEMINFO_HIGH_SUNRECLAIM)

        assert result.error_detected is False

    def test_empty_meminfo_fields_are_none(self):
        result = analyze_std_hibernation_error(DMESG_WITH_ERROR, MEMINFO_EMPTY)

        assert result.mem_total_kb is None
        assert result.sunreclaim_kb is None
        assert result.swap_free_kb is None
        assert result.sunreclaim_ratio is None
        assert result.sunreclaim_exceeds_threshold is False

    def test_empty_meminfo_still_detects_error(self):
        result = analyze_std_hibernation_error(DMESG_WITH_ERROR, MEMINFO_EMPTY)

        assert result.error_detected is True

    def test_pydantic_input_schema_accepts_valid_input(self):
        inp = STDHibernationInput(dmesg_log=DMESG_WITH_ERROR, meminfo_log=MEMINFO_HIGH_SUNRECLAIM)
        result = analyze_std_hibernation_error(inp.dmesg_log, inp.meminfo_log)

        assert isinstance(result, STDHibernationOutput)

    def test_output_confidence_always_in_valid_range(self):
        cases = [
            (DMESG_NO_ERROR, MEMINFO_HIGH_SUNRECLAIM),
            (DMESG_WITH_ERROR, MEMINFO_HIGH_SUNRECLAIM),
            (DMESG_WITH_ERROR, MEMINFO_LOW_SUNRECLAIM_NO_SWAP),
            (DMESG_WITH_ERROR, MEMINFO_LOW_SUNRECLAIM_GOOD_SWAP),
            (DMESG_WITH_ERROR, MEMINFO_EMPTY),
        ]
        for dmesg, meminfo in cases:
            result = analyze_std_hibernation_error(dmesg, meminfo)
            assert 0.0 <= result.confidence <= 1.0
