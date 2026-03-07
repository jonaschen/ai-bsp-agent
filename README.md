# Android BSP Diagnostic Expert

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Version:** v6.0 (Skill-Based Expert)
> **Status:** Research Prototype / Serious AI Systems Engineering

## Project Overview

This repository hosts the **Android BSP Diagnostic Expert**, a specialized AI agent system for diagnosing complex Android/Linux BSP (Board Support Package) issues. The system uses an Anthropic Claude tool-use loop paired with deterministic Python skills to perform accurate Root Cause Analysis (RCA) on kernel logs, power management failures, and hardware-related panics.

### Market Positioning

The **Android BSP Diagnostic Expert** occupies a unique niche by utilizing the Anthropic Tool-Use / Agent Skill paradigm. It serves as a **Specialized AI Systems Research Prototype** for:

- **Domain-Specific Expertise:** Focusing on the high-stakes, log-intensive environment of Android Board Support Package (BSP) development.
- **Deterministic Reasoning:** Replacing error-prone AI code generation with deterministic, human-authored Python tools that provide ground truth for the reasoning LLM.

### Why This Matters

- **Accuracy over Autonomy:** By enforcing strict tool use, we prevent LLM hallucinations regarding hardware state and register calculations.
- **Skill-Based Architecture:** The v6 pivot replaces the legacy code-generation factory with an expert diagnostic agent backed by pure Python Skills.

---

## Architecture

The system operates as a **Skill-Based Expert Agent** using the Anthropic Tool-Use paradigm. Three distinct layers:

### Layer 1: The Brain (Reasoning Engine)

- **`BSPDiagnosticAgent`** (`product/bsp_agent/agent.py`): Runs the Claude Sonnet tool-use loop; invokes Skills via `dispatch_tool()` and validates the final `ConsultantResponse`.
- **`SupervisorAgent`** (`product/bsp_agent/agents/supervisor.py`): Claude Haiku triage router — classifies incoming logs as `kernel_pathologist`, `hardware_advisor`, or `clarify_needed` in a single token (max_tokens=16).
- **Constraint:** The Brain never performs math, parses hex offsets, or calculates memory sizes — it always delegates to Skills.

### Layer 2: The Skill Registry (Deterministic Tools)

Pure Python functions in `skills/bsp_diagnostics/`. Every skill has:
- Strict Pydantic `Input`/`Output` schemas
- Registration in `skills/registry.py` as an Anthropic-compatible tool definition
- Isolated `pytest` coverage — no LLM calls

### Layer 3: The Knowledge Base

Markdown files in `docs/` with YAML frontmatter scoping each document to a supervisor route and skill set. The Brain reads these as context to produce better `root_cause_summary` and `sop_steps` in the `ConsultantResponse`.

---

## Diagnostic Skills

### `hardware_advisor` route

| Skill | File | What it detects |
|---|---|---|
| `analyze_std_hibernation_error` | `std_hibernation.py` | STD Error -12; SUnreclaim > 10% MemTotal; SwapFree == 0 |
| `check_vendor_boot_ufs_driver` | `vendor_boot.py` | UFS driver failures during STD restore; phase-classified as probe / link_startup / resume |
| `check_pmic_rail_voltage` | `pmic.py` | PMIC OCP and undervoltage events; parses Qualcomm rpm-smd, qpnp, and generic regulator formats |

### `kernel_pathologist` route

| Skill | File | What it detects |
|---|---|---|
| `decode_esr_el1` | `aarch64_exceptions.py` | Decodes AArch64 ESR_EL1 (EC, IL, ISS, DFSC/IFSC) against ARM DDI0487 tables |
| `check_cache_coherency_panic` | `aarch64_exceptions.py` | SError / PoC cache coherency failures; ESR_EL1 EC=0x2F |
| `analyze_watchdog_timeout` | `watchdog.py` | Soft lockup, hard lockup (NMI watchdog), RCU stall; extracts CPU, PID, process name, call trace |

---

## Repository Structure

```
.
├── AGENTS.md                        # The Constitution: rules and governance for all agents.
├── CLAUDE.md                        # Coding agent guidance and milestone tracker.
├── DESIGN.md                        # Software design document (class diagram, sequence diagram, roadmap).
├── README.md                        # This file.
├── cli.py                           # CLI entry point: python cli.py --dmesg <path> [--meminfo <path>]
├── requirements.txt                 # Python dependencies.
├── pytest.ini                       # Pytest configuration (pythonpath = .).
├── docs/                            # Knowledge base — domain reference for the Brain.
│   ├── aarch64-exceptions.md        # ESR_EL1 field layout, EC/DFSC tables, SError checklist.
│   └── memory-reclamation.md        # STD hibernation failure logic, SUnreclaim/SwapFree thresholds.
├── product/                         # Core product logic.
│   ├── bsp_agent/
│   │   ├── agent.py                 # BSPDiagnosticAgent — the main Claude tool-use loop.
│   │   └── agents/
│   │       └── supervisor.py        # SupervisorAgent — log triage router (Claude Haiku).
│   └── schemas/
│       └── __init__.py              # All Pydantic models: CaseFile, ConsultantResponse, LogPayload, …
├── skills/                          # The Skill Registry: deterministic Python tools.
│   ├── SKILL.md                     # Skill index and authoring contract.
│   ├── registry.py                  # Anthropic tool definitions + dispatch_tool() router.
│   └── bsp_diagnostics/
│       ├── std_hibernation.py       # analyze_std_hibernation_error
│       ├── aarch64_exceptions.py    # decode_esr_el1, check_cache_coherency_panic
│       ├── vendor_boot.py           # check_vendor_boot_ufs_driver
│       ├── watchdog.py              # analyze_watchdog_timeout
│       └── pmic.py                  # check_pmic_rail_voltage
├── tests/
│   └── product_tests/               # Isolated pytest suite (no LLM calls) — 231 tests.
│       ├── test_integration.py      # End-to-end pipeline (mocked Anthropic client).
│       └── fixtures/                # Golden-set log files and expected output JSON.
└── studio/                          # Legacy factory code (deprecated — do not modify).
```

