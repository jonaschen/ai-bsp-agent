"""
Kernel Oops Diagnostic Skill.

Provides one deterministic tool for the Kernel Pathologist domain:
  - extract_kernel_oops_log: parse a kernel Oops or BUG report from dmesg,
    extracting the fault type, faulting process/PID, ESR_EL1, FAR_EL1,
    pc/lr symbols, and call trace.

Domain: Android BSP / Kernel Pathologist
Reference: Linux kernel Documentation/admin-guide/bug-hunting.rst
"""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class KernelOopsInput(BaseModel):
    dmesg_log: str = Field(
        ...,
        description=(
            "Raw kernel dmesg or panic log. May contain 'Unable to handle kernel', "
            "'Internal error: Oops:', or 'kernel BUG at' messages."
        ),
    )


class KernelOopsOutput(BaseModel):
    oops_detected: bool = Field(
        ..., description="True if a kernel Oops or BUG was found in the log"
    )
    oops_type: str = Field(
        ..., description="Classified Oops type: 'null_pointer', 'paging_request', 'kernel_bug', 'generic_oops', or 'none'"
    )
    faulting_process: Optional[str] = Field(
        None, description="Name of the process that caused the Oops (from 'Comm:' field)"
    )
    faulting_pid: Optional[int] = Field(
        None, description="PID of the faulting process"
    )
    cpu_number: Optional[int] = Field(
        None, description="CPU number where the Oops occurred"
    )
    kernel_version: Optional[str] = Field(
        None, description="Kernel version string from the Oops header"
    )
    esr_el1_hex: Optional[str] = Field(
        None, description="ESR_EL1 hex value extracted from the log (pass to decode_esr_el1)"
    )
    far_hex: Optional[str] = Field(
        None, description="FAR_EL1 hex value extracted from the log (fault address)"
    )
    pc_symbol: Optional[str] = Field(
        None, description="Program counter symbol at the time of the fault (e.g. 'mydriver_probe+0x234/0x400')"
    )
    lr_symbol: Optional[str] = Field(
        None, description="Link register symbol at the time of the fault"
    )
    call_trace: list[str] = Field(
        ..., description="Call trace entries extracted from the Oops (symbol+offset/size strings)"
    )
    first_oops_line: Optional[str] = Field(
        None, description="First log line that triggered Oops detection"
    )
    confidence: float = Field(..., ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Detection patterns
# ---------------------------------------------------------------------------

# Oops trigger lines
_NULL_PTR_RE = re.compile(
    r"Unable to handle kernel NULL pointer dereference", re.IGNORECASE
)
_PAGING_RE = re.compile(
    r"Unable to handle kernel paging request", re.IGNORECASE
)
_KERNEL_BUG_RE = re.compile(
    r"kernel BUG at\s+\S+:\d+", re.IGNORECASE
)
_OOPS_INTERNAL_RE = re.compile(
    r"Internal error:\s+Oops", re.IGNORECASE
)

# Process / CPU / kernel info
_CPU_PID_RE = re.compile(
    r"CPU:\s*(\d+)\s+PID:\s*(\d+)\s+Comm:\s*(\S+)", re.IGNORECASE
)
_KERNEL_VERSION_RE = re.compile(
    r"(?:Not tainted|Tainted:)\s+(\S+)", re.IGNORECASE
)

# Register extraction
_ESR_RE = re.compile(r"ESR(?:_EL1)?\s*[=:]\s*(0x[0-9a-fA-F]+)", re.IGNORECASE)
_FAR_RE = re.compile(r"FAR_EL1\s*[=:]\s*(0x[0-9a-fA-F]+)", re.IGNORECASE)
_TS_PREFIX = r"(?:\[\s*\d+\.\d+\]\s*)?"  # optional kernel timestamp

_PC_RE = re.compile(rf"^{_TS_PREFIX}\s*pc\s*:\s*(\S+)", re.MULTILINE)
_LR_RE = re.compile(rf"^{_TS_PREFIX}\s*lr\s*:\s*(\S+)", re.MULTILINE)

# Call trace — lines like "  function_name+0xNN/0xNN" after "Call trace:" or "Call Trace:"
_CALL_TRACE_HEADER_RE = re.compile(r"Call\s+[Tt]race\s*:", re.IGNORECASE)
_CALL_TRACE_ENTRY_RE = re.compile(
    rf"^{_TS_PREFIX}\s+(\w[\w.:/+-]+\+0x[0-9a-fA-F]+/0x[0-9a-fA-F]+)"
)


# ---------------------------------------------------------------------------
# Skill function
# ---------------------------------------------------------------------------

def extract_kernel_oops_log(dmesg_log: str) -> KernelOopsOutput:
    """
    Parse a kernel Oops or BUG report from a dmesg log.

    Detects 'Unable to handle kernel NULL pointer dereference',
    'Unable to handle kernel paging request', 'kernel BUG at', and
    'Internal error: Oops' messages. Extracts the faulting process,
    PID, CPU number, ESR_EL1, FAR_EL1, pc/lr symbols, and call trace.

    The extracted esr_el1_hex can be passed directly to decode_esr_el1()
    or decode_aarch64_exception() for full register decoding.

    Args:
        dmesg_log: Raw kernel dmesg or panic log.

    Returns:
        KernelOopsOutput with detection result and extracted fields.
    """
    if not dmesg_log.strip():
        return KernelOopsOutput(
            oops_detected=False,
            oops_type="none",
            call_trace=[],
            confidence=0.85,
        )

    # --- Oops type detection (priority order) ---
    first_oops_line: Optional[str] = None
    oops_type = "none"

    for line in dmesg_log.splitlines():
        stripped = line.strip()
        if _NULL_PTR_RE.search(stripped):
            oops_type = "null_pointer"
            first_oops_line = stripped
            break
        if _PAGING_RE.search(stripped):
            oops_type = "paging_request"
            first_oops_line = stripped
            break
        if _KERNEL_BUG_RE.search(stripped):
            oops_type = "kernel_bug"
            first_oops_line = stripped
            break

    # Internal error: Oops as fallback trigger (may appear even without the above)
    if oops_type == "none":
        for line in dmesg_log.splitlines():
            if _OOPS_INTERNAL_RE.search(line):
                oops_type = "generic_oops"
                first_oops_line = line.strip()
                break

    oops_detected = oops_type != "none"

    if not oops_detected:
        return KernelOopsOutput(
            oops_detected=False,
            oops_type="none",
            call_trace=[],
            confidence=0.88,
        )

    # --- CPU, PID, process name ---
    cpu_number: Optional[int] = None
    faulting_pid: Optional[int] = None
    faulting_process: Optional[str] = None
    cpu_pid_match = _CPU_PID_RE.search(dmesg_log)
    if cpu_pid_match:
        cpu_number = int(cpu_pid_match.group(1))
        faulting_pid = int(cpu_pid_match.group(2))
        faulting_process = cpu_pid_match.group(3)

    # --- Kernel version ---
    kernel_version: Optional[str] = None
    kv_match = _KERNEL_VERSION_RE.search(dmesg_log)
    if kv_match:
        kernel_version = kv_match.group(1)

    # --- ESR_EL1 and FAR ---
    esr_el1_hex: Optional[str] = None
    esr_match = _ESR_RE.search(dmesg_log)
    if esr_match:
        esr_el1_hex = esr_match.group(1)

    far_hex: Optional[str] = None
    far_match = _FAR_RE.search(dmesg_log)
    if far_match:
        far_hex = far_match.group(1)

    # --- pc / lr symbols ---
    pc_symbol: Optional[str] = None
    pc_match = _PC_RE.search(dmesg_log)
    if pc_match:
        pc_symbol = pc_match.group(1)

    lr_symbol: Optional[str] = None
    lr_match = _LR_RE.search(dmesg_log)
    if lr_match:
        lr_symbol = lr_match.group(1)

    # --- Call trace ---
    call_trace: list[str] = []
    in_trace = False
    for line in dmesg_log.splitlines():
        if _CALL_TRACE_HEADER_RE.search(line):
            in_trace = True
            continue
        if in_trace:
            m = _CALL_TRACE_ENTRY_RE.match(line)
            if m:
                call_trace.append(m.group(1))
            elif not line.strip() or re.search(r"^\[[\s\d.]+\]\s*$", line):
                # Blank or timestamp-only line — skip but continue
                continue
            elif re.search(r"^\[[\s\d.]+\]", line):
                # Timestamped content line that didn't match entry — keep scanning
                continue
            else:
                # Non-timestamped, non-entry line — end of trace
                break
    # Cap at 32 entries to avoid oversized outputs
    call_trace = call_trace[:32]

    # Confidence: higher when we have ESR + call trace
    base = 0.75
    if esr_el1_hex:
        base += 0.10
    if call_trace:
        base += 0.05
    confidence = min(base, 0.95)

    return KernelOopsOutput(
        oops_detected=True,
        oops_type=oops_type,
        faulting_process=faulting_process,
        faulting_pid=faulting_pid,
        cpu_number=cpu_number,
        kernel_version=kernel_version,
        esr_el1_hex=esr_el1_hex,
        far_hex=far_hex,
        pc_symbol=pc_symbol,
        lr_symbol=lr_symbol,
        call_trace=call_trace,
        first_oops_line=first_oops_line,
        confidence=confidence,
    )
