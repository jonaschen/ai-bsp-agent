"""
Early Boot Diagnostic Skills.

Provides two deterministic tools for the Early Boot Advisor domain:
  - parse_early_boot_uart_log: detect TF-A / BootROM / PMIC failures in
    pre-kernel UART output (BL1, BL2, BL31, BL32, BL33 stages).
  - analyze_lk_panic: detect Little Kernel (LK) or U-Boot assert / panic
    messages and extract register state.

Domain: Android BSP / Early Boot Advisor (Pre-Kernel)
Reference: ARM Trusted Firmware-A source (github.com/TrustedFirmware-A),
           Little Kernel (LK) source, U-Boot source.
"""
from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field

from skills.extensions import get_extension_patterns

EarlyBootErrorType = Literal[
    "auth_failure",
    "image_load_failure",
    "ddr_init_failure",
    "pmic_failure",
    "generic_error",
    "none",
]

LKPanicType = Literal[
    "assert",
    "ddr_failure",
    "image_load",
    "pmic_failure",
    "generic",
    "none",
]

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class EarlyBootUARTInput(BaseModel):
    raw_uart_log: str = Field(
        ...,
        description=(
            "Raw UART serial output from the device, covering the pre-kernel boot "
            "sequence (BootROM → TF-A BL1/BL2/BL31 → BL33/U-Boot)"
        ),
    )


class EarlyBootUARTOutput(BaseModel):
    failure_detected: bool = Field(
        ..., description="True if a pre-kernel boot failure was found"
    )
    detected_bl_stage: Optional[str] = Field(
        None,
        description="Bootloader stage where the failure occurred (e.g. 'BL2', 'BL31', 'U-Boot')",
    )
    last_successful_step: Optional[str] = Field(
        None, description="Last boot step that completed successfully before the failure"
    )
    first_error_line: Optional[str] = Field(
        None, description="First log line containing an error indicator"
    )
    error_type: EarlyBootErrorType = Field(
        ..., description="Classified error category"
    )
    root_cause: str = Field(..., description="Identified root cause or absence of failure")
    recommended_action: str = Field(..., description="Recommended remediation steps")
    confidence: float = Field(..., ge=0.0, le=1.0)


class LKPanicInput(BaseModel):
    uart_log_snippet: str = Field(
        ...,
        description=(
            "UART log snippet covering the LK (Little Kernel) or U-Boot stage, "
            "including any assert or panic output"
        ),
    )


class LKPanicOutput(BaseModel):
    panic_detected: bool = Field(
        ..., description="True if a LK assert or U-Boot panic was found"
    )
    panic_type: LKPanicType = Field(
        ..., description="Classified panic category"
    )
    failing_function: Optional[str] = Field(
        None, description="Function or module where the assert/panic occurred"
    )
    assert_file: Optional[str] = Field(
        None, description="Source file referenced in the assert message"
    )
    assert_line: Optional[int] = Field(
        None, description="Line number referenced in the assert message"
    )
    register_dump: list[str] = Field(
        ..., description="Register state lines extracted from the log"
    )
    root_cause: str = Field(..., description="Identified root cause or absence of failure")
    recommended_action: str = Field(..., description="Recommended remediation steps")
    confidence: float = Field(..., ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Skill 1 patterns — parse_early_boot_uart_log
# ---------------------------------------------------------------------------

# TF-A stage detection — ordered BL1 → BL31 (earliest to latest)
_BL_STAGE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("BL1",    re.compile(r"NOTICE:\s+BL1:|BL1:\s+\w")),
    ("BL2",    re.compile(r"NOTICE:\s+BL2:|BL2:\s+\w")),
    ("BL31",   re.compile(r"NOTICE:\s+BL31:|BL31:\s+\w")),
    ("BL32",   re.compile(r"NOTICE:\s+BL32:|BL32:\s+\w")),
    ("BL33",   re.compile(r"NOTICE:\s+BL33:|BL33:\s+\w")),
    ("U-Boot", re.compile(r"U-Boot\s+\d{4}\.\d{2}")),
    ("XBL",    re.compile(r"XBL CORE|SBL1 build", re.IGNORECASE)),
    ("UEFI",   re.compile(r"UEFI firmware|EDK II", re.IGNORECASE)),
]

