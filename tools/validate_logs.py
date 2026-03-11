#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_logs.py
================
Local validator for the 28 log entries in LOG_PENDING_LIST.md.

Checks each log file against keyword/regex criteria derived from the
spec descriptions.  No LLM calls — entirely deterministic.

Usage
-----
    python tools/validate_logs.py [logs_validation_dir]

    Default dir: ./logs/validation

Output
------
Markdown report written to stdout.
A companion JSON summary is written to <logs_validation_dir>/validation_report.json.

Exit codes
----------
    0  all checks pass
    1  one or more FAIL / MISSING entries
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Check:
    """A single regex check applied to the full log text."""
    pattern: str
    description: str
    flags: int = re.IGNORECASE


@dataclass
class LogSpec:
    log_id: str
    filename: str               # canonical name from LOG_PENDING_LIST.md
    primary_skill: str
    required: list[Check] = field(default_factory=list)
    forbidden: list[Check] = field(default_factory=list)
    min_lines: int = 10
    max_lines: Optional[int] = None
    companion_files: list[str] = field(default_factory=list)  # must also exist
    alt_filenames: list[str] = field(default_factory=list)    # disk aliases


@dataclass
class FileResult:
    log_id: str
    canonical_filename: str
    found_filename: Optional[str]    # None = missing entirely
    status: str                      # PASS | FAIL | MISSING
    line_count: int = 0
    failed_required: list[str] = field(default_factory=list)
    failed_forbidden: list[str] = field(default_factory=list)
    line_count_issue: Optional[str] = None
    missing_companions: list[str] = field(default_factory=list)
    filename_mismatch: bool = False   # on-disk name differs from canonical


# ---------------------------------------------------------------------------
# Validation specs — one per LOG-NNN entry
# ---------------------------------------------------------------------------

