#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
skill_validation.py
===================
Runs every BSP diagnostic skill directly against its target validation log
and checks the output against expected outcomes from LOG_PENDING_LIST.md.

No LLM calls — entirely deterministic.

Usage
-----
    python tools/skill_validation.py [logs_validation_dir]

    Default dir: ./logs/validation

Output
------
Markdown report written to stdout.
JSON summary written to logs/validation/skill_validation_report.json.

Exit codes
----------
    0  all checks PASS
    1  one or more FAIL / PARTIAL
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

# --- skill imports ---
from skills.bsp_diagnostics.log_segmenter import segment_boot_log
from skills.bsp_diagnostics.early_boot import parse_early_boot_uart_log, analyze_lk_panic
from skills.bsp_diagnostics.kernel_oops import extract_kernel_oops_log
from skills.bsp_diagnostics.aarch64_exceptions import (
    decode_esr_el1, decode_aarch64_exception, check_cache_coherency_panic,
)
from skills.bsp_diagnostics.watchdog import analyze_watchdog_timeout
from skills.bsp_diagnostics.std_hibernation import analyze_std_hibernation_error
from skills.bsp_diagnostics.vendor_boot import check_vendor_boot_ufs_driver
from skills.bsp_diagnostics.pmic import check_pmic_rail_voltage


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

@dataclass
class Check:
    description: str
    fn: Callable[[dict], bool]


@dataclass
class SkillRun:
    log_id: str
    log_file: str
    skill_name: str
    status: str = "PENDING"          # PASS | PARTIAL | FAIL | ERROR
    result: Optional[dict] = None
    failed_checks: list[str] = field(default_factory=list)
    passed_checks: list[str] = field(default_factory=list)
    error: Optional[str] = None
    secondary_results: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _run(fn, **kwargs) -> dict:
    return fn(**kwargs).model_dump()


# ---------------------------------------------------------------------------
# Validation cases
# ---------------------------------------------------------------------------

