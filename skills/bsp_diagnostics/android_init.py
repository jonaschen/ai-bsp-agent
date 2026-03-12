"""
Android Init Diagnostic Skills.

Parses Android userspace init and SELinux AVC log output.

  analyze_selinux_denial  — detects SELinux AVC denial events from dmesg/logcat.
  check_android_init_rc   — detects init.rc command failures and service crashes.

Domain: Android BSP / Android Init Advisor
Reference: Android SELinux architecture, init.rc service lifecycle.
"""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field

from skills.extensions import get_extension_patterns


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SELinuxDenialInput(BaseModel):
    logcat_log: str = Field(
        ...,
        description=(
            "Combined dmesg and/or logcat output from the device containing "
            "SELinux AVC denial lines (type=1400 audit lines). Accepts both "
            "kernel dmesg format ([timestamp] ...) and logcat format."
        ),
    )


class SELinuxDenialEntry(BaseModel):
    permission: str = Field(
        ..., description="SELinux permission that was denied (e.g. 'syslog_read')"
    )
    comm: Optional[str] = Field(
        None, description="Process name (comm=) if present in the denial line"
    )
    scontext: str = Field(
        ..., description="Source security context (e.g. u:r:shell:s0)"
    )
    tcontext: str = Field(
        ..., description="Target security context (e.g. u:object_r:vendor_toolbox_exec:s0)"
    )
    tclass: str = Field(
        ..., description="Object class (e.g. file, system, chr_file)"
    )
    permissive: bool = Field(
        ..., description="True if permissive=1 (logged but not blocked by policy)"
    )


class SELinuxDenialOutput(BaseModel):
    denial_detected: bool = Field(
        ..., description="True if at least one AVC denial was found"
    )
    denial_count: int = Field(
        ..., description="Total number of AVC denial lines parsed (before deduplication)"
    )
    denials: list[SELinuxDenialEntry] = Field(
        ..., description="Deduplicated list of unique denial entries"
    )
    enforcing_count: int = Field(
        ..., description="Number of denial lines with permissive=0 (actual enforcement)"
    )
    root_cause: str = Field(..., description="Identified root cause or context")
    recommended_action: str = Field(..., description="Recommended remediation steps")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in the diagnosis")


class AndroidInitRCInput(BaseModel):
    dmesg_log: str = Field(
        ...,
        description=(
            "Kernel dmesg output containing Android init log lines "
            "(e.g. 'init: Command ... took Xms and failed: reason'). "
            "Also captures service non-zero exit events."
        ),
    )


class FailedCommandEntry(BaseModel):
    command: str = Field(..., description="The failed init.rc command string")
    action: str = Field(..., description="The init.rc action trigger (e.g. 'boot')")
    rc_file: str = Field(..., description="Path to the init.rc file (e.g. /system/etc/init/hw/init.rc)")
    rc_line: int = Field(..., description="Line number in the rc file")
    reason: str = Field(..., description="Failure reason message from init")


class FailedServiceEntry(BaseModel):
    service: str = Field(..., description="Service name from init.rc")
    pid: int = Field(..., description="PID of the service process")
    exit_status: int = Field(..., description="Non-zero exit status code")


class AndroidInitRCOutput(BaseModel):
    failure_detected: bool = Field(
        ..., description="True if any init.rc command failure or service crash was found"
    )
    failed_commands: list[FailedCommandEntry] = Field(
        ..., description="List of init.rc commands that explicitly failed"
    )
    failed_services: list[FailedServiceEntry] = Field(
        ..., description="List of services that exited with a non-zero status"
    )
    root_cause: str = Field(..., description="Identified root cause or context")
    recommended_action: str = Field(..., description="Recommended remediation steps")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in the diagnosis")


# ---------------------------------------------------------------------------
# Detection patterns — SELinux AVC denial
# ---------------------------------------------------------------------------

# Matches both dmesg and logcat AVC denial formats.
# dmesg: "[timestamp] type=1400 audit(...): avc: denied { perm } for comm="x" scontext=... tcontext=... tclass=... permissive=N"
# logcat: "MM-DD ... I auditd: type=1400 audit(...): avc: denied { perm } for comm="x" ... permissive=N"
_AVC_DENIED_RE = re.compile(
    r"avc:\s+denied\s+\{\s*([\w\s]+?)\s*\}"   # { permission(s) }
    r".*?scontext=(\S+)"                        # scontext=X
    r".*?tcontext=(\S+)"                        # tcontext=X
    r".*?tclass=(\S+)"                          # tclass=X (stops at next whitespace)
    r".*?permissive=(\d)",                      # permissive=N
    re.IGNORECASE,
)

