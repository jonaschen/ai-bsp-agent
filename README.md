# Android BSP Diagnostic Expert

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Version:** v6.0 (Skill-Based Expert)
> **Status:** Research Prototype / Serious AI Systems Engineering

## Project Overview

This repository hosts the **Android BSP Diagnostic Expert**, a specialized AI agent system for diagnosing complex Android/Linux BSP (Board Support Package) issues. The system uses an Anthropic Claude tool-use loop paired with deterministic Python skills to perform accurate Root Cause Analysis (RCA) on kernel logs, power management failures, and hardware-related panics.

### 市場定位 | Market Positioning
The **Android BSP Diagnostic Expert** occupies a unique niche by utilizing the Anthropic Tool-Use / Agent Skill paradigm. It serves as a **Specialized AI Systems Research Prototype** for:
*   **Domain-Specific Expertise:** Focusing on the high-stakes, log-intensive environment of Android Board Support Package (BSP) development.
*   **Deterministic Reasoning:** Replacing error-prone AI code generation with deterministic, human-authored Python tools that provide ground truth for the reasoning LLM.

### 為何重要 | Why This Matters
*   **Accuracy over Autonomy:** By enforcing strict tool use, we prevent LLM hallucinations regarding hardware state and register calculations.
*   **Skill-Based Architecture:** The v6 pivot replaces the legacy code-generation factory with an expert diagnostic agent backed by pure Python Skills.

### 當前功能快照 | Current Capability Snapshot
*   **BSPDiagnosticAgent:** Claude (`claude-sonnet-4-6`) tool-use loop that runs registered Skills and returns structured `ConsultantResponse` JSON.
*   **SupervisorAgent:** Claude (`claude-haiku-4-5-20251001`) triage router that classifies incoming logs as `kernel_pathologist`, `hardware_advisor`, or `clarify_needed`.
*   **Skill Registry:** Anthropic-compatible tool definitions auto-generated from Pydantic schemas; `dispatch_tool()` router.
*   **STD Hibernation Skill:** Diagnoses Suspend-to-Disk failures by parsing `SUnreclaim`, `SwapFree`, and `MemTotal` from dmesg + meminfo logs.

### 侷限性 | Limitations
*   **Environment Specificity:** Currently optimized for Android BSP contexts; adapting to other domains requires new Skills and knowledge-base updates.
*   **Single Skill:** Only one diagnostic skill (`analyze_std_hibernation_error`) is registered; AArch64 exception skills are planned.
*   **API Key Required:** Requires a valid `ANTHROPIC_API_KEY` for agent execution (not needed for skill unit tests).

---

### GitHub Topics
`ai-systems`, `multi-agent`, `anthropic`, `tool-use`, `android-bsp`, `ai-safety`, `bsp-diagnostics`, `pydantic`

---

## Architecture

The system operates as a **Skill-Based Expert Agent** using the Anthropic Tool-Use paradigm. It consists of three layers defined in `AGENTS.md`:

### Layer 1: The Brain (The Reasoning Engine)
*   **`BSPDiagnosticAgent`** (`product/bsp_agent/agent.py`): Runs the Anthropic tool-use loop; invokes Skills via `dispatch_tool()` and validates the final `ConsultantResponse`.
*   **`SupervisorAgent`** (`product/bsp_agent/agents/supervisor.py`): Triages incoming `AgentState` logs and routes to the appropriate specialist.
*   **Constraint:** The Brain never performs math, parses hex offsets, or calculates memory sizes directly — it delegates to Skills.

### Layer 2: The Skill Registry (The Tools)
*   Pure Python functions located in `skills/bsp_diagnostics/`.
*   Every skill has strict Pydantic `Input`/`Output` schemas and is registered in `skills/registry.py` as an Anthropic-compatible tool.
*   Deterministic, isolated — no LLM calls, no side effects, no global state.

