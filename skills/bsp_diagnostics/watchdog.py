"""
Watchdog Timeout Diagnostic Skill.

Parses soft lockup and hard lockup events from kernel dmesg logs.
Extracts CPU number, PID, process name, stuck duration, and call trace.

Domain: Android BSP / Kernel Pathologist
Reference: Linux kernel watchdog/softlockup.c, watchdog/hardlockup.c
"""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class WatchdogInput(BaseModel):
    dmesg_log: str = Field(
        ...,
        description=(
            "Raw dmesg output from the device, covering the lockup event "
            "and surrounding context (ideally the full log)"
        ),
    )


class WatchdogOutput(BaseModel):
    lockup_detected: bool = Field(
        ..., description="True if a soft or hard lockup event was found"
    )
    lockup_type: Optional[str] = Field(
        None, description="'soft_lockup' or 'hard_lockup'"
    )
    cpu: Optional[int] = Field(
        None, description="CPU number on which the lockup was detected"
    )
    pid: Optional[int] = Field(
        None, description="PID of the task involved in the lockup"
    )
    process_name: Optional[str] = Field(
        None, description="Name of the task/process involved in the lockup"
    )
    stuck_duration_s: Optional[float] = Field(
        None, description="Duration in seconds the CPU was stuck (from log message)"
    )
    call_trace: list[str] = Field(
        ..., description="Extracted call trace lines from the lockup event"
    )
    root_cause: str = Field(..., description="Identified root cause or context")
    recommended_action: str = Field(..., description="Recommended remediation steps")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in the diagnosis")


# ---------------------------------------------------------------------------
# Detection patterns
# ---------------------------------------------------------------------------

# Soft lockup: "watchdog: BUG: soft lockup - CPU#3 stuck for 23s! [kworker/u8:4:1234]"
# Process name may contain colons (e.g. "kworker/u8:4"), so use a greedy capture
# for the name and let the final ":PID" be the last colon-separated segment.
_SOFT_LOCKUP_RE = re.compile(
    r"(?:watchdog[:\s]+)?BUG:\s*soft\s+lockup\s*[-–]\s*CPU#(\d+)\s+stuck\s+for\s+([\d.]+)s[!.]?\s*"
    r"\[(.+):(\d+)\]",
    re.IGNORECASE,
)

# Hard lockup (NMI watchdog): "watchdog: BUG: hard lockup on CPU 2"
_HARD_LOCKUP_RE = re.compile(
    r"(?:NMI\s+)?(?:watchdog[:\s]+)?BUG:\s*hard\s+lockup\s+(?:on\s+CPU\s+|[-–]\s*CPU#)(\d+)",
    re.IGNORECASE,
)

# RCU stall — treated as soft lockup class
_RCU_STALL_RE = re.compile(
    r"rcu[_\-]sched(?:\s+self-detected)?\s+stall\s+on\s+CPU\s*(\d+)|"
    r"INFO:\s+rcu_sched\s+(?:self-)?detected\s+stall",
    re.IGNORECASE,
)

# Call trace lines: look for hex function offsets like "my_func+0x3c/0x120".
# Use search() (not match()) because lines may start with a kernel timestamp
# prefix like "[  120.004000]" before the function offset.
_CALL_TRACE_START = re.compile(r"Call trace:|call trace:", re.IGNORECASE)
_CALL_TRACE_LINE = re.compile(r"[\w.]+\+0x[\da-f]+/0x[\da-f]+")
_REGISTER_LINE = re.compile(r"\b(x\d+|pc|lr|sp)\s*:", re.IGNORECASE)

# Task info line: "CPU: 3 PID: 1234 Comm: kworker/u8:4"
_TASK_INFO_RE = re.compile(
    r"CPU:\s*(\d+)\s+PID:\s*(\d+)\s+Comm:\s*([\w/:.-]+)",
    re.IGNORECASE,
)


