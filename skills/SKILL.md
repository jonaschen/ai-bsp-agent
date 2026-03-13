# SKILL.md — BSP Diagnostic Skills Registry

## Overview

This directory contains pure Python **Diagnostic Skills** (Tools) for the Android BSP
Consultant Agent. Each Skill is a deterministic, human-authored function that parses
hardware/kernel logs and returns a structured diagnostic report.

**Related documentation:**
- `docs/emulator-spec.md` — exact software/source versions for all training emulators
- `docs/skill-extension-guide.md` — how end-user agents extend skills for real hardware

## Architecture

Skills follow the **Anthropic Tool-Use** paradigm:
- **Pure functions** — no side effects, no LLM calls, no global state.
- **Pydantic schemas** — strict typed inputs/outputs for every Tool.
- **Isolated testing** — each Skill has a corresponding `pytest` test that does NOT invoke the LLM.

## Expected Tool Structure

```python
from pydantic import BaseModel

class MySkillInput(BaseModel):
    dmesg_log: str
    meminfo_log: str

class MySkillOutput(BaseModel):
    root_cause: str
    recommended_action: str
    confidence: float

def my_bsp_skill(input: MySkillInput) -> MySkillOutput:
    """
    Deterministic diagnostic function.
    Parse logs, extract metrics, return structured RCA.
    """
    ...
```

## Current Skills

19 core skills across 5 supervisor routes. Phase 8 adds 4 workspace analysis skills (23 total including improvement tools). See `reports/skill_validation_report.md` for the full validation run.

| Module | Function | Supervisor Route | Domain |
|--------|----------|-----------------|--------|
| `bsp_diagnostics/log_segmenter.py` | `segment_boot_log` | **universal** (all routes) | Boot Stage Triage |
| `bsp_diagnostics/early_boot.py` | `parse_early_boot_uart_log` | `early_boot_advisor` | TF-A / BootROM UART |
| `bsp_diagnostics/early_boot.py` | `analyze_lk_panic` | `early_boot_advisor` | LK / U-Boot Panic |
| `bsp_diagnostics/kernel_oops.py` | `extract_kernel_oops_log` | `kernel_pathologist` | Kernel Oops / BUG Parser |
| `bsp_diagnostics/aarch64_exceptions.py` | `decode_esr_el1` | `kernel_pathologist` | AArch64 ESR_EL1 Decode |
| `bsp_diagnostics/aarch64_exceptions.py` | `decode_aarch64_exception` | `kernel_pathologist` | ESR_EL1 + FAR_EL1 Decode |
| `bsp_diagnostics/aarch64_exceptions.py` | `check_cache_coherency_panic` | `kernel_pathologist` | AArch64 Cache Coherency |
| `bsp_diagnostics/std_hibernation.py` | `analyze_std_hibernation_error` | `hardware_advisor` | STD / Suspend-to-Disk |
| `bsp_diagnostics/vendor_boot.py` | `check_vendor_boot_ufs_driver` | `hardware_advisor` | UFS Driver / STD Restore |
| `bsp_diagnostics/watchdog.py` | `analyze_watchdog_timeout` | `kernel_pathologist` | Watchdog / Soft+Hard Lockup |
| `bsp_diagnostics/pmic.py` | `check_pmic_rail_voltage` | `hardware_advisor` | PMIC Rail Voltages |
| `bsp_diagnostics/android_init.py` | `analyze_selinux_denial` | `android_init_advisor` | SELinux AVC Denial Parser |
| `bsp_diagnostics/android_init.py` | `check_android_init_rc` | `android_init_advisor` | Init.rc Command / Service Failure |
| `bsp_diagnostics/subsystems.py` | `check_clock_dependencies` | `kernel_pathologist` | CCF Probe-Defer / clk_get Failure |
| `bsp_diagnostics/subsystems.py` | `diagnose_vfs_mount_failure` | `kernel_pathologist` | VFS Root Mount Error |
| `bsp_diagnostics/subsystems.py` | `analyze_firmware_load_error` | `kernel_pathologist` | Firmware request_firmware Failure |
| `bsp_diagnostics/subsystems.py` | `analyze_early_oom_killer` | `hardware_advisor` | Early OOM Kill Events |
| `bsp_diagnostics/workspace.py` | `resolve_oops_symbols` | `source_analyst` | Oops Call-Trace Symbol Resolution |
| `bsp_diagnostics/workspace.py` | `compare_device_tree_nodes` | `source_analyst` | DTS Node Property Diff |
| `bsp_diagnostics/workspace.py` | `diff_kernel_configs` | `source_analyst` | Kernel .config Diff |
| `bsp_diagnostics/workspace.py` | `validate_gpio_pinctrl_conflict` | `source_analyst` | GPIO/Pinctrl Conflict Detection |
| `bsp_diagnostics/skill_improvement.py` | `validate_skill_extension` | **any** (end-user agent) | Dry-run regex against log snippet |
| `bsp_diagnostics/skill_improvement.py` | `suggest_pattern_improvement` | **any** (end-user agent) | Validate + persist new detection pattern |

### Pattern coverage notes (real-hardware validated)

| Skill | Key pattern details |
|---|---|
| `segment_boot_log` | Detects LK via `welcome to lk/MP` and `INIT: cpu N, calling hook`; early_boot wins even when kernel timestamps also present (mixed logs) |
| `parse_early_boot_uart_log` | Auth failure: matches `Authentication.*(?:fail\|error)` (wildcard); PMIC: matches `PMIC.*not ready` and `regulator not ready` |
| `analyze_lk_panic` | Registers: handles both `x0 = 0xdeadbeef` (ARM32 style) and LK AArch64 space-padded `x0  0x               1` format; generic panic confidence raised to 0.75 when registers present |
| `extract_kernel_oops_log` | FAR: extracted from `FAR_EL1 = 0x...` **or** from `at virtual address X` in the Oops trigger line |
| `check_vendor_boot_ufs_driver` | Probe-phase confidence: 0.85 (consistent with link_startup 0.82 / resume 0.88) |
| `check_pmic_rail_voltage` | Undervoltage confidence: 0.82 (explicit `under-voltage detected` message warrants high confidence) |

## Domains

- **`bsp_diagnostics/`** — Android BSP kernel/hardware log analysis.

## Contributing

1. Write the pure Python function with strict Pydantic I/O.
2. Add a `pytest` test in `tests/product_tests/` that exercises the function with fixture data.
3. Register the function as an Anthropic-compatible Tool in the Agent's tool registry.

See `AGENTS.md` §2.2 for the full Skill Registry contract.

## Extending Skills for Real Hardware

The built-in patterns are trained on emulator logs (see `docs/emulator-spec.md`).
When a skill misses a real-hardware pattern, use the two improvement skills:

1. `validate_skill_extension` — dry-run test of a proposed regex
2. `suggest_pattern_improvement` — write the validated pattern to `~/.bsp-diagnostics/skill_extensions.json`

See `docs/skill-extension-guide.md` for the full workflow and examples.
