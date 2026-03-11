"""
STD (Suspend-to-Disk) Hibernation Diagnostic Skill.

Parses dmesg and /proc/meminfo logs to diagnose hibernation image creation
failures (Error -12).

Domain: Android BSP / Power Management
"""
import re
from typing import Optional
from pydantic import BaseModel, Field

from skills.extensions import get_extension_patterns


SUNRECLAIM_THRESHOLD_RATIO = 0.10  # 10% of MemTotal


class STDHibernationInput(BaseModel):
    dmesg_log: str = Field(..., description="Raw dmesg output from the device")
    meminfo_log: str = Field(..., description="Raw /proc/meminfo output from the device")


class STDHibernationOutput(BaseModel):
    error_detected: bool = Field(..., description="Whether 'Error -12 creating hibernation image' was found in dmesg")
    mem_total_kb: Optional[int] = Field(None, description="MemTotal from meminfo (kB)")
    sunreclaim_kb: Optional[int] = Field(None, description="SUnreclaim from meminfo (kB)")
    swap_free_kb: Optional[int] = Field(None, description="SwapFree from meminfo (kB)")
    sunreclaim_ratio: Optional[float] = Field(None, description="SUnreclaim / MemTotal ratio")
    sunreclaim_exceeds_threshold: bool = Field(False, description="Whether SUnreclaim > 10% of MemTotal")
    root_cause: str = Field(..., description="Identified root cause of the failure")
    recommended_action: str = Field(..., description="Recommended remediation action")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in the diagnosis")


def _parse_meminfo_field(meminfo_log: str, field: str) -> Optional[int]:
    """Extract a kB integer value for a named field from /proc/meminfo."""
    match = re.search(rf"^{re.escape(field)}:\s+(\d+)\s+kB", meminfo_log, re.MULTILINE)
    if match:
        return int(match.group(1))
    return None


def analyze_std_hibernation_error(dmesg_log: str, meminfo_log: str) -> STDHibernationOutput:
    """
    Analyze STD hibernation failure from dmesg and meminfo logs.

    Checks for 'Error -12 creating hibernation image' in dmesg, then
    evaluates whether high SUnreclaim or insufficient swap is the root cause.

    Args:
        dmesg_log: Raw dmesg content.
        meminfo_log: Raw /proc/meminfo content.

    Returns:
        STDHibernationOutput with root cause and recommended action.
    """
    error_detected = "Error -12 creating hibernation image" in dmesg_log

    mem_total_kb = _parse_meminfo_field(meminfo_log, "MemTotal")
    sunreclaim_kb = _parse_meminfo_field(meminfo_log, "SUnreclaim")
    swap_free_kb = _parse_meminfo_field(meminfo_log, "SwapFree")

    sunreclaim_ratio: Optional[float] = None
    sunreclaim_exceeds_threshold = False

    if mem_total_kb and sunreclaim_kb:
        sunreclaim_ratio = sunreclaim_kb / mem_total_kb
        sunreclaim_exceeds_threshold = sunreclaim_ratio > SUNRECLAIM_THRESHOLD_RATIO

    if not error_detected:
        # --- User extension patterns ---
        combined = dmesg_log + "\n" + meminfo_log
        for pat in get_extension_patterns("analyze_std_hibernation_error"):
            if re.search(pat["match"], combined, re.IGNORECASE):
                return STDHibernationOutput(
                    error_detected=True,
                    mem_total_kb=mem_total_kb,
                    sunreclaim_kb=sunreclaim_kb,
                    swap_free_kb=swap_free_kb,
                    sunreclaim_ratio=sunreclaim_ratio,
                    sunreclaim_exceeds_threshold=sunreclaim_exceeds_threshold,
                    root_cause=f"[user pattern] {pat['description']}",
                    recommended_action="Pattern added by user extension — review the matched log line.",
                    confidence=0.60,
                )
        return STDHibernationOutput(
            error_detected=False,
            mem_total_kb=mem_total_kb,
            sunreclaim_kb=sunreclaim_kb,
            swap_free_kb=swap_free_kb,
            sunreclaim_ratio=sunreclaim_ratio,
            sunreclaim_exceeds_threshold=sunreclaim_exceeds_threshold,
            root_cause="No hibernation error detected in dmesg.",
            recommended_action="No action required.",
            confidence=1.0,
        )

    if sunreclaim_exceeds_threshold:
        return STDHibernationOutput(
            error_detected=True,
            mem_total_kb=mem_total_kb,
            sunreclaim_kb=sunreclaim_kb,
            swap_free_kb=swap_free_kb,
            sunreclaim_ratio=sunreclaim_ratio,
            sunreclaim_exceeds_threshold=True,
            root_cause=(
                f"SUnreclaim ({sunreclaim_kb} kB) exceeds 10% of MemTotal "
                f"({mem_total_kb} kB). Unreclaimable slab memory is preventing "
                "hibernation image allocation."
            ),
            recommended_action="echo 3 > /proc/sys/vm/drop_caches",
            confidence=0.92,
        )

    if swap_free_kb is not None and swap_free_kb == 0:
        return STDHibernationOutput(
            error_detected=True,
            mem_total_kb=mem_total_kb,
            sunreclaim_kb=sunreclaim_kb,
            swap_free_kb=0,
            sunreclaim_ratio=sunreclaim_ratio,
            sunreclaim_exceeds_threshold=False,
            root_cause="SwapFree is 0 kB. No swap space available for the hibernation image.",
            recommended_action=(
                "Increase swap partition size or add a swap file. "
                "Minimum recommended: equal to MemTotal."
            ),
            confidence=0.88,
        )

    return STDHibernationOutput(
        error_detected=True,
        mem_total_kb=mem_total_kb,
        sunreclaim_kb=sunreclaim_kb,
        swap_free_kb=swap_free_kb,
        sunreclaim_ratio=sunreclaim_ratio,
        sunreclaim_exceeds_threshold=False,
        root_cause=(
            "Error -12 detected but SUnreclaim is within threshold and swap is available. "
            "Root cause may be fragmentation or a transient memory spike. "
            "Further investigation required."
        ),
        recommended_action=(
            "Collect a full meminfo snapshot at the moment of failure and check "
            "/proc/buddyinfo for memory fragmentation."
        ),
        confidence=0.45,
    )