def analyze_watchdog_timeout(dmesg_log: str) -> WatchdogOutput:
    """
    Parse soft lockup and hard lockup events from a dmesg log.

    Extracts CPU number, PID, process name, stuck duration, and call trace
    from the first lockup event found.

    Args:
        dmesg_log: Raw dmesg content.

    Returns:
        WatchdogOutput with detection result and recommended action.
    """
    lines = dmesg_log.splitlines()

    lockup_type: Optional[str] = None
    cpu: Optional[int] = None
    pid: Optional[int] = None
    process_name: Optional[str] = None
    stuck_duration_s: Optional[float] = None
    lockup_line_idx: Optional[int] = None

    # --- Scan for lockup event ---
    for idx, line in enumerate(lines):
        if lockup_type is not None:
            break

        m = _SOFT_LOCKUP_RE.search(line)
        if m:
            lockup_type = "soft_lockup"
            cpu = int(m.group(1))
            stuck_duration_s = float(m.group(2))
            process_name = m.group(3)
            pid = int(m.group(4))
            lockup_line_idx = idx
            continue

        m = _HARD_LOCKUP_RE.search(line)
        if m:
            lockup_type = "hard_lockup"
            cpu = int(m.group(1))
            lockup_line_idx = idx
            continue

        m = _RCU_STALL_RE.search(line)
        if m:
            lockup_type = "soft_lockup"
            try:
                cpu = int(m.group(1))
            except (IndexError, TypeError):
                pass
            lockup_line_idx = idx

    if lockup_type is None:
        return WatchdogOutput(
            lockup_detected=False,
            lockup_type=None,
            cpu=None,
            pid=None,
            process_name=None,
            stuck_duration_s=None,
            call_trace=[],
            root_cause="No soft lockup or hard lockup event detected in dmesg.",
            recommended_action="No action required.",
            confidence=0.9,
        )

    # --- Extract task info (PID/Comm) from the context window around the lockup line ---
    search_start = max(0, lockup_line_idx - 5)
    search_end = min(len(lines), lockup_line_idx + 30)
    context_lines = lines[search_start:search_end]

    if pid is None or process_name is None:
        for line in context_lines:
            m = _TASK_INFO_RE.search(line)
            if m:
                if cpu is None:
                    cpu = int(m.group(1))
                if pid is None:
                    pid = int(m.group(2))
                if process_name is None:
                    process_name = m.group(3)
                break

    # --- Extract call trace ---
    call_trace: list[str] = []
    in_call_trace = False
    for line in context_lines:
        if _CALL_TRACE_START.search(line):
            in_call_trace = True
            continue
        if in_call_trace:
            if _CALL_TRACE_LINE.search(line):
                call_trace.append(line.strip())
            elif _REGISTER_LINE.search(line):
                # register dumps interspersed with call trace — skip
                continue
            elif line.strip() and call_trace:
                # Non-trace, non-register, non-empty line after trace started → end
                break

    # --- Build root cause ---
    if lockup_type == "soft_lockup":
        duration_str = f" for {stuck_duration_s:.0f}s" if stuck_duration_s else ""
        proc_str = f"'{process_name}' (PID {pid})" if process_name and pid else "a task"
        cpu_str = f" on CPU#{cpu}" if cpu is not None else ""
        root_cause = (
            f"Soft lockup detected{cpu_str}: {proc_str} held the CPU{duration_str} "
            "without scheduling. This indicates the task is spinning in kernel code "
            "without yielding, blocking all other tasks on that CPU."
        )
        recommended_action = (
            "1. Inspect the call trace to identify the spinning function.\n"
            "2. Check whether the lockup occurs during suspend (kworker/cpufreq hot path).\n"
            "3. Look for spinlock contention: add 'lockdep=1' to kernel cmdline.\n"
            "4. If the stuck task is a driver thread, check for infinite polling loops "
            "or a missing completion/wait_event call.\n"
            "5. Enable CONFIG_SOFTLOCKUP_DETECTOR and CONFIG_HARDLOCKUP_DETECTOR in the kernel."
        )
        confidence = 0.90 if call_trace else 0.70
    else:
        cpu_str = f" on CPU#{cpu}" if cpu is not None else ""
        root_cause = (
            f"Hard lockup (NMI watchdog timeout) detected{cpu_str}. "
            "The CPU did not service the NMI watchdog timer, indicating that interrupts "
            "were disabled for longer than the watchdog threshold (typically 20 s). "
            "This is more severe than a soft lockup and usually indicates a kernel bug, "
            "hardware error, or a driver holding interrupts disabled in a tight loop."
        )
        recommended_action = (
            "1. Inspect the call trace for the interrupt-disabled code path.\n"
            "2. Search for 'local_irq_disable()' / 'spin_lock_irqsave()' held across "
            "long operations in the faulting driver.\n"
            "3. Check for SMC/EL3 firmware calls that block the CPU with HVC/SMC.\n"
            "4. Enable CONFIG_HARDLOCKUP_DETECTOR_PERF and collect a stack trace with "
            "NMI shootdown before the system hangs.\n"
            "5. Check for thermal/voltage events that may have caused the CPU to throttle "
            "to near-zero frequency while holding interrupts."
        )
        confidence = 0.85 if call_trace else 0.65

    return WatchdogOutput(
        lockup_detected=True,
        lockup_type=lockup_type,
        cpu=cpu,
        pid=pid,
        process_name=process_name,
        stuck_duration_s=stuck_duration_s,
        call_trace=call_trace[:30],  # cap to 30 frames
        root_cause=root_cause,
        recommended_action=recommended_action,
        confidence=confidence,
    )
