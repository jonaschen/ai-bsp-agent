"""
Isolated pytest for AArch64 Exception Diagnostic Skills.
No LLM is invoked.

ESR_EL1 test values (manually verified against ARM DDI0487):
  0x96000005 — EC=0x25 (Data Abort, current EL), IL=1, WnR=0, DFSC=0x05 (Translation L1)
  0x96000045 — EC=0x25 (Data Abort, current EL), IL=1, WnR=1, DFSC=0x05 (Translation L1)
  0x86000005 — EC=0x21 (Instruction Abort, current EL), IL=1, IFSC=0x05 (Translation L1)
  0xBE000000 — EC=0x2F (SError Interrupt), IL=1, ISS=0
  0x00000000 — EC=0x00 (Unknown reason)
"""
import pytest

from skills.bsp_diagnostics.aarch64_exceptions import (
    CacheCoherencyInput,
    CacheCoherencyOutput,
    ESRELInput,
    ESREL1Output,
    check_cache_coherency_panic,
    decode_esr_el1,
)

# ---------------------------------------------------------------------------
# ESR_EL1 log snippets for cache coherency tests
# ---------------------------------------------------------------------------

SERROR_PANIC_LOG = """\
[  1450.123456] SError Interrupt on CPU 3
[  1450.123460] ESR_EL1 = 0xBE000000
[  1450.123461] FAR_EL1 = 0x0000000000000000
[  1450.123462] Kernel panic - not syncing: Asynchronous SError Interrupt
[  1450.123463] CPU: 3 PID: 1 Comm: swapper/3
"""

ARM64_SERROR_LOG = """\
[  200.000000] arm64: taking pending SError interrupt
[  200.000001] Kernel panic - not syncing: Oops - BUG: failure
"""

CACHE_COHERENCY_LOG = """\
[  300.000000] Bad mode in Error handler detected on CPU 2
[  300.000001] ESR_EL1 = 0xBE000002
[  300.000002] cache coherency failure detected
"""

NORMAL_PANIC_LOG = """\
[  100.000000] Unable to handle kernel NULL pointer dereference
[  100.000001] Mem abort info:
[  100.000002] ESR_EL1 = 0x96000005
[  100.000003] PC is at drm_atomic_helper_commit+0x1c/0x88
"""

CLEAN_LOG = """\
[  1.000000] Linux version 6.1.0
[  1.000001] Booting Linux on physical CPU 0x0000000000 [0x412fd050]
"""


# ===========================================================================
# Tests — decode_esr_el1
# ===========================================================================

class TestDecodeESREL1Fields:
    def test_data_abort_current_el_read(self):
        # 0x96000005: EC=0x25, IL=1, WnR=0, DFSC=0x05 (Translation L1)
        result = decode_esr_el1("0x96000005")
        assert result.ec == 0x25
        assert result.il == 1
        assert result.iss == 0x05
        assert result.is_data_abort is True
        assert result.is_instruction_abort is False
        assert result.is_serror is False

    def test_data_abort_current_el_write(self):
        # 0x96000045: EC=0x25, IL=1, WnR=1 (bit 6 set), DFSC=0x05
        result = decode_esr_el1("0x96000045")
        assert result.ec == 0x25
        assert result.is_data_abort is True
        assert "write" in result.iss_detail.lower()

    def test_data_abort_read_iss_detail_describes_translation_fault(self):
        result = decode_esr_el1("0x96000005")
        assert result.iss_detail is not None
        assert "read" in result.iss_detail.lower()
        assert "Translation fault" in result.iss_detail

    def test_instruction_abort_current_el(self):
        # 0x86000005: EC=0x21 (Instruction Abort current EL), IFSC=0x05
        result = decode_esr_el1("0x86000005")
        assert result.ec == 0x21
        assert result.is_instruction_abort is True
        assert result.is_data_abort is False
        assert result.is_serror is False

    def test_serror_interrupt(self):
        # 0xBE000000: EC=0x2F (SError), IL=1, ISS=0
        result = decode_esr_el1("0xBE000000")
        assert result.ec == 0x2F
        assert result.is_serror is True
        assert result.is_data_abort is False
        assert result.is_instruction_abort is False

    def test_unknown_ec(self):
        # 0x00000000: EC=0x00 (Unknown)
        result = decode_esr_el1("0x00000000")
        assert result.ec == 0x00
        assert "Unknown" in result.ec_description
        assert result.is_data_abort is False
        assert result.is_serror is False

    def test_il_field_32bit_instruction(self):
        result = decode_esr_el1("0x96000005")
        assert result.il == 1
        assert "32-bit" in result.il_description

    def test_raw_hex_preserved_in_output(self):
        result = decode_esr_el1("0x96000005")
        assert result.raw_hex == "0x96000005"
        assert result.raw_value == 0x96000005

    def test_accepts_hex_without_0x_prefix(self):
        result = decode_esr_el1("96000005")
        assert result.ec == 0x25
        assert result.raw_value == 0x96000005


