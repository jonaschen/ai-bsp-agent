# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Prime Directive

**Follow `AGENTS.md` at all times.** It is the supreme governance document ("The Constitution"). Key rules:
- **TDD is Law**: Write a failing test first (Red), then minimal implementation (Green), then one refactor attempt. If refactor breaks tests, revert to Green and tag `#TODO: Tech Debt`.
- **No Self-Modification**: The Agent cannot modify `AGENTS.md`, its own source code, or its Tools.
- **Skill Purity**: Every skill in `skills/` must be a pure function — no side effects, no LLM calls, no global state.
- **Frozen Dirs**: `studio/subgraphs/engineer.py` and `studio/utils/sandbox.py` are deprecated. Do not modify them.

## Commands

Run any tests and any git operations without asking for confirmation first.

Run tests:
```bash
source venv/bin/activate && python -m pytest
```

Run a single test file or function:
```bash
source venv/bin/activate && python -m pytest tests/product_tests/test_std_hibernation.py
source venv/bin/activate && python -m pytest tests/product_tests/test_std_hibernation.py::TestHighSUnreclaim
```

`pytest.ini` sets `pythonpath = .`, so `PYTHONPATH=.` is only needed when running scripts directly (not pytest).

## Architecture (v6 — Skill-Based Expert)

This system is an **Android BSP Diagnostic Expert Agent**. It pivoted from a code-generation factory (v5) to a skill-based expert (v6). See `PIVOT_PLAN.md` for rationale.

**Do NOT attempt to fix legacy `studio/` factory logic, Docker/sandbox issues, or `issues.md` items.**

Three layers:

### Layer 1: The Brain (Reasoning Engine)
- `product/bsp_agent/agent.py` — `BSPDiagnosticAgent`: runs the Anthropic tool-use loop. Accepts a `CaseFile`, calls the Supervisor, selects route-appropriate tools, returns a `ConsultantResponse`.
- `product/bsp_agent/agents/supervisor.py` — `SupervisorAgent` (Claude Haiku): triages dmesg and routes to `kernel_pathologist`, `hardware_advisor`, or `clarify_needed`. Performs event-horizon chunking for large logs.
- `product/bsp_agent/core/state.py` — `AgentState` TypedDict passed to the supervisor.
- The Brain must **never** do math, parse hex offsets, or calculate memory sizes directly — always delegate to Skills.

### Layer 2: The Skill Registry (Tools)
Pure Python functions in `skills/bsp_diagnostics/`. Each skill:
- Has strict Pydantic `Input` / `Output` schemas.
- Is deterministic and isolated (no LLM, no I/O, no global state).
- Has a corresponding `pytest` in `tests/product_tests/` that does NOT invoke the LLM.
- Is registered in `skills/registry.py` as an Anthropic-compatible tool definition.
- `skills/registry.py` also exports `ROUTE_TOOLS` — a mapping from supervisor routes to the set of tool names for that domain. The Brain uses this to offer only the relevant tools to Claude per session.

| Skill file | Function | Route | Domain |
|---|---|---|---|
| `skills/bsp_diagnostics/std_hibernation.py` | `analyze_std_hibernation_error(dmesg_log, meminfo_log)` | `hardware_advisor` | STD / Suspend-to-Disk |
| `skills/bsp_diagnostics/aarch64_exceptions.py` | `decode_esr_el1(hex_value)` | `kernel_pathologist` | AArch64 Exceptions |
| `skills/bsp_diagnostics/aarch64_exceptions.py` | `check_cache_coherency_panic(panic_log)` | `kernel_pathologist` | AArch64 Cache Coherency |

### Layer 3: The Knowledge Base
- `skills/SKILL.md` — Skill Registry index and authoring contract.
- `AGENTS.md` — Architecture constitution (do not modify).
- `docs/` — Markdown domain knowledge files (kernel versions, GKI requirements, etc.).

### Product Schemas
`product/schemas/__init__.py` — All Pydantic models:
- `CaseFile`, `LogPayload` — core input unit. `LogPayload` has three fields: `dmesg_content` (required), `meminfo_content` (optional, `/proc/meminfo`), `logcat_content` (optional).
- `TriageReport`, `RCAReport`, `ConsultantResponse` — diagnostic outputs.
- `SOPStep` — individual remediation step.
- Agent I/O contracts: `SupervisorInput`, `PathologistOutput`, `HardwareAdvisorInput/Output`.

### Deprecated (do not touch)
- `studio/subgraphs/engineer.py` — legacy Jules/GitHub dispatch loop.
- `studio/utils/sandbox.py` — legacy Docker QA sandbox.
- `issues.md` — legacy factory issue tracker (irrelevant to v6).

## Development Milestones

- **Milestone 1** (DONE): First skill — `analyze_std_hibernation_error` + 14 isolated tests.
- **Milestone 2** (DONE): `skills/registry.py` — Anthropic-compatible tool definitions auto-generated from Pydantic schemas; `dispatch_tool()` + `ROUTE_TOOLS`; 11 tests.
- **Milestone 3** (DONE): `product/bsp_agent/agent.py` — `BSPDiagnosticAgent` Anthropic tool-use loop; Supervisor integration; route-based tool selection; markdown stripping; CLARIFY_NEEDED fallback.
- **Milestone 4** (DONE): `SupervisorAgent` migrated from Vertex AI to Claude (`claude-haiku-4-5-20251001`). `anthropic` added to `requirements.txt`.
- **Fix #1** (DONE): `LogPayload.meminfo_content` added; `_build_user_message` fixed; logcat/meminfo no longer conflated.
- **Fix #2** (DONE): `SupervisorAgent` wired into `BSPDiagnosticAgent.run()`; route-based tool filtering via `ROUTE_TOOLS`.
- **Skills #3+#4** (DONE): `decode_esr_el1` + `check_cache_coherency_panic` in `skills/bsp_diagnostics/aarch64_exceptions.py`; 31 isolated tests. Total product tests: 107.

## Adding a New Skill

1. Create `skills/bsp_diagnostics/<skill_name>.py` with `Input`/`Output` Pydantic models and the pure function.
2. Write isolated pytest in `tests/product_tests/test_<skill_name>.py` — no LLM.
3. Register in `skills/registry.py` as an Anthropic-compatible tool.
4. Add a row to the skill table in `skills/SKILL.md` and in this file.
