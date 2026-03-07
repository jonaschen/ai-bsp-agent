"""
AArch64 Exception Diagnostic Skills.

Provides two deterministic tools for the Kernel Pathologist domain:
  - decode_esr_el1: decode AArch64 ESR_EL1 exception syndrome register
  - check_cache_coherency_panic: detect PoC cache coherency failures in panic logs

Domain: Android BSP / AArch64 Architecture & Exceptions
Reference: ARM Architecture Reference Manual (ARMv8-A), DDI0487
"""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Exception Class (EC) table — ESR_EL1 bits [31:26]
# ---------------------------------------------------------------------------

_EC_TABLE: dict[int, str] = {
    0x00: "Unknown reason",
    0x01: "Trapped WFI/WFE instruction",
    0x03: "Trapped MCR/MRC access (coproc=0b1111)",
    0x04: "Trapped MCRR/MRRC access (coproc=0b1111)",
    0x05: "Trapped MCR/MRC access (coproc=0b1110)",
    0x06: "Trapped LDC/STC access",
    0x07: "Trapped FP/SIMD/SVE (AArch32)",
    0x0C: "Trapped MRRC access (coproc=0b1110)",
    0x0D: "Branch Target Exception",
    0x0E: "Illegal Execution state",
    0x11: "SVC instruction (AArch32)",
    0x15: "SVC instruction (AArch64)",
    0x18: "Trapped MSR/MRS/System instruction",
    0x19: "Trapped SVE access",
    0x20: "Instruction Abort from lower EL",
    0x21: "Instruction Abort from current EL",
    0x22: "PC alignment fault",
    0x24: "Data Abort from lower EL",
    0x25: "Data Abort from current EL",
    0x26: "SP alignment fault",
    0x28: "Trapped FP exception (AArch32)",
    0x2C: "Trapped FP exception (AArch64)",
    0x2F: "SError Interrupt",
    0x30: "Breakpoint exception from lower EL",
    0x31: "Breakpoint exception from current EL",
    0x32: "Software Step exception from lower EL",
    0x33: "Software Step exception from current EL",
    0x34: "Watchpoint exception from lower EL",
    0x35: "Watchpoint exception from current EL",
    0x38: "BKPT instruction (AArch32)",
    0x3C: "BRK instruction (AArch64)",
}

# Data/Instruction Fault Status Code (DFSC/IFSC) — ISS bits [5:0]
_DFSC_TABLE: dict[int, str] = {
    0x00: "Address size fault, level 0 (TTB)",
    0x01: "Address size fault, level 1",
    0x02: "Address size fault, level 2",
    0x03: "Address size fault, level 3",
    0x04: "Translation fault, level 0",
    0x05: "Translation fault, level 1",
    0x06: "Translation fault, level 2",
    0x07: "Translation fault, level 3",
    0x09: "Access flag fault, level 1",
    0x0A: "Access flag fault, level 2",
    0x0B: "Access flag fault, level 3",
    0x0D: "Permission fault, level 1",
    0x0E: "Permission fault, level 2",
    0x0F: "Permission fault, level 3",
    0x10: "Synchronous External abort (non-table walk)",
    0x11: "Synchronous Tag Check Fault",
    0x14: "Synchronous External abort (table walk, level 1)",
    0x15: "Synchronous External abort (table walk, level 2)",
    0x16: "Synchronous External abort (table walk, level 3)",
    0x18: "Synchronous parity/ECC error (non-table walk)",
    0x1C: "Synchronous parity/ECC error (table walk, level 1)",
    0x1D: "Synchronous parity/ECC error (table walk, level 2)",
    0x1E: "Synchronous parity/ECC error (table walk, level 3)",
    0x21: "Alignment fault",
    0x30: "TLB conflict abort",
    0x31: "Unsupported atomic hardware update fault",
}

_TRANSLATION_FAULT_DFSC = {0x04, 0x05, 0x06, 0x07}
_PERMISSION_FAULT_DFSC = {0x0D, 0x0E, 0x0F}
_ECC_FAULT_DFSC = {0x10, 0x18, 0x1C, 0x1D, 0x1E}

# ---------------------------------------------------------------------------
# Skill 3: decode_esr_el1
# ---------------------------------------------------------------------------

class ESRELInput(BaseModel):
    hex_value: str = Field(
        ...,
        description="ESR_EL1 register value as hex string (e.g. '0x96000045' or '96000045')",
        examples=["0x96000045", "0xBE000000"],
    )