# Successful handoff markers — used to find last_successful_step
_HANDOFF_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("BL1 → BL2",    re.compile(r"BL1:\s+Booting BL2|Booting BL2 image")),
    ("BL2 → BL31",   re.compile(r"BL2:\s+Booting BL31|Loading BL31")),
    ("BL31 → BL33",  re.compile(r"BL31:\s+Booting BL33|Booting BL33")),
    ("BL2 → BL32",   re.compile(r"BL2:\s+Booting BL32|Loading BL32")),
    ("BL2 loaded",   re.compile(r"BL2:\s+Loading image id")),
    ("DDR init OK",  re.compile(r"DDR.*init.*(?:pass|ok|done|success)", re.IGNORECASE)),
]

# Error classification patterns
_AUTH_FAIL_RE = re.compile(
    r"Authentication.*(?:fail|error)|"
    r"Secure Boot.*fail|"
    r"BL\d+.*auth.*fail|"
    r"image integrity check.*fail|"
    r"ROTPK.*mismatch",
    re.IGNORECASE,
)

_IMAGE_LOAD_RE = re.compile(
    r"Failed to load image|"
    r"BL\d+.*Failed to load|"
    r"image load.*error|"
    r"FIP.*not found|"
    r"Bad Linux ARM64 Image|"
    r"Invalid.*image|"
    r"mmcblk.*read.*error",
    re.IGNORECASE,
)

_DDR_INIT_RE = re.compile(
    r"DDR.*init.*(?:fail|error)|"
    r"DDRSS.*fail|"
    r"lpddr4.*init.*fail|"
    r"memory.*init.*fail|"
    r"DRAM.*(?:fail|error)|"
    r"SMEM.*alloc.*fail",
    re.IGNORECASE,
)

_PMIC_EARLY_RE = re.compile(
    r"PMIC.*(?:fail|error|not respond|not ready)|"
    r"VDD.*not ready|"
    r"regulator.*(?:not ready|fail.*early)|"
    r"power.*sequence.*fail",
    re.IGNORECASE,
)

_GENERIC_ERROR_RE = re.compile(r"^(?:ERROR|ASSERT|PANIC|FATAL):", re.IGNORECASE | re.MULTILINE)


