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
- `product/bsp_agent/agents/supervisor.py` — `SupervisorAgent` (Claude Haiku): triages dmesg and routes to one of the registered route tokens. Performs event-horizon chunking for large logs. Current routes: `kernel_pathologist`, `hardware_advisor`, `clarify_needed`. Planned additions: `early_boot_advisor` (Phase 4), `android_init_advisor` (Phase 6), `source_analyst` (Phase 8).
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
| `skills/bsp_diagnostics/vendor_boot.py` | `check_vendor_boot_ufs_driver(dmesg_log)` | `hardware_advisor` | UFS Driver / STD Restore |
| `skills/bsp_diagnostics/watchdog.py` | `analyze_watchdog_timeout(dmesg_log)` | `kernel_pathologist` | Watchdog / Soft+Hard Lockup |
| `skills/bsp_diagnostics/pmic.py` | `check_pmic_rail_voltage(dmesg_log, logcat_log)` | `hardware_advisor` | PMIC Rail Voltages |

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
| CLI entry point | DONE | `cli.py` — `python cli.py --dmesg <path> [--meminfo <path>] [--output <path>]` |
| End-to-end integration test | DONE | `tests/product_tests/test_integration.py` — 25 tests, 3 fixture scenarios |
| Knowledge base docs | DONE | `docs/memory-reclamation.md`, `docs/aarch64-exceptions.md` |

### Phase 3 — Expanded Domain Coverage (DONE) ✓

| # | Item | Status | Deliverable |
|---|---|---|---|
| 8 | Skill: `check_vendor_boot_ufs_driver` | DONE | `skills/bsp_diagnostics/vendor_boot.py` — 16 tests; phase-classified (probe/link_startup/resume) |
| 9 | Skill: `analyze_watchdog_timeout` | DONE | `skills/bsp_diagnostics/watchdog.py` — 19 tests; soft/hard lockup, RCU stall, call trace extraction |
| 10 | Skill: `check_pmic_rail_voltage` | DONE | `skills/bsp_diagnostics/pmic.py` — 19 tests; OCP + undervoltage detection, rpm-smd/qpnp/generic formats |
| 11 | Real-world log validation | FUTURE | Run against actual BSP logs; tune thresholds; document edge cases |
| **Total product tests** | **231 passing** | |

### Phase 4 — Early Boot Skills (NEXT)

New supervisor route: `early_boot_advisor`. Trigger: no kernel timestamp pattern in log; TF-A/LK boot markers present.

| Deliverable | Detail |
|---|---|
| `skills/bsp_diagnostics/early_boot.py` | `parse_early_boot_uart_log`, `analyze_lk_panic` |
| `tests/product_tests/test_early_boot_skill.py` | ~18 tests |
| Supervisor update | Add `early_boot_advisor` to triage prompt + `ROUTE_TOOLS` |
| `docs/early-boot-stages.md` | TF-A BL1/BL2 error codes, LK assert format |

### Phase 5 — Kernel Exception & Oops Skills (PLANNED)

Extends `kernel_pathologist` route. No new supervisor route needed.

| Deliverable | Detail |
|---|---|
| `skills/bsp_diagnostics/kernel_oops.py` | `extract_kernel_oops_log` — stateless hex call trace extractor |
| Update `skills/bsp_diagnostics/aarch64_exceptions.py` | Add `decode_aarch64_exception(esr_val, far_val)` — extends `decode_esr_el1` with FAR field; EL inferred from EC bits, no `el_level` input |
| Tests | ~24 new tests |
| Update `docs/aarch64-exceptions.md` | FAR field layout and fault address interpretation |

### Phase 6 — Android Init Skills (PLANNED)

New supervisor route: `android_init_advisor`. Trigger: SELinux AVC lines, init.rc service failures, `[FAILED]` markers.

| Deliverable | Detail |
|---|---|
| `skills/bsp_diagnostics/android_init.py` | `analyze_selinux_denial`, `check_android_init_rc` |
| `tests/product_tests/test_android_init_skill.py` | ~20 tests |
| Supervisor update | Add `android_init_advisor` to triage prompt + `ROUTE_TOOLS` |
| `docs/android-init.md` | SELinux type enforcement, init.rc service lifecycle |

### Phase 7 — Subsystem Diagnostics (PLANNED)

Log-only variants. `fstab_path` input becomes `fstab_content: str` — no filesystem access required.

| Deliverable | Detail |
|---|---|
| `skills/bsp_diagnostics/subsystems.py` | `check_clock_dependencies`, `diagnose_vfs_mount_failure`, `analyze_firmware_load_error`, `analyze_early_oom_killer` |
| `tests/product_tests/test_subsystems_skill.py` | ~24 tests |
| `docs/subsystem-boot.md` | CCF probe defer patterns, VFS mount error codes, firmware search paths |

### Phase 8 — Stateful Workspace Skills (PLANNED — infrastructure decision required)

New supervisor route: `source_analyst`. Trigger: regression/commit/DTS-change keywords.

**Before coding:** Agree on workspace access model (see `ANDROID_LINUX_BSP_BOOTING_SKILL_SETS.md` §6 Phase 8).
Recommended start: Option A — file path inputs; `resolve_oops_symbols` calls `addr2line` via subprocess.

| Deliverable | Detail |
|---|---|
| `skills/bsp_diagnostics/workspace.py` | `resolve_oops_symbols`, `compare_device_tree_nodes`, `diff_kernel_configs`, `validate_gpio_pinctrl_conflict` |
| `tests/product_tests/test_workspace_skill.py` | ~20 tests — mock subprocess for `addr2line` |
| Supervisor update | Add `source_analyst` route |
| `docs/workspace-analysis.md` | DTS node naming conventions, CONFIG flag impact reference |

**Note:** `resolve_oops_symbols` depends on hex trace output from Phase 5 `extract_kernel_oops_log`.

### Phase 9a — SoC Errata Lookup (PLANNED)

| Deliverable | Detail |
|---|---|
| `skills/knowledge/errata.py` | `check_soc_errata_tracker` — static dict keyed by `(ip_block, soc_revision)`; covers Qualcomm SM8x50, MTK MT6xxx, Samsung Exynos |
| `tests/product_tests/test_errata_skill.py` | ~12 tests |

### Phase 9b — ARM TRM RAG (DEFERRED)

Requires vector DB + embedding pipeline. Start only after Phase 9a is validated in real use and RAG infrastructure design is complete.

### Phase 10 — Governed Actions (DEFERRED)

`generate_patch_and_build` with HITL blocking approval gate. Start only after Phases 4–7 are validated on real BSP logs — diagnostic accuracy must be high before actions are enabled.

---

## Adding a New Skill

1. Create `skills/bsp_diagnostics/<skill_name>.py` with `Input`/`Output` Pydantic models and the pure function.
2. Write isolated pytest in `tests/product_tests/test_<skill_name>.py` — no LLM.
3. Register in `skills/registry.py` as an Anthropic-compatible tool.
4. Add a row to the skill table in `skills/SKILL.md` and in this file.

## Adding a New Supervisor Route

1. Add the new route token string to the supervisor triage prompt in `product/bsp_agent/agents/supervisor.py`.
2. Add the route and its trigger keywords to the supervisor's routing decision logic.
3. Add an entry in `ROUTE_TOOLS` in `skills/registry.py` mapping the route token to the set of tool names.
4. Update integration tests in `tests/product_tests/test_integration.py` with a fixture scenario for the new route.