---

## Getting Started

### Prerequisites

- Python 3.10+
- `ANTHROPIC_API_KEY` environment variable (required for agent execution; not needed for skill unit tests)

### Installation

```bash
pip install -r requirements.txt
```

### Running Tests

No API key needed — the full test suite is isolated:

```bash
source venv/bin/activate && python -m pytest
```

Run a single skill test file:

```bash
source venv/bin/activate && python -m pytest tests/product_tests/test_watchdog_skill.py
```

### CLI Usage

```bash
# Basic — dmesg only
python cli.py --dmesg logs/dmesg.txt

# With meminfo (required for STD hibernation diagnosis)
python cli.py --dmesg logs/dmesg.txt --meminfo logs/meminfo.txt

# Save structured output to file
python cli.py --dmesg logs/panic.txt --device Pixel_Watch_Proto --output result.json

# Custom query
python cli.py --dmesg logs/dmesg.txt \
              --query "Device failed to resume from STD" \
              --output result.json
```

Output is a `ConsultantResponse` JSON printed to stdout. Status messages go to stderr so the JSON can be piped directly.

### Python API Usage

```python
from product.schemas import CaseFile, LogPayload
from product.bsp_agent.agent import BSPDiagnosticAgent

case = CaseFile(
    case_id="CASE-001",
    device_model="Pixel_Watch_Proto",
    source_code_mode="USER_UPLOADED",
    user_query="Device failed to resume from STD",
    log_payload=LogPayload(
        dmesg_content=open("logs/dmesg.txt").read(),
        meminfo_content=open("logs/meminfo.txt").read(),  # optional
    ),
)

agent = BSPDiagnosticAgent()  # requires ANTHROPIC_API_KEY
response = agent.run(case)
print(response.model_dump_json(indent=2))
```

---

## Real-World Log Validation (Item #11)

The skills were authored from documentation and synthetic test logs. Running against real hardware logs is the next critical step. Here is the recommended workflow.

### Step 1 — Run the agent on a known failure

Use a log where you already know the root cause. Compare the agent's output to your actual diagnosis and note every discrepancy.

```bash
python cli.py --dmesg /path/to/real_dmesg.txt \
              --meminfo /path/to/real_meminfo.txt \
              --query "Describe the failure you observed" \
              --output result.json
```

For each run, evaluate:
- Was the **supervisor route** correct (`hardware_advisor` vs `kernel_pathologist`)?
- Did the agent call the **right skill**?
- Was the **root_cause** accurate?
- Was the **confidence** realistic?
- Were the **sop_steps** actionable?

### Step 2 — Known gaps to watch for

**Supervisor routing errors** (most damaging — wrong toolset offered):
- A UFS resume failure with a co-occurring kernel oops may be misrouted to `kernel_pathologist`
- A watchdog lockup during suspend may be misrouted to `hardware_advisor` if the panic message is ambiguous

**Skill false negatives** (most likely per skill):

| Skill | Likely gap |
|---|---|
| `analyze_watchdog_timeout` | Vendor kernels use non-standard formats (e.g., Qualcomm: `[0: kworker:1234] BUG: soft lockup`) |
| `check_pmic_rail_voltage` | Vendor-specific voltage log formats not yet covered |
| `check_vendor_boot_ufs_driver` | MTK (`ufs-mediatek`) and Exynos (`ufshcd-exynos`) driver prefixes not fully covered |
| `analyze_std_hibernation_error` | 10% SUnreclaim threshold may need lowering for 512 MB devices |

### Step 3 — Deciding what to fix

For each discrepancy found, choose the right fix:

| Discrepancy | Fix |
|---|---|
| Agent had all the information but reasoned poorly | Add/improve `docs/` knowledge base |
| Skill missed a real log pattern | Fix the skill's regex or detection logic |
| A new failure class with no existing skill | Add a new skill (see workflow below) |
| Supervisor routed to the wrong domain | Improve supervisor prompt or add routing keywords |

### Step 4 — Knowledge base docs to add

These docs give the Brain context to write better `root_cause_summary` and `sop_steps`:

| File | Scope | Trigger keywords |
|---|---|---|
| `docs/ufs-driver.md` | UFS link startup, ufshcd error codes, PHY power sequencing | `hardware_advisor` |
| `docs/watchdog-lockup.md` | Soft/hard lockup anatomy, call trace reading, CONFIG_LOCKUP_DETECTOR | `kernel_pathologist` |
| `docs/pmic-rails.md` | Qualcomm/MTK PMIC rail naming conventions, OCP behavior, UVLO thresholds | `hardware_advisor` |

---

## Adding a New Skill

1. Create `skills/bsp_diagnostics/<skill_name>.py` with `Input`/`Output` Pydantic models and the pure function.
2. Write isolated pytest in `tests/product_tests/test_<skill_name>.py` — no LLM.
3. Register in `skills/registry.py`: add to `TOOL_DEFINITIONS`, `ROUTE_TOOLS`, and `_DISPATCH_TABLE`.
4. Add a row to `skills/SKILL.md`.

See `AGENTS.md` §4 for the full development protocol.

---

## License

This project is licensed under the **MIT License**.

- **SPDX Identifier:** [MIT](https://opensource.org/licenses/MIT)
- **License Text:** See the [LICENSE](LICENSE) file in this repository for full details.
