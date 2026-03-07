"""
Vendor Boot UFS Driver Diagnostic Skill.

Detects UFS (Universal Flash Storage) driver load failures during the STD
(Suspend-to-Disk) restore phase, which can prevent the system from completing
resume from disk.

Domain: Android BSP / Hardware Advisor (Storage & Boot)
"""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class VendorBootUFSInput(BaseModel):
    dmesg_log: str = Field(
        ...,
        description=(
            "Raw dmesg output from the device, ideally covering the full STD "
            "restore sequence (kernel boot through vendor_boot completion)"
        ),
    )


class VendorBootUFSOutput(BaseModel):
    failure_detected: bool = Field(
        ..., description="True if a UFS driver load or link failure was found"
    )
    error_lines: list[str] = Field(
        ..., description="Exact dmesg lines that matched UFS error indicators"
    )
    failure_phase: Optional[str] = Field(
        None,
        description=(
            "Phase in which the failure occurred: 'probe', 'link_startup', or 'resume'"
        ),
    )
    root_cause: str = Field(..., description="Identified root cause or absence of failure")
    recommended_action: str = Field(..., description="Recommended remediation steps")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in the diagnosis")


# ---------------------------------------------------------------------------
# Detection patterns — ordered from most to least specific
# ---------------------------------------------------------------------------

# Each entry: (phase, compiled_pattern)
_PHASE_PATTERNS: list[tuple[str, re.Pattern]] = [
    # --- resume phase ---
    ("resume", re.compile(
        r"ufshcd_host_reset_and_restore.*failed|"
        r"ufshcd_eh_host_reset_handler.*failed|"
        r"ufshcd.*resume.*error|"
        r"ufs.*resume.*fail",
        re.IGNORECASE,
    )),
    # --- link startup phase ---
    ("link_startup", re.compile(
        r"ufshcd_link_startup.*failed|"
        r"UFS link startup failed|"
        r"ufshcd_hba_enable.*failed|"
        r"ufshcd_wait_for_dev_cmd.*failed|"
        r"ufshcd_uic_pwr_ctrl.*failed",
        re.IGNORECASE,
    )),
    # --- probe / initialisation phase ---
    ("probe", re.compile(
        r"ufshcd_probe_hba.*failed|"
        r"ufs.*probe.*failed|"
        r"ufshcd.*init.*error|"
        r"ufshcd.*error.*-\d+|"
        r"ufshcd.*failed to (enable|initialize|reset)",
        re.IGNORECASE,
    )),
]

# Catch-all UFS error lines (any phase).
# Allows optional device identifier between driver name and error keyword,
# e.g. "ufs_qcom 1d84000.ufshc: error -5" or "ufshcd-hisi ff3c0000.ufs: Reset failed".
_GENERIC_UFS_ERROR = re.compile(
    r"(ufshcd|ufs_qcom|ufs-qcom|ufs_mtk).*(error|fail|timeout|abort|reset|panic|fatal)",
    re.IGNORECASE,
)

# Lines that indicate the STD restore is underway (context filter)
_STD_RESTORE_CONTEXT = re.compile(
    r"Restoring|restore.*image|read.*hibernation|PM: Loading|PM: Restoring",
    re.IGNORECASE,
)


def check_vendor_boot_ufs_driver(dmesg_log: str) -> VendorBootUFSOutput:
    """
    Detect UFS driver load failures during STD restore phase.

    Scans dmesg for ufshcd / ufs_qcom error messages and classifies them
    by failure phase (probe, link_startup, or resume).

    Args:
        dmesg_log: Raw dmesg content.

    Returns:
        VendorBootUFSOutput with detection result and recommended action.
    """
    error_lines: list[str] = []
    detected_phase: Optional[str] = None

    # Check for STD restore context (raises confidence when present)
    in_std_restore = bool(_STD_RESTORE_CONTEXT.search(dmesg_log))

    for line in dmesg_log.splitlines():
        matched_phase: Optional[str] = None
        for phase, pattern in _PHASE_PATTERNS:
            if pattern.search(line):
                matched_phase = phase
                break
        if matched_phase is None and _GENERIC_UFS_ERROR.search(line):
            matched_phase = "unknown"
        if matched_phase is not None:
            error_lines.append(line.strip())
            # Prefer the most specific (first) phase we observe
            if detected_phase is None or matched_phase != "unknown":
                detected_phase = matched_phase

    if not error_lines:
        return VendorBootUFSOutput(
            failure_detected=False,
            error_lines=[],
            failure_phase=None,
            root_cause="No UFS driver errors detected in dmesg.",
            recommended_action="No action required.",
            confidence=0.9,
        )

    # Build root cause description based on phase
    if detected_phase == "resume":
        root_cause = (
            "UFS driver failed to restore the host controller state during STD resume. "
            "The ufshcd_host_reset_and_restore() call did not complete successfully, "
            "preventing the block device from becoming accessible after hibernation restore."
        )
        recommended_action = (
            "1. Check vendor ufshcd_pltfrm_resume() implementation for missing clock/reset sequencing.\n"
            "2. Verify that all PMIC rails (VCC, VCCQ, VCCQ2) are stable before UFS link re-initialisation.\n"
            "3. Increase ufshcd_wait_for_dev_cmd timeout if the UFS device needs more warm-up time.\n"
            "4. Inspect ufshcd_eh_host_reset_handler() in drivers/ufs/core/ufshcd.c for error propagation."
        )
        confidence = 0.88 if in_std_restore else 0.70
    elif detected_phase == "link_startup":
        root_cause = (
            "UFS link startup failed. The UIC layer could not bring up the M-PHY link "
            "between the SoC UFS host controller and the UFS device. This may indicate "
            "a power sequencing issue, a hardware reset not being deasserted, or a "
            "firmware incompatibility."
        )
        recommended_action = (
            "1. Verify UFS device Vcc/Vccq power rails are within spec before link startup.\n"
            "2. Check RST_N (reset) signal deassert timing relative to Vcc stabilisation.\n"
            "3. Review UIC PA_MAXRXHSGEAR / PA_TXGEAR attributes for compatibility with the device.\n"
            "4. Check ufshcd-pltfrm variant driver for SoC-specific power-on sequencing hooks."
        )
        confidence = 0.82
    elif detected_phase == "probe":
        root_cause = (
            "UFS host controller probe failed. The ufshcd driver could not initialise "
            "the hardware during kernel boot or STD restore, preventing the UFS block "
            "device from being registered with the kernel."
        )
        recommended_action = (
            "1. Check dmesg for IOMMU or clock framework errors before the UFS probe error.\n"
            "2. Verify device tree bindings: clocks, resets, PHY handles, and reg addresses.\n"
            "3. Confirm that the vendor UFS PHY driver is present in the ramdisk/vendor_boot.\n"
            "4. Run 'lspci'/'ls /sys/bus/platform/devices' to confirm MMIO is mapped."
        )
        confidence = 0.75
    else:
        root_cause = (
            f"UFS driver errors detected ({len(error_lines)} lines). "
            "Phase could not be determined from the log context."
        )
        recommended_action = (
            "Collect the full boot log from power-on through vendor_boot stage. "
            "Look for 'ufshcd_probe_hba', 'ufshcd_link_startup', and resume error messages."
        )
        confidence = 0.55

    return VendorBootUFSOutput(
        failure_detected=True,
        error_lines=error_lines[:20],  # cap to 20 lines to stay within token budget
        failure_phase=detected_phase,
        root_cause=root_cause,
        recommended_action=recommended_action,
        confidence=confidence,
    )