SPECS: list[LogSpec] = [

    # ── Domain 0: Universal Triage ──────────────────────────────────────

    LogSpec(
        log_id="LOG-001",
        filename="d0_android_normal_boot.log",
        primary_skill="segment_boot_log",
        min_lines=100,
        required=[
            Check(r"\[\s*\d+\.\d+\]", "kernel timestamp present"),
            Check(
                r"android\.hardware|Zygote|SystemServer|sys\.boot_completed|ActivityManager|init\s+:",
                "Android-layer marker present",
            ),
        ],
        forbidden=[
            Check(r"NOTICE:\s+BL[123]|TF-A", "no TF-A early-boot markers"),
            Check(r"BUG: soft lockup|BUG: hard lockup|Kernel panic", "no panic in normal boot"),
        ],
    ),

    LogSpec(
        log_id="LOG-002",
        filename="d0_linux_kernel_only.log",
        primary_skill="segment_boot_log",
        min_lines=30,
        required=[
            Check(r"\[\s*0\.000000\]", "kernel timestamp from t=0"),
            Check(r"Linux version \d|Booting Linux|BusyBox|Freeing unused kernel", "Linux kernel marker"),
        ],
        forbidden=[
            Check(r"android\.hardware|Zygote|SystemServer|sys\.boot_completed", "no Android markers"),
            Check(r"NOTICE:\s+BL[123]", "no TF-A early-boot markers"),
        ],
    ),

    LogSpec(
        log_id="LOG-003",
        filename="d0_mixed_uart_kernel.log",
        primary_skill="segment_boot_log",
        min_lines=30,
        required=[
            Check(r"NOTICE:\s+BL[12]|INFO:\s+BL[12]|BL1:|BL2:", "TF-A stage marker"),
            Check(r"\[\s*0\.000000\]", "kernel timestamp also present"),
        ],
    ),

    LogSpec(
        log_id="LOG-004",
        filename="d0_unknown_fragment.log",
        primary_skill="segment_boot_log",
        min_lines=5,
        max_lines=50,
        forbidden=[
            Check(r"\[\s*0\.000000\]", "no kernel timestamp"),
            Check(r"NOTICE:\s+BL[123]|TF-A", "no TF-A markers"),
            Check(r"android\.hardware|Zygote|sys\.boot_completed", "no Android markers"),
        ],
    ),

    # ── Domain 1: Early Boot ─────────────────────────────────────────────

    LogSpec(
        log_id="LOG-005",
        filename="d1_tfa_auth_failure.log",
        primary_skill="parse_early_boot_uart_log",
        min_lines=10,
        required=[
            Check(r"NOTICE:\s+BL[12]|INFO:\s+BL[12]", "TF-A stage present"),
            Check(
                r"Authentication.*fail|auth.*fail|Failed to load image|ERROR.*BL31",
                "authentication / image load failure message",
            ),
            Check(r"ERROR:", "ERROR: line present"),
        ],
    ),

    LogSpec(
        log_id="LOG-006",
        filename="d1_lk_ddr_init_fail.log",
        primary_skill="parse_early_boot_uart_log",
        min_lines=10,
        required=[
            Check(
                r"ddr.*fail|ddr training fail|DRAM.*fail|PHY.*timed out|ddr_init failure",
                "DDR/DRAM initialisation failure",
            ),
            Check(r"PANIC|panic|CRASH|crash", "panic or crash line"),
        ],
    ),

    LogSpec(
        log_id="LOG-007",
        filename="d1_tfa_pmic_failure.log",
        primary_skill="parse_early_boot_uart_log",
        min_lines=10,
        required=[
            Check(r"NOTICE:\s+BL[123]|INFO:\s+BL[123]", "TF-A stage present"),
            Check(
                r"PMIC.*fail|pmic.*fail|regulator.*not ready|Failed.*rail|VDD.*fail",
                "PMIC / regulator failure",
            ),
            Check(r"ERROR:", "ERROR: line present"),
        ],
    ),

    LogSpec(
        log_id="LOG-008",
        filename="d1_lk_assert_arm32.log",
        primary_skill="analyze_lk_panic",
        min_lines=15,
        required=[
            Check(r"ASSERT FAILED|assert.*failed", "assert failure message"),
            Check(r"r0\s+0x|r1\s+0x|r14\s+0x|r15\s+0x", "ARM32 register dump (r0/r14/r15)"),
            Check(r"CRASH|panic", "crash / panic confirmation"),
        ],
        forbidden=[
            Check(r"x0\s+0x[0-9a-f]{8,}", "no AArch64 x0 register (ARM32 log)"),
        ],
    ),

    LogSpec(
        log_id="LOG-009",
        filename="d1_lk_panic_aarch64.log",
        primary_skill="analyze_lk_panic",
        min_lines=15,
        required=[
            Check(r"x0\s+0x|x1\s+0x|x29\s+0x|elr\s+0x", "AArch64 register dump (x0/x29/elr)"),
            Check(r"ESR\s+0x[0-9a-fA-F]+|ESR_EL[12]\s*=\s*0x", "ESR register value"),
            Check(r"CRASH|panic|data fault|abort", "crash / fault confirmation"),
        ],
        forbidden=[
            Check(r"r0\s+0x[0-9a-f]+\s+r1\s+0x", "no ARM32 register format in AArch64 log"),
        ],
    ),

    # ── Domain 2: Kernel Pathologist ────────────────────────────────────

    LogSpec(
        log_id="LOG-010",
        filename="d2_qemu_null_pointer.log",
        primary_skill="extract_kernel_oops_log",
        min_lines=20,
        required=[
            Check(
                r"data fault|Unable to handle kernel NULL|NULL pointer|null pointer dereference|Oops|CRASH.*panic",
                "null pointer / data fault / oops indication",
            ),
            Check(r"FAR\s+0x[0-9a-fA-F]+|FAR_EL1\s*=|far\s+0x", "Fault Address Register"),
            Check(r"ESR\s+0x[0-9a-fA-F]+|ESR_EL1\s*=", "ESR register value"),
        ],
    ),

    LogSpec(
        log_id="LOG-011",
        filename="d2_aarch64_null_ptr.log",
        primary_skill="extract_kernel_oops_log + decode_aarch64_exception",
        min_lines=20,
        required=[
            Check(r"Unable to handle kernel NULL pointer", "null pointer header line"),
            # Kernel prints either 'ESR_EL1 = 0x...' (older) or '  ESR = 0x...' (mem_abort_info)
            Check(r"ESR_EL1\s*=\s*0x[0-9a-fA-F]+|ESR\s*=\s*0x[0-9a-fA-F]+", "ESR register"),
            Check(r"Internal error: Oops", "Oops confirmation line"),
            Check(r"pc\s*:\s*\S+\+0x|pc\s+:\s+\S+|Call trace:|call trace", "pc symbol or call trace"),
        ],
    ),

    LogSpec(
        log_id="LOG-012",
        filename="d2_aarch64_paging_request.log",
        primary_skill="extract_kernel_oops_log + decode_aarch64_exception",
        min_lines=20,
        required=[
            Check(r"Unable to handle kernel paging request", "paging request header"),
            # Kernel prints either 'ESR_EL1 = 0x...' (older) or '  ESR = 0x...' (mem_abort_info)
            Check(r"ESR_EL1\s*=\s*0x[0-9a-fA-F]+|ESR\s*=\s*0x[0-9a-fA-F]+", "ESR register"),
            Check(r"ffff[0-9a-fA-F]{12}", "kernel VA (0xffff...) in FAR"),
        ],
    ),

    LogSpec(
        log_id="LOG-013",
        filename="d2_serror_interrupt.log",
        primary_skill="decode_esr_el1 + check_cache_coherency_panic",
        min_lines=20,
        required=[
            Check(r"SError Interrupt|SError interrupt|Internal error.*SError", "SError message"),
            Check(r"ESR_EL1\s*=\s*0x[0-9a-fA-F]+", "ESR_EL1 register"),
        ],
    ),

    LogSpec(
        log_id="LOG-014",
        filename="d2_soft_lockup.log",
        primary_skill="analyze_watchdog_timeout",
        min_lines=15,
        required=[
            Check(r"BUG: soft lockup", "soft lockup header"),
            Check(r"CPU#\d+\s+stuck for \d+s!", "stuck duration line"),
            Check(r"kworker|swapper|migration|ksoftirqd|\[[\w/:.]+\]", "process name"),
        ],
        forbidden=[
            Check(r"BUG: hard lockup|hard LOCKUP|Watchdog detected hard LOCKUP", "not a hard lockup log"),
        ],
    ),

    LogSpec(
        log_id="LOG-015",
        filename="d2_hard_lockup.log",
        primary_skill="analyze_watchdog_timeout",
        min_lines=15,
        required=[
            Check(r"BUG: hard lockup|hard LOCKUP|Watchdog detected hard LOCKUP", "hard lockup header"),
            Check(r"cpu\s*\d+|CPU#\d+", "CPU number"),
            Check(r"stuck for \d+s!|60s", "stuck duration"),
        ],
        forbidden=[
            Check(r"^.*BUG: soft lockup", "not a soft lockup log"),
        ],
    ),

    LogSpec(
        log_id="LOG-016",
        filename="d2_rcu_stall.log",
        primary_skill="analyze_watchdog_timeout",
        min_lines=10,
        required=[
            Check(r"rcu.*detected stall|rcu_sched.*stall|INFO: rcu", "RCU stall message"),
        ],
        forbidden=[
            Check(r"BUG: soft lockup|BUG: hard lockup", "not a lockup log"),
        ],
    ),

    LogSpec(
        log_id="LOG-017",
        filename="d2_watchdog_serror_combined.log",
        primary_skill="analyze_watchdog_timeout + decode_esr_el1 (synergy)",
        min_lines=20,
        required=[
            Check(r"BUG: soft lockup|BUG: hard lockup", "watchdog event"),
            Check(r"SError Interrupt|SError interrupt|ESR_EL1\s*=", "concurrent SError / ESR"),
        ],
    ),

    # ── Domain 3: Hardware Advisor ───────────────────────────────────────

    LogSpec(
        log_id="LOG-018",
        filename="d3_std_high_sunreclaim.log",
        primary_skill="analyze_std_hibernation_error",
        min_lines=10,
        companion_files=["d3_std_high_sunreclaim.meminfo"],
        required=[
            Check(r"Error -12 creating hibernation image|PM: Error -12", "hibernation error -12"),
        ],
    ),

    LogSpec(
        log_id="LOG-018-meminfo",
        filename="d3_std_high_sunreclaim.meminfo",
        primary_skill="analyze_std_hibernation_error (companion)",
        min_lines=5,
        required=[
            Check(r"SUnreclaim:\s+\d+ kB", "SUnreclaim field"),
            Check(r"SwapFree:\s+\d+ kB", "SwapFree field"),
        ],
    ),

    LogSpec(
        log_id="LOG-019",
        filename="d3_std_swap_exhausted.log",
        primary_skill="analyze_std_hibernation_error",
        min_lines=10,
        companion_files=["d3_std_swap_exhausted.meminfo"],
        required=[
            Check(r"Error -12 creating hibernation image|PM: Error -12", "hibernation error -12"),
        ],
    ),

    LogSpec(
        log_id="LOG-019-meminfo",
        filename="d3_std_swap_exhausted.meminfo",
        primary_skill="analyze_std_hibernation_error (companion)",
        min_lines=5,
        required=[
            Check(r"SwapFree:\s+0 kB", "SwapFree is 0 (exhausted)"),
            Check(r"SUnreclaim:\s+\d+ kB", "SUnreclaim field"),
        ],
    ),

    LogSpec(
        log_id="LOG-020",
        filename="d3_ufs_probe_fail.log",
        primary_skill="check_vendor_boot_ufs_driver",
        min_lines=10,
        required=[
            Check(r"probe of .* failed|ufshcd.*probe.*failed", "UFS probe failure"),
            Check(r"ufshcd|ufshc", "ufshcd driver reference"),
        ],
        forbidden=[
            Check(r"ufshcd_link_startup failed", "no link_startup failure (probe-only log)"),
        ],
    ),

    LogSpec(
        log_id="LOG-021",
        filename="d3_ufs_link_startup_fail.log",
        primary_skill="check_vendor_boot_ufs_driver",
        min_lines=10,
        required=[
            Check(r"ufshcd_link_startup failed|link_startup.*failed|link startup failed", "UFS link_startup failure"),
            Check(r"ufshcd|ufshc", "ufshcd driver reference"),
        ],
        forbidden=[
            Check(r"probe of .* failed with error", "no probe failure (link_startup-only log)"),
        ],
    ),

    LogSpec(
        log_id="LOG-022",
        filename="d3_pmic_ocp_display.log",
        primary_skill="check_pmic_rail_voltage",
        min_lines=10,
        required=[
            Check(r"over-current|overcurrent|OCP", "OCP / over-current event"),
            Check(r"qpnp|vreg_lcd|vreg", "PMIC rail name"),
        ],
        forbidden=[
            Check(r"below minimum|under-voltage|undervoltage detected", "no undervoltage (OCP-only log)"),
        ],
    ),

    LogSpec(
        log_id="LOG-023",
        filename="d3_pmic_undervoltage_cpu.log",
        primary_skill="check_pmic_rail_voltage",
        min_lines=10,
        required=[
            Check(r"under-voltage|undervoltage|below minimum|set_voltage failed", "undervoltage event"),
            Check(r"rpm-smd|s1a|regulator", "PMIC rail reference"),
        ],
        forbidden=[
            Check(r"over-current|overcurrent", "no OCP (undervoltage-only log)"),
        ],
    ),

    LogSpec(
        log_id="LOG-024",
        filename="d3_pmic_clean_boot.log",
        primary_skill="check_pmic_rail_voltage (negative)",
        min_lines=20,
        forbidden=[
            Check(r"over-current|overcurrent|OCP", "no OCP events"),
            Check(r"under-voltage|undervoltage|below minimum", "no undervoltage events"),
        ],
    ),

    # ── Domain 4: Routing / End-to-End ──────────────────────────────────

    LogSpec(
        log_id="LOG-025",
        filename="d4_ambiguous_ufs_kernel.log",
        primary_skill="supervisor routing stress test",
        min_lines=20,
        required=[
            Check(r"ufshcd.*probe.*failed|probe of.*ufshc.*failed", "UFS probe failure"),
            Check(
                r"BUG: soft lockup|Internal error: Oops|Unable to handle",
                "concurrent kernel error",
            ),
        ],
    ),

    LogSpec(
        log_id="LOG-026",
        filename="d4_early_boot_healthy.log",
        primary_skill="parse_early_boot_uart_log (negative)",
        min_lines=20,
        required=[
            Check(
                r"NOTICE:.*BL[123]|welcome to lk|entering main console|lk/MP|initializing apps",
                "bootloader / LK healthy-boot marker",
            ),
        ],
        forbidden=[
            Check(r"ERROR:.*BL|ASSERT FAILED|Authentication.*fail|ddr.*fail|PMIC.*fail", "no fatal error"),
        ],
    ),

    LogSpec(
        log_id="LOG-027",
        filename="d4_android_selinux_avc.log",
        primary_skill="segment_boot_log + Phase 6 preview",
        min_lines=50,
        required=[
            Check(r"avc:\s*denied", "AVC denial line"),
            Check(r"\[\s*\d+\.\d+\]|logcat|Android", "Android / kernel context"),
        ],
    ),

    LogSpec(
        log_id="LOG-028",
        filename="d4_android_slow_boot.log",
        primary_skill="segment_boot_log (slow boot timing baseline)",
        min_lines=100,
        required=[
            Check(r"\[\s*\d+\.\d+\]", "kernel timestamp"),
            Check(
                r"android\.hardware|Zygote|SystemServer|sys\.boot_completed|Android Boot Log",
                "Android marker",
            ),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

def validate_spec(spec: LogSpec, logs_dir: Path) -> FileResult:
    canonical = spec.filename
    result = FileResult(
        log_id=spec.log_id,
        canonical_filename=canonical,
        found_filename=None,
        status="MISSING",
    )

    # Resolve file on disk: try canonical name first, then alt names
    resolved: Optional[Path] = None
    for name in [canonical] + spec.alt_filenames:
        candidate = logs_dir / name
        if candidate.exists():
            resolved = candidate
            if name != canonical:
                result.filename_mismatch = True
            result.found_filename = name
            break

    if resolved is None:
        return result

    # Read content
    text = resolved.read_text(errors="replace")
    lines = text.splitlines()
    result.line_count = len(lines)

    # Line count checks
    if result.line_count < spec.min_lines:
        result.line_count_issue = (
            f"too few lines: {result.line_count} < {spec.min_lines} minimum"
        )
    if spec.max_lines is not None and result.line_count > spec.max_lines:
        result.line_count_issue = (
            f"too many lines: {result.line_count} > {spec.max_lines} maximum"
        )

    # Required pattern checks
    for check in spec.required:
        if not re.search(check.pattern, text, check.flags):
            result.failed_required.append(
                f"MISSING `{check.pattern}` — {check.description}"
            )

    # Forbidden pattern checks
    for check in spec.forbidden:
        m = re.search(check.pattern, text, check.flags)
        if m:
            snippet = m.group(0)[:60].replace("\n", " ")
            result.failed_forbidden.append(
                f"FOUND `{check.pattern}` — {check.description} (found: '{snippet}')"
            )

    # Companion file checks
    for companion in spec.companion_files:
        if not (logs_dir / companion).exists():
            result.missing_companions.append(companion)

    # Determine overall status
    failures = (
        result.failed_required
        + result.failed_forbidden
        + result.missing_companions
        + ([result.line_count_issue] if result.line_count_issue else [])
    )
    result.status = "FAIL" if failures else "PASS"

    return result


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

STATUS_ICON = {"PASS": "✅", "FAIL": "❌", "MISSING": "⚠️"}


def render_markdown(results: list[FileResult]) -> str:
    lines: list[str] = []

    # Header
    lines += [
        "# Log Validation Report",
        "",
        f"Validated {len(results)} entries against LOG_PENDING_LIST.md specs.",
        "",
    ]

    # Summary counts
    counts = {s: sum(1 for r in results if r.status == s) for s in ("PASS", "FAIL", "MISSING")}
    lines += [
        "## Summary",
        "",
        f"| Status | Count |",
        f"|--------|-------|",
        f"| ✅ PASS    | {counts['PASS']} |",
        f"| ❌ FAIL    | {counts['FAIL']} |",
        f"| ⚠️  MISSING | {counts['MISSING']} |",
        "",
    ]

    # Summary table
    lines += [
        "## Results Table",
        "",
        "| ID | File | Lines | Status | Issues |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        icon = STATUS_ICON.get(r.status, r.status)
        fname = r.found_filename or r.canonical_filename
        mismatch_note = " ⚠️ filename mismatch" if r.filename_mismatch else ""
        if r.status == "MISSING":
            issue_summary = "file not found"
        else:
            n = (
                len(r.failed_required)
                + len(r.failed_forbidden)
                + len(r.missing_companions)
                + (1 if r.line_count_issue else 0)
            )
            issue_summary = f"{n} issue(s)" if n else "—"
        lines.append(
            f"| {r.log_id} | `{fname}`{mismatch_note} | {r.line_count} | {icon} {r.status} | {issue_summary} |"
        )

    lines.append("")

    # Detailed findings for non-PASS entries
    problem_results = [r for r in results if r.status != "PASS"]
    if problem_results:
        lines += ["## Detailed Findings", ""]
        for r in problem_results:
            icon = STATUS_ICON.get(r.status, r.status)
            lines += [f"### {icon} {r.log_id} — `{r.canonical_filename}`", ""]

            if r.status == "MISSING":
                lines += [
                    f"**File not found.** Expected at `logs/validation/{r.canonical_filename}`.",
                    "",
                ]
                continue

            if r.filename_mismatch:
                lines += [
                    f"**Filename mismatch:** LOG_PENDING_LIST.md specifies `{r.canonical_filename}` "
                    f"but file found as `{r.found_filename}`. "
                    f"Update the spec filename or rename the file.",
                    "",
                ]

            if r.line_count_issue:
                lines += [f"- **Line count:** {r.line_count_issue}", ""]

            for msg in r.failed_required:
                lines.append(f"- **Required pattern absent:** {msg}")
            for msg in r.failed_forbidden:
                lines.append(f"- **Forbidden pattern found:** {msg}")
            for companion in r.missing_companions:
                lines.append(f"- **Missing companion file:** `{companion}`")

            lines.append("")
    else:
        lines += ["## Detailed Findings", "", "All checks passed — no issues to report.", ""]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    logs_dir = Path(argv[1]) if len(argv) > 1 else Path("logs/validation")

    if not logs_dir.exists():
        print(f"ERROR: directory not found: {logs_dir}", file=sys.stderr)
        return 1

    results = [validate_spec(spec, logs_dir) for spec in SPECS]

    # Markdown to stdout
    print(render_markdown(results))

    # JSON summary alongside the logs
    json_path = logs_dir / "validation_report.json"
    report_data = [
        {
            "log_id": r.log_id,
            "canonical_filename": r.canonical_filename,
            "found_filename": r.found_filename,
            "status": r.status,
            "line_count": r.line_count,
            "filename_mismatch": r.filename_mismatch,
            "failed_required": r.failed_required,
            "failed_forbidden": r.failed_forbidden,
            "line_count_issue": r.line_count_issue,
            "missing_companions": r.missing_companions,
        }
        for r in results
    ]
    json_path.write_text(json.dumps(report_data, indent=2))
    print(f"\n<!-- JSON report written to {json_path} -->", file=sys.stderr)

    return 0 if all(r.status == "PASS" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
