"""
Subsystem Diagnostic Skills — Phase 7.

Four log-content skills covering common kernel subsystem failures:

  check_clock_dependencies    — CCF probe-defer and clk_get failures
  diagnose_vfs_mount_failure  — VFS mount errors (root device not found)
  analyze_firmware_load_error — firmware request failures (request_firmware)
  analyze_early_oom_killer    — early OOM kill events before userspace stable

All inputs are plain strings (log content); no filesystem access.
Domain: Android BSP / Kernel Pathologist + Hardware Advisor
"""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field

from skills.extensions import get_extension_patterns


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ClockDepsInput(BaseModel):
    dmesg_log: str = Field(
        ...,
        description="Raw dmesg output containing kernel clock/probe messages.",
    )


class ClockDepsOutput(BaseModel):
    failure_detected: bool = Field(
        ..., description="True if a clock dependency or probe-defer failure was found"
    )
    deferred_devices: list[str] = Field(
        ..., description="Platform device names that had deferred_probe_pending"
    )
    missing_clocks: list[str] = Field(
        ..., description="Clock names that failed to be obtained (clk_get failed)"
    )
    root_cause: str = Field(..., description="Identified root cause or context")
    recommended_action: str = Field(..., description="Recommended remediation steps")
    confidence: float = Field(..., ge=0.0, le=1.0)


class VFSMountInput(BaseModel):
    dmesg_log: str = Field(
        ...,
        description="Raw dmesg output containing VFS mount or block device messages.",
    )


class VFSMountOutput(BaseModel):
    failure_detected: bool = Field(
        ..., description="True if a VFS mount failure was found"
    )
    device: Optional[str] = Field(
        None, description="Block device name that failed to mount (e.g. mmcblk0p14)"
    )
    error_code: Optional[int] = Field(
        None, description="Numeric errno from the mount failure (e.g. -6 = ENXIO, -22 = EINVAL)"
    )
    fs_type: Optional[str] = Field(
        None, description="Filesystem type if identifiable (e.g. ext4, fat)"
    )
    root_cause: str = Field(..., description="Identified root cause or context")
    recommended_action: str = Field(..., description="Recommended remediation steps")
    confidence: float = Field(..., ge=0.0, le=1.0)


class FirmwareLoadInput(BaseModel):
    dmesg_log: str = Field(
        ...,
        description="Raw dmesg output containing firmware request messages.",
    )


class FirmwareLoadOutput(BaseModel):
    failure_detected: bool = Field(
        ..., description="True if a firmware load failure was found"
    )
    firmware_files: list[str] = Field(
        ..., description="Firmware file names that failed to load"
    )
    drivers: list[str] = Field(
        ..., description="Driver names that reported the firmware failure"
    )
    root_cause: str = Field(..., description="Identified root cause or context")
    recommended_action: str = Field(..., description="Recommended remediation steps")
    confidence: float = Field(..., ge=0.0, le=1.0)


class EarlyOOMInput(BaseModel):
    dmesg_log: str = Field(
        ...,
        description="Raw dmesg output containing OOM killer messages.",
    )