class ESREL1Output(BaseModel):
    raw_hex: str = Field(..., description="Original hex string as supplied")
    raw_value: int = Field(..., description="Parsed integer value of ESR_EL1")
    ec: int = Field(..., description="Exception Class field (bits [31:26])")
    ec_description: str = Field(..., description="Human-readable EC description")
    il: int = Field(..., description="Instruction Length bit (bit [25]): 1=32-bit, 0=16-bit")
    il_description: str = Field(..., description="Human-readable IL description")
    iss: int = Field(..., description="Instruction Specific Syndrome (bits [24:0])")
    iss_detail: Optional[str] = Field(None, description="Decoded ISS fields where applicable")
    is_data_abort: bool = Field(..., description="True if EC indicates a Data Abort (0x24 or 0x25)")
    is_instruction_abort: bool = Field(..., description="True if EC indicates an Instruction Abort (0x20 or 0x21)")
    is_serror: bool = Field(..., description="True if EC indicates an SError Interrupt (0x2F)")
    recommended_action: str = Field(..., description="Recommended next debugging step")


def decode_esr_el1(hex_value: str) -> ESREL1Output:
    """
    Decode an AArch64 ESR_EL1 (Exception Syndrome Register) value.

    Extracts EC (Exception Class), IL (Instruction Length), and ISS
    (Instruction Specific Syndrome) and maps them to human-readable descriptions.

    Args:
        hex_value: ESR_EL1 as a hex string ('0x96000045' or '96000045').

    Returns:
        ESREL1Output with all decoded fields and a recommended action.
    """
    raw = hex_value.strip()
    value = int(raw, 16)

    ec = (value >> 26) & 0x3F
    il = (value >> 25) & 0x1
    iss = value & 0x1FFFFFF

    ec_description = _EC_TABLE.get(ec, f"Reserved/Unknown (0x{ec:02X})")
    il_description = "32-bit instruction" if il else "16-bit (Thumb/compressed) instruction"

    is_data_abort = ec in (0x24, 0x25)
    is_instruction_abort = ec in (0x20, 0x21)
    is_serror = ec == 0x2F

    iss_detail: Optional[str] = None
    recommended_action = "Collect full register dump and stack backtrace for further analysis."

    if is_data_abort:
        wnr = (iss >> 6) & 0x1
        dfsc = iss & 0x3F
        dfsc_desc = _DFSC_TABLE.get(dfsc, f"Unknown DFSC (0x{dfsc:02X})")
        access = "write" if wnr else "read"
        iss_detail = f"Data Abort ({access}) — DFSC: {dfsc_desc}"

        if dfsc in _TRANSLATION_FAULT_DFSC:
            recommended_action = (
                "Translation fault likely caused by a NULL or unmapped pointer dereference. "
                "Add NULL checks around the faulting pc address shown in the panic log."
            )
        elif dfsc in _PERMISSION_FAULT_DFSC:
            recommended_action = (
                "Permission fault: the page table does not grant the required access. "
                "Verify memory mappings and page table permissions at the faulting address."
            )
        elif dfsc in _ECC_FAULT_DFSC:
            recommended_action = (
                "External/ECC fault during memory access. "
                "Check for hardware memory errors (DRAM ECC logs, PMIC rails)."
            )

    elif is_instruction_abort:
        ifsc = iss & 0x3F
        ifsc_desc = _DFSC_TABLE.get(ifsc, f"Unknown IFSC (0x{ifsc:02X})")
        iss_detail = f"Instruction Abort — IFSC: {ifsc_desc}"
        if ifsc in _TRANSLATION_FAULT_DFSC:
            recommended_action = (
                "Instruction fetch from an unmapped or invalid address. "
                "Check for stack/heap corruption that may have overwritten a function pointer."
            )

    elif is_serror:
        iss_detail = "SError Interrupt — may indicate cache coherency failure or hardware memory error."
        recommended_action = (
            "Run check_cache_coherency_panic on the full panic log. "
            "Verify dcache flush sequence during CPU suspend/resume. "
            "Inspect DRAM ECC and PMIC rail stability."
        )

    return ESREL1Output(
        raw_hex=raw,
        raw_value=value,
        ec=ec,
        ec_description=ec_description,
        il=il,
        il_description=il_description,
        iss=iss,
        iss_detail=iss_detail,
        is_data_abort=is_data_abort,
        is_instruction_abort=is_instruction_abort,
        is_serror=is_serror,
        recommended_action=recommended_action,
    )


# ---------------------------------------------------------------------------
# Skill 4: check_cache_coherency_panic
# ---------------------------------------------------------------------------