class TestDecodeESREL1Recommendations:
    def test_translation_fault_recommends_null_check(self):
        result = decode_esr_el1("0x96000005")
        assert "NULL" in result.recommended_action or "pointer" in result.recommended_action.lower()

    def test_serror_recommends_cache_coherency_check(self):
        result = decode_esr_el1("0xBE000000")
        assert "cache" in result.recommended_action.lower() or "SError" in result.recommended_action

    def test_instruction_abort_translation_recommends_corruption_check(self):
        result = decode_esr_el1("0x86000005")
        assert "pointer" in result.recommended_action.lower() or "corrupt" in result.recommended_action.lower()


class TestDecodeESREL1Schema:
    def test_output_is_esrel1_output(self):
        assert isinstance(decode_esr_el1("0x96000005"), ESREL1Output)

    def test_pydantic_input_accepts_valid_hex(self):
        inp = ESRELInput(hex_value="0x96000045")
        result = decode_esr_el1(inp.hex_value)
        assert isinstance(result, ESREL1Output)


# ===========================================================================
# Tests — check_cache_coherency_panic
# ===========================================================================

class TestCacheCoherencyDetection:
    def test_serror_interrupt_log_is_detected(self):
        result = check_cache_coherency_panic(SERROR_PANIC_LOG)
        assert result.is_coherency_panic is True

    def test_arm64_serror_message_is_detected(self):
        result = check_cache_coherency_panic(ARM64_SERROR_LOG)
        assert result.is_coherency_panic is True

    def test_cache_coherency_text_plus_bad_mode_is_detected(self):
        result = check_cache_coherency_panic(CACHE_COHERENCY_LOG)
        assert result.is_coherency_panic is True

    def test_clean_log_not_flagged(self):
        result = check_cache_coherency_panic(CLEAN_LOG)
        assert result.is_coherency_panic is False

    def test_normal_null_pointer_panic_not_flagged(self):
        # Normal panic with EC=0x25 (Data Abort), not SError
        result = check_cache_coherency_panic(NORMAL_PANIC_LOG)
        assert result.is_coherency_panic is False


class TestCacheCoherencyESRExtraction:
    def test_extracts_esr_el1_from_log(self):
        result = check_cache_coherency_panic(SERROR_PANIC_LOG)
        assert result.esr_el1_hex == "0xBE000000"

    def test_esr_serror_ec_is_flagged(self):
        result = check_cache_coherency_panic(SERROR_PANIC_LOG)
        assert result.esr_is_serror is True

    def test_esr_non_serror_ec_is_not_flagged(self):
        # 0x96000005 has EC=0x25 (Data Abort), not SError
        result = check_cache_coherency_panic(NORMAL_PANIC_LOG)
        assert result.esr_is_serror is False

    def test_no_esr_in_log_returns_none(self):
        result = check_cache_coherency_panic(ARM64_SERROR_LOG)
        assert result.esr_el1_hex is None


class TestCacheCoherencyIndicators:
    def test_indicators_list_is_populated_for_serror_log(self):
        result = check_cache_coherency_panic(SERROR_PANIC_LOG)
        assert len(result.indicators_found) >= 1
        assert "serror_interrupt" in result.indicators_found

    def test_indicators_list_is_empty_for_clean_log(self):
        result = check_cache_coherency_panic(CLEAN_LOG)
        assert len(result.indicators_found) == 0


class TestCacheCoherencyConfidenceAndRecommendation:
    def test_detected_panic_has_high_confidence(self):
        result = check_cache_coherency_panic(SERROR_PANIC_LOG)
        assert result.confidence >= 0.6

    def test_clean_log_has_low_confidence(self):
        result = check_cache_coherency_panic(CLEAN_LOG)
        assert result.confidence <= 0.2

    def test_detected_panic_recommends_dcache_flush(self):
        result = check_cache_coherency_panic(SERROR_PANIC_LOG)
        assert "flush" in result.recommended_action.lower() or "cache" in result.recommended_action.lower()

    def test_confidence_always_in_valid_range(self):
        for log in [SERROR_PANIC_LOG, ARM64_SERROR_LOG, CACHE_COHERENCY_LOG, NORMAL_PANIC_LOG, CLEAN_LOG, ""]:
            result = check_cache_coherency_panic(log)
            assert 0.0 <= result.confidence <= 1.0


class TestCacheCoherencySchema:
    def test_output_is_cache_coherency_output(self):
        assert isinstance(check_cache_coherency_panic(SERROR_PANIC_LOG), CacheCoherencyOutput)

    def test_pydantic_input_accepts_valid_log(self):
        inp = CacheCoherencyInput(panic_log=SERROR_PANIC_LOG)
        result = check_cache_coherency_panic(inp.panic_log)
        assert isinstance(result, CacheCoherencyOutput)