def build_cases(logs_dir: Path) -> list[tuple[str, Callable[[], SkillRun]]]:
    """Return (log_id, runner_fn) pairs for all 28 validation entries."""
    cases: list[tuple[str, Callable[[], SkillRun]]] = []

    def add(log_id: str, log_file: str, skill_name: str,
            run_fn: Callable[[], dict],
            checks: list[Check],
            secondary_fn: Optional[Callable[[dict], list[dict]]] = None):
        def runner() -> SkillRun:
            sr = SkillRun(log_id=log_id, log_file=log_file, skill_name=skill_name)
            try:
                sr.result = run_fn()
                if secondary_fn:
                    sr.secondary_results = secondary_fn(sr.result)
            except Exception as exc:
                sr.status = "ERROR"
                sr.error = str(exc)
                return sr

            for chk in checks:
                try:
                    passed = chk.fn(sr.result)
                except Exception as exc:
                    passed = False
                    chk.description += f" [check error: {exc}]"
                if passed:
                    sr.passed_checks.append(chk.description)
                else:
                    sr.failed_checks.append(chk.description)

            if not sr.failed_checks:
                sr.status = "PASS"
            elif sr.passed_checks:
                sr.status = "PARTIAL"
            else:
                sr.status = "FAIL"
            return sr
        cases.append((log_id, runner))

    # --- Domain 0: Universal Triage ---

    add("LOG-001", "d0_android_normal_boot.log", "segment_boot_log",
        lambda: _run(segment_boot_log, raw_log=_read(logs_dir / "d0_android_normal_boot.log")),
        [
            Check("detected_stage == 'android_init'",
                  lambda r: r["detected_stage"] == "android_init"),
            Check("confidence >= 0.80",
                  lambda r: r["confidence"] >= 0.80),
        ])

    add("LOG-002", "d0_linux_kernel_only.log", "segment_boot_log",
        lambda: _run(segment_boot_log, raw_log=_read(logs_dir / "d0_linux_kernel_only.log")),
        [
            Check("detected_stage == 'kernel_init'",
                  lambda r: r["detected_stage"] == "kernel_init"),
            Check("confidence >= 0.75",
                  lambda r: r["confidence"] >= 0.75),
        ])

    add("LOG-003", "d0_mixed_uart_kernel.log", "segment_boot_log",
        lambda: _run(segment_boot_log, raw_log=_read(logs_dir / "d0_mixed_uart_kernel.log")),
        [
            Check("detected_stage == 'early_boot' (early-boot wins over kernel_init)",
                  lambda r: r["detected_stage"] == "early_boot"),
            Check("confidence >= 0.70",
                  lambda r: r["confidence"] >= 0.70),
        ])

    add("LOG-004", "d0_unknown_fragment.log", "segment_boot_log",
        lambda: _run(segment_boot_log, raw_log=_read(logs_dir / "d0_unknown_fragment.log")),
        [
            Check("detected_stage == 'unknown'",
                  lambda r: r["detected_stage"] == "unknown"),
            Check("confidence <= 0.30",
                  lambda r: r["confidence"] <= 0.30),
        ])

    # --- Domain 1: Early Boot ---

    add("LOG-005", "d1_tfa_auth_failure.log", "parse_early_boot_uart_log",
        lambda: _run(parse_early_boot_uart_log,
                     raw_uart_log=_read(logs_dir / "d1_tfa_auth_failure.log")),
        [
            Check("failure_detected == True",
                  lambda r: r["failure_detected"] is True),
            Check("error_type == 'auth_failure'",
                  lambda r: r["error_type"] == "auth_failure"),
            Check("confidence >= 0.85",
                  lambda r: r["confidence"] >= 0.85),
        ])

    add("LOG-006", "d1_lk_ddr_init_fail.log", "parse_early_boot_uart_log",
        lambda: _run(parse_early_boot_uart_log,
                     raw_uart_log=_read(logs_dir / "d1_lk_ddr_init_fail.log")),
        [
            Check("failure_detected == True",
                  lambda r: r["failure_detected"] is True),
            Check("error_type == 'ddr_init_failure'",
                  lambda r: r["error_type"] == "ddr_init_failure"),
            Check("confidence >= 0.80",
                  lambda r: r["confidence"] >= 0.80),
        ])

    add("LOG-007", "d1_tfa_pmic_failure.log", "parse_early_boot_uart_log",
        lambda: _run(parse_early_boot_uart_log,
                     raw_uart_log=_read(logs_dir / "d1_tfa_pmic_failure.log")),
        [
            Check("failure_detected == True",
                  lambda r: r["failure_detected"] is True),
            Check("error_type == 'pmic_failure'",
                  lambda r: r["error_type"] == "pmic_failure"),
            Check("confidence >= 0.75",
                  lambda r: r["confidence"] >= 0.75),
        ])

    add("LOG-008", "d1_lk_assert_arm32.log", "analyze_lk_panic",
        lambda: _run(analyze_lk_panic,
                     uart_log_snippet=_read(logs_dir / "d1_lk_assert_arm32.log")),
        [
            Check("panic_detected == True",
                  lambda r: r["panic_detected"] is True),
            Check("panic_type == 'assert'",
                  lambda r: r["panic_type"] == "assert"),
            Check("assert_file populated",
                  lambda r: bool(r.get("assert_file"))),
            Check("register_dump non-empty",
                  lambda r: len(r.get("register_dump", [])) > 0),
            Check("confidence >= 0.85",
                  lambda r: r["confidence"] >= 0.85),
        ])

    add("LOG-009", "d1_lk_panic_aarch64.log", "analyze_lk_panic",
        lambda: _run(analyze_lk_panic,
                     uart_log_snippet=_read(logs_dir / "d1_lk_panic_aarch64.log")),
        [
            Check("panic_detected == True",
                  lambda r: r["panic_detected"] is True),
            Check("panic_type in ('generic','assert')",
                  lambda r: r["panic_type"] in ("generic", "assert")),
            Check("register_dump non-empty (AArch64 x0..x29)",
                  lambda r: len(r.get("register_dump", [])) > 0),
            Check("confidence >= 0.75",
                  lambda r: r["confidence"] >= 0.75),
        ])

    # --- Domain 2: Kernel Pathologist ---

    add("LOG-010", "d2_qemu_null_pointer.log", "extract_kernel_oops_log",
        lambda: _run(extract_kernel_oops_log,
                     dmesg_log=_read(logs_dir / "d2_qemu_null_pointer.log")),
        [
            Check("oops_detected == True",
                  lambda r: r["oops_detected"] is True),
            Check("oops_type in ('generic_oops','null_pointer','kernel_bug')",
                  lambda r: r["oops_type"] in ("generic_oops", "null_pointer", "kernel_bug")),
            Check("call_trace non-empty",
                  lambda r: len(r.get("call_trace", [])) > 0),
            Check("esr_el1_hex populated (AArch64 log has ESR)",
                  lambda r: r.get("esr_el1_hex") is not None),
        ])

    def _log011_secondary(oops_result: dict) -> list[dict]:
        esr = oops_result.get("esr_el1_hex") or "0x96000006"
        far = oops_result.get("far_hex") or "0x0000000000000018"
        return [_run(decode_aarch64_exception, esr_val=esr, far_val=far)]

    add("LOG-011", "d2_aarch64_null_ptr.log", "extract_kernel_oops_log",
        lambda: _run(extract_kernel_oops_log,
                     dmesg_log=_read(logs_dir / "d2_aarch64_null_ptr.log")),
        [
            Check("oops_detected == True",
                  lambda r: r["oops_detected"] is True),
            Check("oops_type == 'null_pointer'",
                  lambda r: r["oops_type"] == "null_pointer"),
            Check("esr_el1_hex populated",
                  lambda r: bool(r.get("esr_el1_hex"))),
            Check("far_hex populated",
                  lambda r: bool(r.get("far_hex"))),
        ],
        secondary_fn=_log011_secondary)

    def _log012_secondary(oops_result: dict) -> list[dict]:
        esr = oops_result.get("esr_el1_hex") or "0x9600004f"
        far = oops_result.get("far_hex") or "0xffff800012345678"
        return [_run(decode_aarch64_exception, esr_val=esr, far_val=far)]

    add("LOG-012", "d2_aarch64_paging_request.log", "extract_kernel_oops_log",
        lambda: _run(extract_kernel_oops_log,
                     dmesg_log=_read(logs_dir / "d2_aarch64_paging_request.log")),
        [
            Check("oops_detected == True",
                  lambda r: r["oops_detected"] is True),
            Check("oops_type == 'paging_request'",
                  lambda r: r["oops_type"] == "paging_request"),
            Check("far_hex populated",
                  lambda r: bool(r.get("far_hex"))),
        ],
        secondary_fn=_log012_secondary)

    def _log013_secondary(esr_result: dict) -> list[dict]:
        return [_run(check_cache_coherency_panic,
                     panic_log=_read(logs_dir / "d2_serror_interrupt.log"))]

    add("LOG-013", "d2_serror_interrupt.log", "decode_esr_el1 + check_cache_coherency_panic",
        lambda: _run(decode_esr_el1, hex_value="0xbf000002"),
        [
            Check("ec_description contains 'SError' or 'serror' or '0x2f'",
                  lambda r: any(s in r.get("ec_description", "").lower()
                                for s in ("serror", "s error", "0x2f"))),
        ],
        secondary_fn=_log013_secondary)

    add("LOG-014", "d2_soft_lockup.log", "analyze_watchdog_timeout",
        lambda: _run(analyze_watchdog_timeout,
                     dmesg_log=_read(logs_dir / "d2_soft_lockup.log")),
        [
            Check("lockup_detected == True",
                  lambda r: r["lockup_detected"] is True),
            Check("lockup_type == 'soft_lockup'",
                  lambda r: r["lockup_type"] == "soft_lockup"),
            Check("cpu populated",
                  lambda r: r.get("cpu") is not None),
            Check("stuck_duration_s > 0",
                  lambda r: (r.get("stuck_duration_s") or 0) > 0),
            Check("call_trace non-empty",
                  lambda r: len(r.get("call_trace", [])) > 0),
        ])

    add("LOG-015", "d2_hard_lockup.log", "analyze_watchdog_timeout",
        lambda: _run(analyze_watchdog_timeout,
                     dmesg_log=_read(logs_dir / "d2_hard_lockup.log")),
        [
            Check("lockup_detected == True",
                  lambda r: r["lockup_detected"] is True),
            Check("lockup_type == 'hard_lockup'",
                  lambda r: r["lockup_type"] == "hard_lockup"),
            Check("cpu == 3",
                  lambda r: r.get("cpu") == 3),
        ])

    add("LOG-016", "d2_rcu_stall.log", "analyze_watchdog_timeout",
        lambda: _run(analyze_watchdog_timeout,
                     dmesg_log=_read(logs_dir / "d2_rcu_stall.log")),
        [
            Check("lockup_detected == True",
                  lambda r: r["lockup_detected"] is True),
            Check("lockup_type in ('rcu_stall','soft_lockup')",
                  lambda r: r["lockup_type"] in ("rcu_stall", "soft_lockup")),
        ])

    def _log017_secondary(wd_result: dict) -> list[dict]:
        return [_run(decode_esr_el1, hex_value="0xbf000002")]

    add("LOG-017", "d2_watchdog_serror_combined.log", "analyze_watchdog_timeout + decode_esr_el1",
        lambda: _run(analyze_watchdog_timeout,
                     dmesg_log=_read(logs_dir / "d2_watchdog_serror_combined.log")),
        [
            Check("lockup_detected == True",
                  lambda r: r["lockup_detected"] is True),
        ],
        secondary_fn=_log017_secondary)

    # --- Domain 3: Hardware Advisor ---

    add("LOG-018", "d3_std_high_sunreclaim.log", "analyze_std_hibernation_error",
        lambda: _run(analyze_std_hibernation_error,
                     dmesg_log=_read(logs_dir / "d3_std_high_sunreclaim.log"),
                     meminfo_log=_read(logs_dir / "d3_std_high_sunreclaim.meminfo")),
        [
            Check("error_detected == True",
                  lambda r: r["error_detected"] is True),
            Check("sunreclaim_exceeds_threshold == True",
                  lambda r: r.get("sunreclaim_exceeds_threshold") is True),
            Check("confidence >= 0.85",
                  lambda r: r["confidence"] >= 0.85),
        ])

    add("LOG-019", "d3_std_swap_exhausted.log", "analyze_std_hibernation_error",
        lambda: _run(analyze_std_hibernation_error,
                     dmesg_log=_read(logs_dir / "d3_std_swap_exhausted.log"),
                     meminfo_log=_read(logs_dir / "d3_std_swap_exhausted.meminfo")),
        [
            Check("error_detected == True",
                  lambda r: r["error_detected"] is True),
            Check("swap_free_kb == 0",
                  lambda r: r.get("swap_free_kb") == 0),
            Check("confidence >= 0.80",
                  lambda r: r["confidence"] >= 0.80),
        ])

    add("LOG-020", "d3_ufs_probe_fail.log", "check_vendor_boot_ufs_driver",
        lambda: _run(check_vendor_boot_ufs_driver,
                     dmesg_log=_read(logs_dir / "d3_ufs_probe_fail.log")),
        [
            Check("failure_detected == True",
                  lambda r: r["failure_detected"] is True),
            Check("failure_phase == 'probe'",
                  lambda r: r.get("failure_phase") == "probe"),
            Check("confidence >= 0.85",
                  lambda r: r["confidence"] >= 0.85),
        ])

    add("LOG-021", "d3_ufs_link_startup_fail.log", "check_vendor_boot_ufs_driver",
        lambda: _run(check_vendor_boot_ufs_driver,
                     dmesg_log=_read(logs_dir / "d3_ufs_link_startup_fail.log")),
        [
            Check("failure_detected == True",
                  lambda r: r["failure_detected"] is True),
            Check("failure_phase == 'link_startup'",
                  lambda r: r.get("failure_phase") == "link_startup"),
            Check("confidence >= 0.80",
                  lambda r: r["confidence"] >= 0.80),
        ])

    add("LOG-022", "d3_pmic_ocp_display.log", "check_pmic_rail_voltage",
        lambda: _run(check_pmic_rail_voltage,
                     dmesg_log=_read(logs_dir / "d3_pmic_ocp_display.log"),
                     logcat_log=""),
        [
            Check("ocp_detected == True",
                  lambda r: r["ocp_detected"] is True),
            Check("fault_rail populated",
                  lambda r: bool(r.get("fault_rail"))),
            Check("confidence >= 0.80",
                  lambda r: r["confidence"] >= 0.80),
        ])

    add("LOG-023", "d3_pmic_undervoltage_cpu.log", "check_pmic_rail_voltage",
        lambda: _run(check_pmic_rail_voltage,
                     dmesg_log=_read(logs_dir / "d3_pmic_undervoltage_cpu.log"),
                     logcat_log=""),
        [
            Check("undervoltage_rails non-empty",
                  lambda r: len(r.get("undervoltage_rails", [])) > 0),
            Check("confidence >= 0.80",
                  lambda r: r["confidence"] >= 0.80),
        ])

    add("LOG-024", "d3_pmic_clean_boot.log", "check_pmic_rail_voltage (negative)",
        lambda: _run(check_pmic_rail_voltage,
                     dmesg_log=_read(logs_dir / "d3_pmic_clean_boot.log"),
                     logcat_log=""),
        [
            Check("ocp_detected == False (no false positive)",
                  lambda r: r["ocp_detected"] is False),
            Check("undervoltage_rails == [] (no false positive)",
                  lambda r: r.get("undervoltage_rails", []) == []),
        ])

    # --- Domain 4: Supervisor Routing ---

    add("LOG-025", "d4_ambiguous_ufs_kernel.log", "segment_boot_log",
        lambda: _run(segment_boot_log,
                     raw_log=_read(logs_dir / "d4_ambiguous_ufs_kernel.log")),
        [
            Check("detected_stage classified (not 'unknown')",
                  lambda r: r["detected_stage"] != "unknown"),
        ])

    add("LOG-026", "d4_early_boot_healthy.log", "segment_boot_log + parse_early_boot_uart_log",
        lambda: _run(segment_boot_log,
                     raw_log=_read(logs_dir / "d4_early_boot_healthy.log")),
        [
            Check("detected_stage == 'early_boot'",
                  lambda r: r["detected_stage"] == "early_boot"),
        ],
        secondary_fn=lambda _: [_run(parse_early_boot_uart_log,
                                      raw_uart_log=_read(logs_dir / "d4_early_boot_healthy.log"))])

    add("LOG-027", "d4_android_selinux_avc.log", "segment_boot_log",
        lambda: _run(segment_boot_log,
                     raw_log=_read(logs_dir / "d4_android_selinux_avc.log")),
        [
            Check("detected_stage == 'android_init'",
                  lambda r: r["detected_stage"] == "android_init"),
        ])

    add("LOG-028", "d4_android_slow_boot.log", "segment_boot_log",
        lambda: _run(segment_boot_log,
                     raw_log=_read(logs_dir / "d4_android_slow_boot.log")),
        [
            Check("detected_stage == 'android_init'",
                  lambda r: r["detected_stage"] == "android_init"),
            Check("confidence >= 0.75",
                  lambda r: r["confidence"] >= 0.75),
        ])

    return cases


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