### Layer 3: The Knowledge Base
*   Markdown files (`skills/SKILL.md`, `AGENTS.md`, `docs/`) containing domain knowledge.
*   Uses progressive disclosure to provide the LLM context only when needed.

## Repository Structure

```
.
├── AGENTS.md                        # The Constitution: Rules and Governance for all agents.
├── CLAUDE.md                        # Coding agent guidance and milestone tracker.
├── DESIGN.md                        # Software design document.
├── README.md                        # This file.
├── requirements.txt                 # Python dependencies.
├── pytest.ini                       # Pytest configuration (pythonpath = .).
├── product/                         # Core product logic.
│   ├── bsp_agent/
│   │   ├── agent.py                 # BSPDiagnosticAgent — the main Claude tool-use loop.
│   │   ├── agents/
│   │   │   └── supervisor.py        # SupervisorAgent — log triage router.
│   │   └── core/
│   │       └── state.py             # AgentState TypedDict for LangGraph.
│   └── schemas/
│       └── __init__.py              # All Pydantic models (CaseFile, ConsultantResponse, …).
├── skills/                          # The Skill Registry: deterministic Python tools.
│   ├── SKILL.md                     # Skill index and authoring contract.
│   ├── registry.py                  # Anthropic tool definitions + dispatch_tool() router.
│   └── bsp_diagnostics/
│       └── std_hibernation.py       # analyze_std_hibernation_error skill.
├── tests/
│   └── product_tests/               # Isolated pytest suite (no LLM calls).
└── studio/                          # Legacy factory code (deprecated — do not modify).
```

## Implemented Milestones

| # | Milestone | Status |
|---|-----------|--------|
| 1 | First skill — `analyze_std_hibernation_error` + 14 isolated tests | ✅ Done |
| 2 | `skills/registry.py` — Anthropic tool definitions + `dispatch_tool()` + 11 tests | ✅ Done |
| 3 | `BSPDiagnosticAgent` — Claude tool-use loop, markdown stripping, CLARIFY_NEEDED fallback + 9 tests | ✅ Done |
| 4 | `SupervisorAgent` migrated from Vertex AI to Claude (`claude-haiku-4-5-20251001`) + 11 tests | ✅ Done |

## Getting Started

### Prerequisites
*   Python 3.10+
*   `ANTHROPIC_API_KEY` environment variable (required for agent execution; not needed for skill unit tests)

### Installation
```bash
pip install -r requirements.txt
```

### Running Tests
Execute the full test suite (Skills and Agents tested in isolation — no LLM calls required):

```bash
source venv/bin/activate && python -m pytest
```

Run a single test file:
```bash
source venv/bin/activate && python -m pytest tests/product_tests/test_std_hibernation.py
```

### Using the Diagnostic Agent
```python
import os
from product.schemas import CaseFile, LogPayload
from product.bsp_agent.agent import BSPDiagnosticAgent

case = CaseFile(
    case_id="CASE-001",
    device_model="Pixel 8",
    source_code_mode="git",
    user_query="Hibernation fails with Error -12",
    log_payload=LogPayload(
        dmesg_content="<paste dmesg here>",
        logcat_content="<paste /proc/meminfo here>",
    ),
)

agent = BSPDiagnosticAgent()   # requires ANTHROPIC_API_KEY
response = agent.run(case)
print(response.model_dump_json(indent=2))
```

## Adding a New Skill

1. Create `skills/bsp_diagnostics/<skill_name>.py` with `Input`/`Output` Pydantic models and the pure function.
2. Write isolated pytest in `tests/product_tests/test_<skill_name>.py` — no LLM.
3. Register in `skills/registry.py` as an Anthropic-compatible tool.
4. Add a row to the skill table in `skills/SKILL.md` and `CLAUDE.md`.

## License

This project is licensed under the **MIT License**.

- **SPDX Identifier:** [MIT](https://opensource.org/licenses/MIT)
- **License Text:** See the [LICENSE](LICENSE) file in this repository for full details.
