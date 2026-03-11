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
| `bsp_diagnostics/skill_improvement.py` | `validate_skill_extension` | **any** (end-user agent) | Dry-run regex against log snippet |
| `bsp_diagnostics/skill_improvement.py` | `suggest_pattern_improvement` | **any** (end-user agent) | Validate + persist new detection pattern |

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