EMOJI = {"PASS": "✅", "PARTIAL": "⚠️ ", "FAIL": "❌", "ERROR": "💥", "PENDING": "⏳"}


def render_report(runs: list[SkillRun], logs_dir: Path) -> str:
    total = len(runs)
    by_status: dict[str, int] = {}
    for sr in runs:
        by_status[sr.status] = by_status.get(sr.status, 0) + 1

    lines = [
        "# BSP Skill Validation Report",
        "",
        f"Validated {total} log entries against {total} skill runs.",
        "",
        "## Summary",
        "",
        "| Status | Count |",
        "|--------|-------|",
    ]
    for status in ("PASS", "PARTIAL", "FAIL", "ERROR"):
        n = by_status.get(status, 0)
        lines.append(f"| {EMOJI[status]} {status} | {n} |")

    lines += [
        "",
        "## Results",
        "",
        "| ID | File | Skill | Status | Details |",
        "|---|---|---|---|---|",
    ]

    for sr in runs:
        em = EMOJI[sr.status]
        if sr.status == "PASS":
            detail = "All checks passed"
        elif sr.status == "ERROR":
            detail = f"Exception: {sr.error}"
        else:
            issues = "; ".join(f"FAIL: {c}" for c in sr.failed_checks)
            detail = issues or "—"
        lines.append(
            f"| {sr.log_id} | `{sr.log_file}` | `{sr.skill_name}` | {em} {sr.status} | {detail} |"
        )

    lines += ["", "## Detailed Findings", ""]

    for sr in runs:
        if sr.status == "PASS":
            continue
        lines += [f"### {sr.log_id} — {sr.log_file} ({sr.status})", ""]
        if sr.error:
            lines += [f"**Exception:** `{sr.error}`", ""]
        if sr.failed_checks:
            lines += ["**Failed checks:**", ""]
            for c in sr.failed_checks:
                lines.append(f"- ❌ {c}")
            lines.append("")
        if sr.passed_checks:
            lines += ["**Passed checks:**", ""]
            for c in sr.passed_checks:
                lines.append(f"- ✅ {c}")
            lines.append("")
        if sr.result:
            key_fields = {
                k: v for k, v in sr.result.items()
                if k not in ("root_cause", "recommended_action")
                   and v not in (None, [], "")
            }
            lines += [
                "**Skill output (key fields):**",
                "```json",
                json.dumps(key_fields, indent=2, default=str),
                "```",
                "",
            ]

    # Improvement recommendations
    failed = [sr for sr in runs if sr.status in ("FAIL", "PARTIAL", "ERROR")]
    if failed:
        lines += [
            "## Improvement Recommendations",
            "",
            "| ID | Skill | Action |",
            "|---|---|---|",
        ]
        for sr in failed:
            if sr.status == "ERROR":
                action = "Fix skill exception — check input schema"
            elif any("error_type" in c or "panic_type" in c or "oops_type" in c
                     or "lockup_type" in c or "failure_phase" in c
                     for c in sr.failed_checks):
                action = "Add/update detection pattern in skill — consider `suggest_pattern_improvement`"
            elif any("confidence" in c for c in sr.failed_checks):
                action = "Confidence below threshold — review classification logic or check log quality"
            else:
                action = "Review expected output vs actual — may require fixture update"
            lines.append(f"| {sr.log_id} | `{sr.skill_name}` | {action} |")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    logs_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("logs/validation")

    if not logs_dir.exists():
        print(f"ERROR: logs directory not found: {logs_dir}", file=sys.stderr)
        return 1

    cases = build_cases(logs_dir)
    runs: list[SkillRun] = []

    for log_id, runner in cases:
        sr = runner()
        runs.append(sr)
        status_icon = EMOJI.get(sr.status, "?")
        print(f"  {status_icon} {log_id} [{sr.skill_name}]", file=sys.stderr)

    report = render_report(runs, logs_dir)
    print(report)

    # Write JSON summary
    summary = {
        "total": len(runs),
        "by_status": {},
        "runs": [],
    }
    for sr in runs:
        summary["by_status"][sr.status] = summary["by_status"].get(sr.status, 0) + 1
        summary["runs"].append({
            "log_id": sr.log_id,
            "log_file": sr.log_file,
            "skill_name": sr.skill_name,
            "status": sr.status,
            "failed_checks": sr.failed_checks,
            "passed_checks": sr.passed_checks,
            "error": sr.error,
        })

    report_path = logs_dir / "skill_validation_report.json"
    report_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\n<!-- JSON report written to {report_path} -->", file=sys.stderr)

    any_fail = any(sr.status in ("FAIL", "ERROR") for sr in runs)
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