class CacheCoherencyInput(BaseModel):
    panic_log: str = Field(
        ...,
        description="Full kernel panic or dmesg log to scan for cache coherency indicators",
        examples=["[  1.234] SError Interrupt on CPU 2\n[  1.235] ESR_EL1 = 0xBE000000"],
    )


class CacheCoherencyOutput(BaseModel):
    is_coherency_panic: bool = Field(
        ..., description="True if the log contains cache coherency failure indicators"
    )
    indicators_found: list[str] = Field(
        ..., description="List of indicator keys that matched in the log"
    )
    esr_el1_hex: Optional[str] = Field(
        None, description="ESR_EL1 hex value extracted from the log (if present)"
    )
    esr_is_serror: bool = Field(
        False, description="True if the extracted ESR_EL1 has EC=0x2F (SError)"
    )
    root_cause: str = Field(..., description="Identified root cause or absence thereof")
    recommended_action: str = Field(..., description="Recommended remediation steps")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in the diagnosis")


# SError / cache coherency indicator patterns
_INDICATORS: dict[str, re.Pattern] = {
    "serror_interrupt":     re.compile(r"SError Interrupt", re.IGNORECASE),
    "arm64_serror":         re.compile(r"arm64:.*SError|taking pending SError", re.IGNORECASE),
    "imp_def_serror":       re.compile(r"IMP DEF SError", re.IGNORECASE),
    "bad_mode_error":       re.compile(r"Bad mode in Error handler", re.IGNORECASE),
    "cache_coherency_text": re.compile(r"cache coherenc", re.IGNORECASE),
    "poc_reference":        re.compile(r"Point of Coherency|PoC flush|dcache_poc", re.IGNORECASE),
    "dcache_flush_trace":   re.compile(r"dcache_by_line_op|__flush_dcache_area|flush_cache_all", re.IGNORECASE),
}

# Patterns that on their own (without SError) strongly suggest coherency failure
_STRONG_INDICATORS = {"serror_interrupt", "arm64_serror", "imp_def_serror", "bad_mode_error"}


def check_cache_coherency_panic(panic_log: str) -> CacheCoherencyOutput:
    """
    Detect AArch64 cache coherency (PoC) failure indicators in a kernel panic log.

    Scans for SError interrupts, ARM64-specific SError messages, cache maintenance
    operation traces, and ESR_EL1 values with EC=0x2F.

    Args:
        panic_log: Raw kernel panic or dmesg content.

    Returns:
        CacheCoherencyOutput with detection result and recommended action.
    """
    found: list[str] = [
        key for key, pattern in _INDICATORS.items()
        if pattern.search(panic_log)
    ]

    # Extract ESR_EL1 if present in the log
    esr_hex: Optional[str] = None
    esr_is_serror = False
    esr_match = re.search(r"ESR_EL1\s*[=:]\s*(0x[0-9a-fA-F]+)", panic_log)
    if esr_match:
        esr_hex = esr_match.group(1)
        ec = (int(esr_hex, 16) >> 26) & 0x3F
        esr_is_serror = ec == 0x2F
        if esr_is_serror and "esr_el1_serror" not in found:
            found.append("esr_el1_serror")

    is_coherency_panic = bool(set(found) & (_STRONG_INDICATORS | {"esr_el1_serror"}))

    if is_coherency_panic:
        root_cause = (
            "Cache coherency violation detected. One or more CPUs failed to synchronize "
            "their caches to the Point of Coherency (PoC) before or after a power state "
            "transition (suspend/resume). This can cause stale data to be read by a "
            "different CPU after it comes back online."
        )
        recommended_action = (
            "1. Verify that __flush_dcache_area() is called for all memory regions "
            "before CPU offline/suspend.\n"
            "2. Check that cache maintenance operations complete before the CPU is powered down "
            "(DSB SY barrier required).\n"
            "3. Review vendor suspend/resume hooks in drivers/cpuidle/ and arch/arm64/kernel/suspend.c.\n"
            "4. If ESR_EL1 is available, run decode_esr_el1 for detailed fault classification."
        )
        confidence = min(0.6 + 0.1 * len(found), 0.95)
    else:
        root_cause = "No cache coherency or SError indicators found in the panic log."
        recommended_action = (
            "Collect the full panic log including ESR_EL1 register value. "
            "Run decode_esr_el1 on the ESR_EL1 value to classify the exception type."
        )
        confidence = 0.1

    return CacheCoherencyOutput(
        is_coherency_panic=is_coherency_panic,
        indicators_found=found,
        esr_el1_hex=esr_hex,
        esr_is_serror=esr_is_serror,
        root_cause=root_cause,
        recommended_action=recommended_action,
        confidence=confidence,
    )
