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

## Development Roadmap

### Phase 1 — Core Infrastructure (DONE) ✓
All pieces of the v6 architecture are in place and tested.

| Item | Status | Deliverable |
|---|---|---|
| Skill: `analyze_std_hibernation_error` | DONE | `skills/bsp_diagnostics/std_hibernation.py` — 14 tests |
| Skill Registry | DONE | `skills/registry.py` — `TOOL_DEFINITIONS`, `ROUTE_TOOLS`, `dispatch_tool()` — 11 tests |
| BSPDiagnosticAgent | DONE | `product/bsp_agent/agent.py` — Anthropic tool-use loop, Supervisor integration, route-based tool selection |
| SupervisorAgent → Claude | DONE | Migrated from Vertex AI to `claude-haiku-4-5-20251001` — 11 tests |
| `LogPayload.meminfo_content` fix | DONE | Correct schema; `logcat` and `/proc/meminfo` no longer conflated |
| Skill: `decode_esr_el1` | DONE | `skills/bsp_diagnostics/aarch64_exceptions.py` — 14 tests |
| Skill: `check_cache_coherency_panic` | DONE | `skills/bsp_diagnostics/aarch64_exceptions.py` — 17 tests |
| **Total product tests** | **107 passing** | |

### Phase 2 — Runnable & Validated (NEXT)

| # | Item | Priority | Notes |
|---|---|---|---|
| 5 | CLI entry point (`cli.py`) | High | `python cli.py --dmesg path --meminfo path` — makes the agent runnable without writing Python |
| 6 | End-to-end integration test | High | Feeds golden-set fixture logs through Supervisor → Agent (mocked LLM) — validates the full pipeline |
| 7 | Knowledge base docs (`docs/`) | Medium | `docs/memory-reclamation.md`, `docs/aarch64-exceptions.md` — domain context for the system prompt |

### Phase 3 — Expanded Domain Coverage (FUTURE)

| # | Item | Route | Notes |
|---|---|---|---|
| 8 | Skill: `check_vendor_boot_ufs_driver` | `hardware_advisor` | Detect UFS driver load failures during STD restore phase |
| 9 | Skill: `analyze_watchdog_timeout` | `kernel_pathologist` | Parse softlockup / hardlockup events from dmesg |
| 10 | Skill: `check_pmic_rail_voltage` | `hardware_advisor` | Extract and validate PMIC rail voltages from logcat/dmesg |
| 11 | Real-world log validation | — | Run against actual BSP logs; tune thresholds; document edge cases |

## Adding a New Skill

1. Create `skills/bsp_diagnostics/<skill_name>.py` with `Input`/`Output` Pydantic models and the pure function.
2. Write isolated pytest in `tests/product_tests/test_<skill_name>.py` — no LLM.
3. Register in `skills/registry.py` as an Anthropic-compatible tool.
4. Add a row to the skill table in `skills/SKILL.md` and in this file.