_AVC_COMM_RE = re.compile(r'comm="([^"]+)"')


# ---------------------------------------------------------------------------
# Detection patterns — init.rc failures
# ---------------------------------------------------------------------------

# init: Command 'CMD' action=ACTION (/path/to/init.rc:LINE) took Xms and failed: REASON
# The rc file path always starts with '/' which disambiguates it from action text.
_INIT_CMD_FAIL_RE = re.compile(
    r"init:\s+Command\s+'([^']+)'"             # 'command'
    r"\s+action=(.+?)"                          # action= (non-greedy)
    r"\s+\((/[^:)]+):(\d+)\)"                 # (/path:line)
    r"\s+took\s+\d+ms\s+and\s+failed:\s+(.+)$",  # reason
    re.IGNORECASE,
)

# init: Service 'NAME' (pid PID) exited with status STATUS ...
_INIT_SVC_EXIT_RE = re.compile(
    r"init:\s+Service\s+'([^']+)'\s+\(pid\s+(\d+)\)\s+exited\s+with\s+status\s+(\d+)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Skill functions
# ---------------------------------------------------------------------------

def analyze_selinux_denial(logcat_log: str) -> SELinuxDenialOutput:
    """
    Detect and classify SELinux AVC denial events from dmesg or logcat output.

    Parses all `avc: denied` lines, extracts permission, comm, scontext, tcontext,
    tclass, and permissive flag. Deduplicates by (permission, scontext, tcontext,
    tclass). Counts enforcing (permissive=0) vs permissive-mode (permissive=1) denials.

    Args:
        logcat_log: Combined dmesg and/or logcat text.

    Returns:
        SELinuxDenialOutput with detection result, denial list, and recommended action.
    """
    raw_denials: list[SELinuxDenialEntry] = []

    for line in logcat_log.splitlines():
        m = _AVC_DENIED_RE.search(line)
        if not m:
            continue
        permission = m.group(1).strip()
        scontext = m.group(2)
        tcontext = m.group(3)
        tclass = m.group(4)
        permissive = (m.group(5) == "1")

        comm_m = _AVC_COMM_RE.search(line)
        comm = comm_m.group(1) if comm_m else None

        raw_denials.append(SELinuxDenialEntry(
            permission=permission,
            comm=comm,
            scontext=scontext,
            tcontext=tcontext,
            tclass=tclass,
            permissive=permissive,
        ))

    if not raw_denials:
        # --- User extension patterns ---
        for pat in get_extension_patterns("analyze_selinux_denial"):
            if re.search(pat["match"], logcat_log, re.IGNORECASE):
                return SELinuxDenialOutput(
                    denial_detected=True,
                    denial_count=1,
                    denials=[],
                    enforcing_count=1,
                    root_cause=f"[user pattern] {pat['description']}",
                    recommended_action="Pattern added by user extension — review the matched log line.",
                    confidence=0.60,
                )
        return SELinuxDenialOutput(
            denial_detected=False,
            denial_count=0,
            denials=[],
            enforcing_count=0,
            root_cause="No SELinux AVC denial events detected.",
            recommended_action="No action required.",
            confidence=0.90,
        )

    enforcing_count = sum(1 for d in raw_denials if not d.permissive)

    # Deduplicate by (permission, scontext, tcontext, tclass) — keep first occurrence
    seen: set[tuple[str, str, str, str]] = set()
    unique_denials: list[SELinuxDenialEntry] = []
    for d in raw_denials:
        key = (d.permission, d.scontext, d.tcontext, d.tclass)
        if key not in seen:
            seen.add(key)
            unique_denials.append(d)

    # Build root cause
    perms = list({d.permission for d in unique_denials})[:3]
    perm_str = ", ".join(f"'{p}'" for p in perms)
    comms = [d.comm for d in unique_denials if d.comm]
    unique_comms = list(dict.fromkeys(comms))[:3]
    comm_str = f" by process(es) {', '.join(unique_comms)}" if unique_comms else ""
    enforcing_str = (
        f"{enforcing_count} enforcing (permissive=0)"
        if enforcing_count
        else "all permissive (permissive=1, logged but not blocked)"
    )
    root_cause = (
        f"SELinux detected {len(raw_denials)} AVC denial(s) ({enforcing_str}){comm_str}. "
        f"Denied permission(s): {perm_str}. "
        "These indicate a process is attempting an operation not permitted by the current SELinux policy."
    )
    recommended_action = (
        "1. Identify which denials are critical (permissive=0) vs informational (permissive=1).\n"
        "2. For each enforcing denial, determine if it is a legitimate policy gap or a genuine "
        "security concern.\n"
        "3. Use 'audit2allow' to generate candidate policy additions for legitimate access.\n"
        "4. Review the sepolicy source for the relevant domain and object type.\n"
        "5. If running with permissive=0 in production, ensure no critical service is blocked "
        "by an incomplete policy."
    )
    confidence = 0.90 if enforcing_count > 0 else 0.75

    return SELinuxDenialOutput(
        denial_detected=True,
        denial_count=len(raw_denials),
        denials=unique_denials,
        enforcing_count=enforcing_count,
        root_cause=root_cause,
        recommended_action=recommended_action,
        confidence=confidence,
    )


def check_android_init_rc(dmesg_log: str) -> AndroidInitRCOutput:
    """
    Detect init.rc command failures and service crashes from dmesg output.

    Parses:
    - 'init: Command ... took Xms and failed: reason' lines
    - 'init: Service ... exited with status N' lines (N != 0 only)

    Args:
        dmesg_log: Raw dmesg content with kernel timestamps.

    Returns:
        AndroidInitRCOutput with failure list and recommended action.
    """
    failed_commands: list[FailedCommandEntry] = []
    failed_services: list[FailedServiceEntry] = []

    for line in dmesg_log.splitlines():
        m = _INIT_CMD_FAIL_RE.search(line)
        if m:
            failed_commands.append(FailedCommandEntry(
                command=m.group(1),
                action=m.group(2).strip(),
                rc_file=m.group(3),
                rc_line=int(m.group(4)),
                reason=m.group(5).strip(),
            ))
            continue

        m = _INIT_SVC_EXIT_RE.search(line)
        if m:
            exit_status = int(m.group(3))
            if exit_status != 0:
                failed_services.append(FailedServiceEntry(
                    service=m.group(1),
                    pid=int(m.group(2)),
                    exit_status=exit_status,
                ))

    if not failed_commands and not failed_services:
        # --- User extension patterns ---
        for pat in get_extension_patterns("check_android_init_rc"):
            if re.search(pat["match"], dmesg_log, re.IGNORECASE):
                return AndroidInitRCOutput(
                    failure_detected=True,
                    failed_commands=[],
                    failed_services=[],
                    root_cause=f"[user pattern] {pat['description']}",
                    recommended_action="Pattern added by user extension — review the matched log line.",
                    confidence=0.60,
                )
        return AndroidInitRCOutput(
            failure_detected=False,
            failed_commands=[],
            failed_services=[],
            root_cause="No init.rc command failures or service crashes detected.",
            recommended_action="No action required.",
            confidence=0.90,
        )

    # Build root cause
    parts: list[str] = []
    if failed_commands:
        cmds = [f"'{c.command}'" for c in failed_commands[:3]]
        parts.append(f"{len(failed_commands)} init.rc command failure(s): {', '.join(cmds)}")
    if failed_services:
        svcs = [
            f"'{s.service}' (exit {s.exit_status})" for s in failed_services[:3]
        ]
        parts.append(f"{len(failed_services)} service crash(es): {', '.join(svcs)}")

    root_cause = (
        "Android init.rc failures detected. "
        + "; ".join(parts) + ". "
        "These indicate misconfigured services, missing system properties, "
        "or incompatible vendor init scripts."
    )
    recommended_action = (
        "1. For 'service not found': verify the service is defined in a vendor init.rc "
        "file present in the current build.\n"
        "2. For property-expansion failures: ensure the property is set before the "
        "action trigger fires (check init.rc ordering and property triggers).\n"
        "3. For non-zero service exits: check logcat for the service's stderr/stdout output "
        "around the same timestamp.\n"
        "4. Cross-reference rc_file path and line number against the init.rc source tree."
    )
    confidence = 0.85 if failed_commands else 0.70

    return AndroidInitRCOutput(
        failure_detected=True,
        failed_commands=failed_commands,
        failed_services=failed_services,
        root_cause=root_cause,
        recommended_action=recommended_action,
        confidence=confidence,
    )
