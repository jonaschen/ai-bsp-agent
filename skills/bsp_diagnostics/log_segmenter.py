"""
Boot Log Segmenter — Universal Triage Entry Point (AGENTS.md §3.1).

The first skill invoked in every diagnostic session. Identifies the failing
boot stage boundary (Early Boot / Kernel Init / Android Init) before any
domain-specific skill is called, so the Brain routes correctly and focuses
its tool selection on the right domain.

Domain: All routes (universal triage — registered under every supervisor route)
"""
from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field

from skills.extensions import get_extension_patterns

BootStage = Literal["early_boot", "kernel_init", "android_init", "unknown"]

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class BootLogSegmenterInput(BaseModel):
    raw_log: str = Field(
        ...,
        description=(
            "Raw log text to triage — may be pre-kernel UART output (TF-A/LK/U-Boot), "
            "kernel dmesg, or Android logcat/init output"
        ),
    )


class BootLogSegmenterOutput(BaseModel):
    detected_stage: BootStage = Field(
        ..., description="Identified boot stage where the failure occurred"
    )
    first_error_line: Optional[str] = Field(
        None, description="First line in the log that contains an error indicator"
    )
    suggested_route: str = Field(
        ...,
        description=(
            "Recommended supervisor route: 'early_boot_advisor', 'kernel_pathologist', "
            "'android_init_advisor', or 'clarify_needed'"
        ),
    )
    stage_indicators: list[str] = Field(
        ..., description="Marker keys that led to the stage classification"
    )
    error_summary: str = Field(
        ..., description="Brief human-readable summary of the triage result"
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in the stage classification")


# ---------------------------------------------------------------------------
# Detection patterns
# ---------------------------------------------------------------------------

# Kernel timestamp — presence means we are in kernel or later
_KERNEL_TS_RE = re.compile(r"\[\s*\d+\.\d{4,6}\]")

# Early boot stage markers (pre-kernel UART output)
_EARLY_BOOT_MARKERS: dict[str, re.Pattern] = {
    "tf_a_bl1":      re.compile(r"NOTICE:\s+BL1:"),
    "tf_a_bl2":      re.compile(r"NOTICE:\s+BL2:"),
    "tf_a_bl31":     re.compile(r"NOTICE:\s+BL31:"),
    "tf_a_generic":  re.compile(r"Booting Trusted Firmware|TF-A\s+v\d", re.IGNORECASE),
    "lk_banner":     re.compile(r"\[0+\]\s+(?:LK|target_init|platform_init)", re.IGNORECASE),
    "lk_version":    re.compile(r"LK version:|LKVersion", re.IGNORECASE),
    "uboot_banner":  re.compile(r"U-Boot\s+\d{4}\.\d{2}"),
    "uefi_banner":   re.compile(r"UEFI firmware\s+|EDK II", re.IGNORECASE),
    "qcom_xbl":      re.compile(r"XBL CORE\s+Version|SBL1\s+build"),
}

# Android userspace markers (kernel timestamps present, plus these)
_ANDROID_MARKERS: dict[str, re.Pattern] = {
    "init_ok":        re.compile(r"\[\s+OK\s+\]|\[  OK  \]"),
    "init_failed":    re.compile(r"\[\s*FAILED\s*\]"),
    "zygote":         re.compile(r"Zygote\s*[:/]", re.IGNORECASE),
    "activity_mgr":   re.compile(r"ActivityManager", re.IGNORECASE),
    "selinux_policy": re.compile(r"SELinux:\s+(?:Loaded|Initializing|policy)", re.IGNORECASE),
    "android_init":   re.compile(r"init:\s+(?:Starting|Service|Parsing)", re.IGNORECASE),
}

# Error line patterns — used to extract first_error_line
_ERROR_LINE_RE = re.compile(
    r"(?:^|\s)(?:"
    r"ERROR:|ASSERT FAILED|Kernel panic|BUG:|FATAL|"
    r"Unable to handle|Oops:|Authentication failed|"
    r"Bad Linux ARM64 Image|### ERROR ###|"
    r"Failed to load|DDR.*init.*fail|"
    r"\[FAILED\]|PANIC:"
    r")",
    re.IGNORECASE | re.MULTILINE,
)

# Route mapping
_STAGE_TO_ROUTE: dict[BootStage, str] = {
    "early_boot":    "early_boot_advisor",
    "kernel_init":   "kernel_pathologist",
    "android_init":  "android_init_advisor",
    "unknown":       "clarify_needed",
}


# ---------------------------------------------------------------------------
# Skill function
# ---------------------------------------------------------------------------

def segment_boot_log(raw_log: str) -> BootLogSegmenterOutput:
    """
    Identify the failing boot stage boundary from a raw log.

    Checks for pre-kernel UART markers (early_boot), kernel timestamps +
    Android init markers (android_init), kernel timestamps alone
    (kernel_init), or none of the above (unknown).

    Args:
        raw_log: Raw log text from any boot stage.

    Returns:
        BootLogSegmenterOutput with stage, route suggestion, and first error.
    """
    has_kernel_ts = bool(_KERNEL_TS_RE.search(raw_log))

    # --- Early boot detection (no kernel timestamps + pre-kernel markers) ---
    early_indicators: list[str] = [
        key for key, pat in _EARLY_BOOT_MARKERS.items() if pat.search(raw_log)
    ]
    is_early_boot = bool(early_indicators) and not has_kernel_ts

    # --- Android init detection (kernel timestamps + Android markers) ---
    android_indicators: list[str] = [
        key for key, pat in _ANDROID_MARKERS.items() if pat.search(raw_log)
    ]
    is_android_init = has_kernel_ts and bool(android_indicators)

    # --- Stage resolution (priority: early_boot > android_init > kernel_init) ---
    if is_early_boot:
        detected_stage: BootStage = "early_boot"
        stage_indicators = early_indicators
        confidence = min(0.70 + 0.05 * len(early_indicators), 0.95)
        summary = (
            f"Pre-kernel UART log detected ({', '.join(early_indicators[:3])}). "
            "Route to early_boot_advisor for TF-A / LK / U-Boot analysis."
        )
    elif is_android_init:
        detected_stage = "android_init"
        stage_indicators = android_indicators
        confidence = min(0.70 + 0.05 * len(android_indicators), 0.95)
        summary = (
            f"Android userspace log detected ({', '.join(android_indicators[:3])}). "
            "Route to android_init_advisor for SELinux / init.rc / service analysis."
        )
    elif has_kernel_ts:
        detected_stage = "kernel_init"
        stage_indicators = ["kernel_timestamp"]
        confidence = 0.75
        summary = (
            "Kernel log detected (timestamp pattern present, no Android init markers). "
            "Route to kernel_pathologist or hardware_advisor for further triage."
        )
    else:
        # --- User extension patterns ---
        user_stage: Optional[BootStage] = None
        for pat in get_extension_patterns("segment_boot_log"):
            if re.search(pat["match"], raw_log, re.IGNORECASE):
                user_stage = pat["category"]  # type: ignore[assignment]
                break
        if user_stage is not None:
            detected_stage = user_stage
            stage_indicators = ["user_pattern"]
            confidence = 0.60
            summary = f"[user pattern] Stage classified as '{user_stage}' by user extension."
        else:
            detected_stage = "unknown"
            stage_indicators = []
            confidence = 0.20
            summary = (
                "No recognisable boot stage markers found. "
                "Log may be incomplete, corrupted, or not a boot log."
            )

    # --- First error line extraction ---
    first_error_line: Optional[str] = None
    for line in raw_log.splitlines():
        if _ERROR_LINE_RE.search(line):
            first_error_line = line.strip()
            break

    return BootLogSegmenterOutput(
        detected_stage=detected_stage,
        first_error_line=first_error_line,
        suggested_route=_STAGE_TO_ROUTE[detected_stage],
        stage_indicators=stage_indicators,
        error_summary=summary,
        confidence=confidence,
    )