class EarlyOOMOutput(BaseModel):
    oom_detected: bool = Field(
        ..., description="True if an OOM kill event was found"
    )
    victims: list[dict] = Field(
        ...,
        description=(
            "List of OOM kill victims. Each entry has: process (str), pid (int), "
            "oom_score_adj (int, optional), total_vm_kb (int, optional), "
            "anon_rss_kb (int, optional)."
        ),
    )
    root_cause: str = Field(..., description="Identified root cause or context")
    recommended_action: str = Field(..., description="Recommended remediation steps")
    confidence: float = Field(..., ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Patterns — clock dependencies
# ---------------------------------------------------------------------------

# "platform adreno_gpu: deferred_probe_pending"
# "platform sdhci@7c4000: deferred_probe_pending"
_DEFER_PROBE_RE = re.compile(
    r"platform\s+([\w@.:-]+):\s+deferred_probe_pending",
    re.IGNORECASE,
)

# "clk: failed to get clk 'gcc_gpu_cfg_ahb_clk' for adreno_gpu"
# "clk_get: cannot get parent clock 'pll_video0' for 'mdss_dsi_clk'"
_CLK_GET_FAIL_RE = re.compile(
    r"(?:failed to get clk|cannot get(?:\s+parent)?\s+clock)\s+'([^']+)'",
    re.IGNORECASE,
)

# "probe with driver failed with error -517"  (-517 = EPROBE_DEFER)
_EPROBE_DEFER_RE = re.compile(
    r"probe\s+(?:with\s+driver\s+)?(?:\w+\s+)?failed\s+with\s+error\s+(-517)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Patterns — VFS mount failure
# ---------------------------------------------------------------------------

# "VFS: Cannot open root device "mmcblk0p14" or unknown-block(0,0): error -6"
_VFS_FAIL_RE = re.compile(
    r'VFS:\s+Cannot\s+open\s+root\s+device\s+"?([^"\s]+)"?\s+or\s+\S+:\s+error\s+(-\d+)',
    re.IGNORECASE,
)

# "EXT4-fs (mmcblk0p14): unable to read superblock"
# "FAT-fs (mmcblk0p1): bogus logical sector size 0"
# Only matches error-indicating keywords — not success messages like "mounted".
_FS_ERROR_RE = re.compile(
    r"([\w\d]+-fs)\s+\(([^)]+)\):\s+(?:unable|bogus|error|failed|cannot|invalid|corrupt)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Patterns — firmware load error
# ---------------------------------------------------------------------------

# "Direct firmware load for ath10k/QCA9984/hw1.0/firmware-5.bin failed with error -2"
_FW_DIRECT_FAIL_RE = re.compile(
    r"Direct\s+firmware\s+load\s+for\s+(\S+)\s+failed\s+with\s+error\s+(-?\d+)",
    re.IGNORECASE,
)

# "request_firmware timed out for 'wifi_drv/fw.bin'"
_FW_TIMEOUT_RE = re.compile(
    r"request_firmware\s+timed\s+out\s+for\s+'([^']+)'",
    re.IGNORECASE,
)

# "ath10k_pci 0000:01:00.0: failed to fetch firmware: -2"
# Extract driver prefix before space or colon
_FW_DRIVER_RE = re.compile(
    r"^(?:\[[\s\d.]+\]\s+)?([\w_-]+)(?:\s+\S+)?:\s+(?:failed to fetch|could not load)\s+firmware",
    re.IGNORECASE | re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Patterns — OOM killer
# ---------------------------------------------------------------------------

# "Out of memory: Killed process 1234 (cameraserver) total-vm:512000kB, anon-rss:480000kB, ..."
_OOM_KILL_RE = re.compile(
    r"Out\s+of\s+memory:\s+Killed\s+process\s+(\d+)\s+\(([^)]+)\)"
    r"(?:.*?total-vm:(\d+)kB)?(?:.*?anon-rss:(\d+)kB)?(?:.*?oom_score_adj:(-?\d+))?",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Skill functions
# ---------------------------------------------------------------------------

def check_clock_dependencies(dmesg_log: str) -> ClockDepsOutput:
    """
    Detect kernel CCF clock dependency failures and probe-defer events.

    Scans for deferred_probe_pending markers, clk_get failures, and
    EPROBE_DEFER (-517) error codes. Extracts the names of affected
    platform devices and missing clock signals.

    Args:
        dmesg_log: Raw dmesg content.

    Returns:
        ClockDepsOutput with deferred device list and missing clock list.
    """
    deferred_devices: list[str] = []
    missing_clocks: list[str] = []

    for line in dmesg_log.splitlines():
        m = _DEFER_PROBE_RE.search(line)
        if m:
            dev = m.group(1)
            if dev not in deferred_devices:
                deferred_devices.append(dev)

        m = _CLK_GET_FAIL_RE.search(line)
        if m:
            clk = m.group(1)
            if clk not in missing_clocks:
                missing_clocks.append(clk)

    if not deferred_devices and not missing_clocks:
        for pat in get_extension_patterns("check_clock_dependencies"):
            if re.search(pat["match"], dmesg_log, re.IGNORECASE):
                return ClockDepsOutput(
                    failure_detected=True,
                    deferred_devices=[],
                    missing_clocks=[],
                    root_cause=f"[user pattern] {pat['description']}",
                    recommended_action="Pattern added by user extension — review the matched log line.",
                    confidence=0.60,
                )
        return ClockDepsOutput(
            failure_detected=False,
            deferred_devices=[],
            missing_clocks=[],
            root_cause="No clock dependency failures or probe-defer events detected.",
            recommended_action="No action required.",
            confidence=0.90,
        )

    parts: list[str] = []
    if deferred_devices:
        devs = ", ".join(deferred_devices[:3])
        parts.append(f"probe deferred for: {devs}")
    if missing_clocks:
        clks = ", ".join(missing_clocks[:3])
        parts.append(f"missing clock(s): {clks}")

    root_cause = (
        "Kernel CCF clock dependency failure. "
        + "; ".join(parts) + ". "
        "Devices are returned to the deferred probe list (EPROBE_DEFER = -517) "
        "because a required clock parent is not yet registered. This is typically "
        "caused by incorrect DTS clock-names ordering or a missing clock provider driver."
    )
    recommended_action = (
        "1. Check the DTS 'clocks' and 'clock-names' properties for the affected device.\n"
        "2. Verify that the clock provider driver (e.g. gcc, camcc) is probing before "
        "the consumer device.\n"
        "3. Add the clock provider to the 'depends-on' or 'init_calls' ordering if needed.\n"
        "4. Enable CONFIG_COMMON_CLK_DEBUG and dump /sys/kernel/debug/clk/clk_summary "
        "to see the full clock tree at runtime.\n"
        "5. Check for typos in 'clock-names' — a mismatch against the driver's "
        "expected name causes clk_get to return -ENOENT."
    )
    confidence = 0.85 if missing_clocks else 0.75

    return ClockDepsOutput(
        failure_detected=True,
        deferred_devices=deferred_devices,
        missing_clocks=missing_clocks,
        root_cause=root_cause,
        recommended_action=recommended_action,
        confidence=confidence,
    )


def diagnose_vfs_mount_failure(dmesg_log: str) -> VFSMountOutput:
    """
    Detect VFS root filesystem mount failures from dmesg.

    Parses 'VFS: Cannot open root device' messages and extracts the
    block device name and errno. Also checks for filesystem-level errors
    (EXT4, FAT) that may precede the VFS failure.

    Args:
        dmesg_log: Raw dmesg content.

    Returns:
        VFSMountOutput with device, error code, and filesystem type.
    """
    device: Optional[str] = None
    error_code: Optional[int] = None
    fs_type: Optional[str] = None

    m = _VFS_FAIL_RE.search(dmesg_log)
    if m:
        device = m.group(1)
        error_code = int(m.group(2))

    # Try to extract fs_type from filesystem-level error lines
    for line in dmesg_log.splitlines():
        fs_m = _FS_ERROR_RE.search(line)
        if fs_m:
            fs_type = fs_m.group(1).lower()  # e.g. "ext4-fs" → "ext4-fs"
            if device is None:
                device = fs_m.group(2)
            break

    if device is None and error_code is None:
        for pat in get_extension_patterns("diagnose_vfs_mount_failure"):
            if re.search(pat["match"], dmesg_log, re.IGNORECASE):
                return VFSMountOutput(
                    failure_detected=True,
                    device=None,
                    error_code=None,
                    fs_type=None,
                    root_cause=f"[user pattern] {pat['description']}",
                    recommended_action="Pattern added by user extension — review the matched log line.",
                    confidence=0.60,
                )
        return VFSMountOutput(
            failure_detected=False,
            device=None,
            error_code=None,
            fs_type=None,
            root_cause="No VFS mount failure detected.",
            recommended_action="No action required.",
            confidence=0.90,
        )

    _ERRNO_NAMES = {
        -2: "ENOENT (file/partition not found)",
        -5: "EIO (I/O error reading superblock)",
        -6: "ENXIO (no such device — partition may not exist)",
        -22: "EINVAL (invalid filesystem or corrupt superblock)",
        -28: "ENOSPC (no space left on device)",
    }
    errno_str = _ERRNO_NAMES.get(error_code, f"error {error_code}") if error_code else "unknown error"

    root_cause = (
        f"VFS failed to mount root filesystem"
        + (f" on '{device}'" if device else "")
        + f": {errno_str}. "
        "This prevents the kernel from transitioning to userspace."
    )
    recommended_action = (
        "1. Verify the 'root=' kernel cmdline parameter matches the actual partition.\n"
        "2. Check that the block device is detected: look for the partition in dmesg "
        "before the VFS line (mmcblk, nvme, sda).\n"
        "3. For -22 (EINVAL) / -5 (EIO): run fsck on the partition from a recovery image.\n"
        "4. For -6 (ENXIO): the partition table may be corrupt — check with 'parted' or "
        "'gdisk' from a recovery shell.\n"
        "5. Verify the filesystem driver is compiled in (not a module) for the root partition type."
    )
    confidence = 0.90 if error_code is not None else 0.70

    return VFSMountOutput(
        failure_detected=True,
        device=device,
        error_code=error_code,
        fs_type=fs_type,
        root_cause=root_cause,
        recommended_action=recommended_action,
        confidence=confidence,
    )


def analyze_firmware_load_error(dmesg_log: str) -> FirmwareLoadOutput:
    """
    Detect firmware file load failures from dmesg.

    Parses 'Direct firmware load for X failed' and 'request_firmware timed out'
    messages. Extracts the firmware file names and the driver names that
    reported the failure.

    Args:
        dmesg_log: Raw dmesg content.

    Returns:
        FirmwareLoadOutput with firmware file list and driver list.
    """
    firmware_files: list[str] = []
    drivers: list[str] = []

    for line in dmesg_log.splitlines():
        m = _FW_DIRECT_FAIL_RE.search(line)
        if m:
            fw = m.group(1)
            if fw not in firmware_files:
                firmware_files.append(fw)
            # Extract driver from the beginning of the line
            drv_m = re.match(r"^\[?[\s\d.]+\]?\s*([\w_-]+)", line)
            if drv_m:
                drv = drv_m.group(1)
                if drv not in drivers:
                    drivers.append(drv)
            continue

        m = _FW_TIMEOUT_RE.search(line)
        if m:
            fw = m.group(1)
            if fw not in firmware_files:
                firmware_files.append(fw)

        m = _FW_DRIVER_RE.search(line)
        if m:
            drv = m.group(1)
            if drv not in drivers:
                drivers.append(drv)

    if not firmware_files:
        for pat in get_extension_patterns("analyze_firmware_load_error"):
            if re.search(pat["match"], dmesg_log, re.IGNORECASE):
                return FirmwareLoadOutput(
                    failure_detected=True,
                    firmware_files=[],
                    drivers=[],
                    root_cause=f"[user pattern] {pat['description']}",
                    recommended_action="Pattern added by user extension — review the matched log line.",
                    confidence=0.60,
                )
        return FirmwareLoadOutput(
            failure_detected=False,
            firmware_files=[],
            drivers=[],
            root_cause="No firmware load failures detected.",
            recommended_action="No action required.",
            confidence=0.90,
        )

    fw_str = ", ".join(f"'{f}'" for f in firmware_files[:3])
    drv_str = (", ".join(drivers[:3]) + " ") if drivers else ""
    root_cause = (
        f"Firmware load failure: {drv_str}could not load {fw_str}. "
        "The kernel's request_firmware() call could not locate the binary in any "
        "of the standard firmware search paths (/lib/firmware, /vendor/firmware, etc.)."
    )
    recommended_action = (
        "1. Verify the firmware file is present in the rootfs or vendor partition "
        "at the expected path.\n"
        "2. Check /sys/module/firmware_class/parameters/path for the active firmware "
        "search path override.\n"
        "3. For -2 (ENOENT): the file is missing — copy it to /lib/firmware or "
        "/vendor/firmware.\n"
        "4. For -110 (ETIMEDOUT): userspace firmware loading daemon is not running "
        "— check udevd or Android ueventd.\n"
        "5. Ensure the firmware file name in the driver matches the actual file on disk "
        "(case-sensitive)."
    )
    confidence = 0.88

    return FirmwareLoadOutput(
        failure_detected=True,
        firmware_files=firmware_files,
        drivers=drivers,
        root_cause=root_cause,
        recommended_action=recommended_action,
        confidence=confidence,
    )


def analyze_early_oom_killer(dmesg_log: str) -> EarlyOOMOutput:
    """
    Detect early OOM kill events from dmesg.

    Parses 'Out of memory: Killed process N (name)' lines and extracts
    the victim process name, PID, oom_score_adj, and memory footprint.

    Args:
        dmesg_log: Raw dmesg content.

    Returns:
        EarlyOOMOutput with victim list and recommended action.
    """
    victims: list[dict] = []

    for line in dmesg_log.splitlines():
        m = _OOM_KILL_RE.search(line)
        if not m:
            continue
        entry: dict = {
            "pid": int(m.group(1)),
            "process": m.group(2),
        }
        if m.group(3):
            entry["total_vm_kb"] = int(m.group(3))
        if m.group(4):
            entry["anon_rss_kb"] = int(m.group(4))
        if m.group(5):
            entry["oom_score_adj"] = int(m.group(5))

        # Deduplicate by pid
        if not any(v["pid"] == entry["pid"] for v in victims):
            victims.append(entry)

    if not victims:
        for pat in get_extension_patterns("analyze_early_oom_killer"):
            if re.search(pat["match"], dmesg_log, re.IGNORECASE):
                return EarlyOOMOutput(
                    oom_detected=True,
                    victims=[],
                    root_cause=f"[user pattern] {pat['description']}",
                    recommended_action="Pattern added by user extension — review the matched log line.",
                    confidence=0.60,
                )
        return EarlyOOMOutput(
            oom_detected=False,
            victims=[],
            root_cause="No OOM kill events detected.",
            recommended_action="No action required.",
            confidence=0.90,
        )

    procs = ", ".join(f"'{v['process']}' (PID {v['pid']})" for v in victims[:3])
    critical = [v for v in victims if v.get("oom_score_adj", 1000) <= 0]
    severity = (
        "CRITICAL: system process(es) killed — device will likely reboot or be unstable"
        if critical
        else "userspace process(es) killed — device may continue operating"
    )
    root_cause = (
        f"OOM killer invoked: {len(victims)} process(es) killed ({procs}). "
        f"{severity}. "
        "Early OOM events indicate available memory was exhausted before userspace "
        "reached a stable state."
    )
    recommended_action = (
        "1. Check oom_score_adj of killed processes: score 0 means a protected system "
        "service was killed, which is severe.\n"
        "2. Review /proc/meminfo at the time of the kill: compare MemFree, Cached, "
        "and Slab to identify where memory went.\n"
        "3. If a HAL or daemon is the victim, check for a memory leak (growing VSZ/RSS "
        "over time in /proc/<pid>/status).\n"
        "4. Consider reducing tmpfs size or increasing CMA reservation in the DTS.\n"
        "5. Enable CONFIG_MEMCG to get per-cgroup memory accounting for better isolation."
    )
    confidence = 0.90 if critical else 0.80

    return EarlyOOMOutput(
        oom_detected=True,
        victims=victims,
        root_cause=root_cause,
        recommended_action=recommended_action,
        confidence=confidence,
    )
