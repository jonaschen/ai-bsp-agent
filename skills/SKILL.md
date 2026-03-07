# SKILL.md — BSP Diagnostic Skills Registry

## Overview

This directory contains pure Python **Diagnostic Skills** (Tools) for the Android BSP
Consultant Agent. Each Skill is a deterministic, human-authored function that parses
hardware/kernel logs and returns a structured diagnostic report.

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
| `bsp_diagnostics/std_hibernation.py` | `analyze_std_hibernation_error` | `hardware_advisor` | STD / Suspend-to-Disk |
| `bsp_diagnostics/aarch64_exceptions.py` | `decode_esr_el1` | `kernel_pathologist` | AArch64 Exceptions |
| `bsp_diagnostics/aarch64_exceptions.py` | `check_cache_coherency_panic` | `kernel_pathologist` | AArch64 Cache Coherency |

## Domains

- **`bsp_diagnostics/`** — Android BSP kernel/hardware log analysis.

## Contributing

1. Write the pure Python function with strict Pydantic I/O.
2. Add a `pytest` test in `tests/product_tests/` that exercises the function with fixture data.
3. Register the function as an Anthropic-compatible Tool in the Agent's tool registry.

See `AGENTS.md` §2.2 for the full Skill Registry contract.