def parse_early_boot_uart_log(raw_uart_log: str) -> EarlyBootUARTOutput:
    """
    Detect and classify failures in TF-A / BootROM UART output.

    Identifies the bootloader stage (BL1, BL2, BL31, U-Boot) where the
    failure occurred, classifies the error type, and recommends a next step.

    Args:
        raw_uart_log: Pre-kernel UART serial output.

    Returns:
        EarlyBootUARTOutput with stage, error type, and recommended action.
    """
    # --- Detected BL stage: latest stage marker present ---
    detected_stage: Optional[str] = None
    for stage, pattern in reversed(_BL_STAGE_PATTERNS):
        if pattern.search(raw_uart_log):
            detected_stage = stage
            break

    # --- Last successful handoff ---
    last_good: Optional[str] = None
    for label, pattern in _HANDOFF_PATTERNS:
        if pattern.search(raw_uart_log):
            last_good = label

    # --- First error line ---
    first_error: Optional[str] = None
    for line in raw_uart_log.splitlines():
        if re.search(r"ERROR:|ASSERT|PANIC|Authentication fail|Failed to load|DDR.*fail", line, re.IGNORECASE):
            first_error = line.strip()
            break

    # --- Error classification (priority order) ---
    if _AUTH_FAIL_RE.search(raw_uart_log):
        error_type: EarlyBootErrorType = "auth_failure"
        root_cause = (
            "Secure Boot authentication failure. The bootloader image signature "
            "did not match the Root-of-Trust Public Key (ROTPK) stored in fuses, "
            "or the certificate chain is invalid."
        )
        recommended_action = (
            "1. Verify that the image was signed with the correct key matching the fused ROTPK.\n"
            "2. Check TF-A BL2 authentication logs for the specific image ID that failed.\n"
            "3. Confirm the FIP (Firmware Image Package) was assembled with the correct certificates.\n"
            "4. If testing with unsigned images, verify that TRUSTED_BOARD_BOOT=0 is set in the build."
        )
        confidence = 0.92

    elif _IMAGE_LOAD_RE.search(raw_uart_log):
        error_type = "image_load_failure"
        stage_str = f" at {detected_stage}" if detected_stage else ""
        root_cause = (
            f"Bootloader image load failure{stage_str}. The stage could not read "
            "the next firmware image from storage (eMMC/UFS/NOR). Possible causes: "
            "missing FIP partition, incorrect partition offset in GPT, or storage "
            "driver not initialised."
        )
        recommended_action = (
            "1. Check that the FIP partition (or equivalent) exists and is at the correct offset.\n"
            "2. Verify the partition table (GPT/MBR) with 'fastboot getvar all' or 'sgdisk -p'.\n"
            "3. Confirm the storage controller (eMMC/UFS) initialised successfully in earlier log lines.\n"
            "4. Re-flash the FIP/bootloader partition and retry."
        )
        confidence = 0.88

    elif _DDR_INIT_RE.search(raw_uart_log):
        error_type = "ddr_init_failure"
        root_cause = (
            "DDR / LPDDR initialisation failure. The memory controller could not "
            "train or initialise the DRAM. This is typically caused by incorrect "
            "DDR timing parameters, PMIC rail instability during memory power-on, "
            "or a hardware defect on the memory interface."
        )
        recommended_action = (
            "1. Check PMIC rail voltages (VDDQ, VDD2) during DDR init with a bench power supply.\n"
            "2. Review DDR timing parameters (CAS latency, tRCD, tRP) in the bootloader DTS or config.\n"
            "3. Run DDR stress tests at lower speed bins (reduce DDR frequency) to isolate signal integrity.\n"
            "4. Inspect PCB layout for impedance mismatch on DQ/DQS lines."
        )
        confidence = 0.90

    elif _PMIC_EARLY_RE.search(raw_uart_log):
        error_type = "pmic_failure"
        root_cause = (
            "PMIC power sequencing failure during early boot. A required voltage "
            "rail did not reach its target within the expected window, causing the "
            "bootloader to abort the boot sequence."
        )
        recommended_action = (
            "1. Measure all required rails (VDD_CPU, VDD_MX, VDDQ) during power-on with an oscilloscope.\n"
            "2. Check PMIC I2C/SPI communication: confirm the PMIC responds to early init commands.\n"
            "3. Review power sequencing order in the bootloader PMIC init table.\n"
            "4. Check for PMIC OTP/fuse settings that may limit rail voltages."
        )
        confidence = 0.85

    elif _GENERIC_ERROR_RE.search(raw_uart_log):
        error_type = "generic_error"
        stage_str = f" in {detected_stage}" if detected_stage else ""
        root_cause = (
            f"Generic error detected{stage_str}. The specific root cause "
            "could not be classified from available log content."
        )
        recommended_action = (
            "Collect the full UART log from power-on. Look for 'ERROR:' lines and "
            "match them against the TF-A source (plat/*/platform.c) or U-Boot logs."
        )
        confidence = 0.55

    else:
        if not raw_uart_log.strip():
            return EarlyBootUARTOutput(
                failure_detected=False,
                detected_bl_stage=None,
                last_successful_step=None,
                first_error_line=None,
                error_type="none",
                root_cause="Empty log provided.",
                recommended_action="Provide the UART serial output from the device.",
                confidence=0.9,
            )
        # --- User extension patterns (checked when built-in detection misses) ---
        for pat in get_extension_patterns("parse_early_boot_uart_log"):
            if re.search(pat["match"], raw_uart_log, re.IGNORECASE):
                first_error = next(
                    (l.strip() for l in raw_uart_log.splitlines()
                     if re.search(pat["match"], l, re.IGNORECASE)), None
                )
                return EarlyBootUARTOutput(
                    failure_detected=True,
                    detected_bl_stage=detected_stage,
                    last_successful_step=last_good,
                    first_error_line=first_error,
                    error_type=pat["category"],
                    root_cause=f"[user pattern] {pat['description']}",
                    recommended_action="Pattern added by user extension — review the matched log line.",
                    confidence=0.60,
                )
        return EarlyBootUARTOutput(
            failure_detected=False,
            detected_bl_stage=detected_stage,
            last_successful_step=last_good,
            first_error_line=None,
            error_type="none",
            root_cause="No early boot failure detected in the UART log.",
            recommended_action="No action required.",
            confidence=0.85,
        )

    return EarlyBootUARTOutput(
        failure_detected=True,
        detected_bl_stage=detected_stage,
        last_successful_step=last_good,
        first_error_line=first_error,
        error_type=error_type,
        root_cause=root_cause,
        recommended_action=recommended_action,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Skill 2 patterns — analyze_lk_panic
# ---------------------------------------------------------------------------

# LK assert: "ASSERT FAILED at [file:line]"
_LK_ASSERT_RE = re.compile(
    r"ASSERT FAILED\s+at\s+\[([^\]:]+):(\d+)\]|"
    r"ASSERT:\s+([^\n]+)",
    re.IGNORECASE,
)

# LK function name (appears before or at the assert)
_LK_FUNC_RE = re.compile(r"^\[0+\]\s+(\w[\w:]+)\s*\(", re.MULTILINE)

# U-Boot image errors
_UBOOT_IMAGE_RE = re.compile(
    r"Bad Linux ARM64 Image magic!|"
    r"Wrong Image Format|"
    r"ERROR: Failed to load kernel|"
    r"### ERROR ###.*Image",
    re.IGNORECASE,
)

# LK DDR failure
_LK_DDR_RE = re.compile(
    r"DDR.*(?:init.*fail|training.*fail|error)|"
    r"dram_init.*fail|"
    r"DDRSS.*fail",
    re.IGNORECASE,
)

# LK PMIC
_LK_PMIC_RE = re.compile(
    r"PMIC.*fail|"
    r"regulator.*fail.*LK|"
    r"target_init.*pmic.*error",
    re.IGNORECASE,
)

# Register dump lines
_REGISTER_LINE_RE = re.compile(
    r"^\s*(?:r\d+|sp|lr|pc|cpsr|x\d+|elr|spsr)\s*(?:=|:)\s*0x[0-9a-fA-F]+",
    re.MULTILINE,
)

# LK panic / abort
_LK_PANIC_RE = re.compile(r"(?:lk_)?panic\s*\(|PANIC:|data_abort|prefetch_abort", re.IGNORECASE)


def analyze_lk_panic(uart_log_snippet: str) -> LKPanicOutput:
    """
    Parse LK (Little Kernel) and U-Boot panic / assert messages.

    Extracts the assert file/line, failing function, register dump, and
    classifies the panic type.

    Args:
        uart_log_snippet: UART log covering the LK or U-Boot stage.

    Returns:
        LKPanicOutput with detection result and recommended action.
    """
    assert_match = _LK_ASSERT_RE.search(uart_log_snippet)
    uboot_image = _UBOOT_IMAGE_RE.search(uart_log_snippet)
    lk_ddr = _LK_DDR_RE.search(uart_log_snippet)
    lk_pmic = _LK_PMIC_RE.search(uart_log_snippet)
    lk_panic = _LK_PANIC_RE.search(uart_log_snippet)

    # --- Register dump ---
    register_lines = [
        line.strip() for line in _REGISTER_LINE_RE.findall(uart_log_snippet)
    ]
    # findall with groups returns strings — re-extract with finditer for full lines
    # Supports both:
    #   "x0 = 0xdeadbeef" (LK ARM32 / standard style)
    #   "x0  0x               1" (LK AArch64 space-padded style, one+ spaces)
    register_lines = [
        m.group().strip()
        for m in re.finditer(
            r"^\s*(?:r\d+|sp|lr|pc|cpsr|x\d+|elr|spsr)\s*(?:[=:]\s*| +)0x\s*[0-9a-fA-F]+[^\n]*",
            uart_log_snippet,
            re.MULTILINE | re.IGNORECASE,
        )
    ]

    # --- Failing function (from LK-style log prefix [0] func_name) ---
    func_match = _LK_FUNC_RE.search(uart_log_snippet)
    failing_function: Optional[str] = func_match.group(1) if func_match else None

    # --- Classification (priority order) ---
    if assert_match:
        panic_type: LKPanicType = "assert"
        # Group 1/2 from ASSERT FAILED form; group 3 from ASSERT: form
        if assert_match.group(1):
            assert_file: Optional[str] = assert_match.group(1)
            assert_line: Optional[int] = int(assert_match.group(2))
        else:
            assert_file = None
            assert_line = None
        root_cause = (
            f"LK assertion failure{f' at {assert_file}:{assert_line}' if assert_file else ''}. "
            "A runtime sanity check inside the bootloader failed, indicating an unexpected "
            "state — commonly caused by a NULL pointer, an out-of-range value, or a missing "
            "hardware initialisation step."
        )
        recommended_action = (
            f"1. Locate the assert in the LK source: {assert_file or 'check LK/target source'}.\n"
            "2. Add debug prints before the assert to trace which variable is invalid.\n"
            "3. Confirm all prerequisite init steps (clock, PMIC, storage) completed before "
            "the failing function.\n"
            "4. Check if the assert correlates with a recent DTS or board config change."
        )
        confidence = 0.92 if register_lines else 0.80

    elif lk_ddr:
        panic_type = "ddr_failure"
        assert_file = assert_line = None
        root_cause = (
            "DDR/DRAM initialisation failure detected in the LK stage. "
            "The bootloader could not complete memory training, preventing "
            "any further boot progress."
        )
        recommended_action = (
            "1. Check PMIC VDDQ/VDD2 rails during LK DDR init phase.\n"
            "2. Review LK DDR timing configuration for the specific DRAM part.\n"
            "3. Reduce DDR frequency to isolate signal integrity vs. timing issues.\n"
            "4. Check LK DDR calibration logs for failing byte lanes."
        )
        confidence = 0.88

    elif uboot_image:
        panic_type = "image_load"
        assert_file = assert_line = None
        root_cause = (
            "U-Boot failed to load or validate the Linux kernel image. "
            "The kernel Image magic number is incorrect, or the image at the "
            "configured load address is corrupted or missing."
        )
        recommended_action = (
            "1. Verify the kernel Image was built for AArch64 (magic bytes: 0x644D5241).\n"
            "2. Confirm the bootargs 'loadaddr' matches the address where the image is stored.\n"
            "3. Re-flash the boot partition: 'fastboot flash boot boot.img'.\n"
            "4. Check if the kernel image is compressed (Image.gz) and U-Boot is configured to decompress it."
        )
        confidence = 0.90

    elif lk_pmic:
        panic_type = "pmic_failure"
        assert_file = assert_line = None
        root_cause = (
            "PMIC initialisation failure in the LK stage. A required power "
            "rail did not stabilise within the expected window."
        )
        recommended_action = (
            "1. Scope PMIC rails during LK boot phase.\n"
            "2. Review PMIC init sequence in target/*/init.c.\n"
            "3. Check I2C/SPI communication between SoC and PMIC."
        )
        confidence = 0.82

    elif lk_panic:
        panic_type = "generic"
        assert_file = assert_line = None
        root_cause = (
            "Generic LK panic or abort detected. The specific cause "
            "could not be classified — collect a more complete UART log."
        )
        recommended_action = (
            "Enable verbose LK logging (set LK_DEBUGLEVEL=2) and capture "
            "the full UART output from reset."
        )
        # Raise confidence when register state was captured — the panic is real
        confidence = 0.75 if register_lines else 0.55

    else:
        # --- User extension patterns ---
        for pat in get_extension_patterns("analyze_lk_panic"):
            if re.search(pat["match"], uart_log_snippet, re.IGNORECASE):
                return LKPanicOutput(
                    panic_detected=True,
                    panic_type=pat["category"],
                    failing_function=failing_function,
                    assert_file=None,
                    assert_line=None,
                    register_dump=register_lines[:20],
                    root_cause=f"[user pattern] {pat['description']}",
                    recommended_action="Pattern added by user extension — review the matched log line.",
                    confidence=0.60,
                )
        return LKPanicOutput(
            panic_detected=False,
            panic_type="none",
            failing_function=None,
            assert_file=None,
            assert_line=None,
            register_dump=[],
            root_cause="No LK panic or U-Boot error detected in the log snippet.",
            recommended_action="No action required.",
            confidence=0.88,
        )

    return LKPanicOutput(
        panic_detected=True,
        panic_type=panic_type,
        failing_function=failing_function,
        assert_file=assert_file,
        assert_line=assert_line,
        register_dump=register_lines[:20],
        root_cause=root_cause,
        recommended_action=recommended_action,
        confidence=confidence,
    )
