# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Prime Directive

**Follow `AGENTS.md` at all times.** It is the supreme governance document ("The Constitution"). Key rules:
- **TDD is Law**: Write a failing test first (Red), then minimal implementation (Green), then one refactor attempt. If refactor breaks tests, revert to Green and tag `#TODO: Tech Debt`.
- **State Sovereignty**: Only `StudioManager` writes to `studio_state.json`.
- **ESL-2**: Any change to `studio/` logic requires manual human review before merging.
- **Optimizer ACL**: The Optimizer may only write to `product/prompts/`. Writes to `studio/` must raise `PermissionError`.

## Commands

Run any tests and any git operations without asking for confirmation first.

Run tests:
```bash
source venv/bin/activate && python -m pytest
```

Run a single test file or function:
```bash
source venv/bin/activate && python -m pytest tests/test_orchestrator.py
source venv/bin/activate && python -m pytest tests/test_orchestrator.py::test_function_name
```

Run the Phase 2 simulation (end-to-end, uses mocked Vertex AI — no GCP credentials needed):
```bash
PYTHONPATH=. python tests/phase2_simulation.py
```

Run the factory (production):
```bash
sudo systemctl start docker && newgrp docker
source venv/bin/activate
PYTHONPATH=. python main.py run
```

Reset local state for a fresh factory run:
```bash
PYTHONPATH=. python main.py clean
```

`pytest.ini` sets `pythonpath = .`, so `PYTHONPATH=.` is only needed when running scripts directly (not pytest).

## Architecture

The system is a **Recursive Cognitive Software Factory** ("The Studio") that autonomously builds the **Android BSP Consultant** product. Two strict layers:

- **`studio/`** — The Factory: agents, orchestrator, governance. Never touched by the Optimizer.
- **`product/`** — The Product: the BSP Consultant agent being built. The Optimizer may only write to `product/prompts/`.

### Core Runtime Files

| File | Role |
|---|---|
| `main.py` | Entry point. Loads state, runs `Orchestrator.app.ainvoke()` with SQLite checkpointer. |
| `studio/orchestrator.py` | LangGraph `StateGraph`. Defines the top-level PLAN→EXECUTE→REVIEW→EVOLVE lifecycle. |
| `studio/manager.py` | `StudioManager` — sole owner of `studio_state.json` persistence (atomic writes via `os.replace`). |
| `studio/memory.py` | All Pydantic state models: `StudioState`, `OrchestrationState`, `EngineeringState`, `JulesMetadata`, `Ticket`, etc. |
| `studio/subgraphs/engineer.py` | Engineer micro-loop subgraph: `task_dispatcher → watch_tower → entropy_guard → qa_verifier → architect_gate → feedback_loop`. |
| `studio/config.py` | `Settings` via `pydantic-settings`. Reads `.env`. Auto-detects pytest and sets `jules_poll_interval=0.1s` (vs 600s in production). |

### Agent Files

| File | Role |
|---|---|
| `studio/agents/architect.py` | Reviews full file source against `AGENTS.md` (hashed for integrity). Uses Gemini-2.5-Pro. Gatekeeper in engineer subgraph. |
| `studio/agents/product_owner.py` | Reads `PRODUCT_BLUEPRINT.md`, generates a topologically-sorted DAG of `Ticket` objects via networkx. |
| `studio/agents/scrum_master.py` | Retrospective analysis at sprint end. Triggers Optimizer if failures detected. |
| `studio/agents/optimizer.py` | OPRO: patches `product/prompts/prompts.json` inside `OptimizerSandbox` (Docker, write-only to `product/prompts/`). |

### Utility Files

| File | Role |
|---|---|
| `studio/utils/entropy_math.py` | `SemanticEntropyCalculator` + `VertexFlashJudge`. Measures semantic uncertainty (SE). SE > threshold → circuit breaker. |
| `studio/utils/sandbox.py` | `DockerSandbox` (QA), `SecureSandbox` (no network), `OptimizerSandbox` (write-only mount to `product/prompts/`). |
| `studio/utils/jules_client.py` | `JulesGitHubClient` — dispatches GitHub Issues for Jules, polls PR status, posts feedback, merges PRs. |
| `studio/utils/git_utils.py` | `checkout_pr_branch()` and `sync_main_branch()` — run git commands on the host repo. |
| `studio/utils/patching.py` | `apply_virtual_patch()` and `extract_affected_files()` — applies unified diffs in-memory using `unidiff` + `patch`. |
| `studio/utils/acl.py` | `verify_write_permission()` — enforces Optimizer can only write to `product/prompts/`. |
| `studio/utils/prompts.py` | `fetch_system_prompt()` / `update_system_prompt()` — reads/writes `product/prompts/prompts.json`. |

### Orchestration Flow

```
START → intent_router → (SPRINT) → product_owner → sprint_planning → backlog_dispatcher
                                                                             ↓ (next ticket)
                                                             context_slicer → engineer_subgraph
                                                                             ↓ (healthy)
                                                             backlog_dispatcher ← (loop)
                                                                             ↓ (backlog empty)
                                                                       scrum_master → END
```

Engineer subgraph internal flow:
```
task_dispatcher → watch_tower → entropy_guard → qa_verifier → architect_gate → END (approved)
      ↑                ↑ (WORKING)       ↓ (tunneling)          ↓ (fail)          ↓ (violations)
      └────────────────────────────── feedback_loop ──────────────────────────────┘
```

### Key Design Invariants

- **Context Slicing**: Agents receive only a `ContextSlice` (filtered files + last 500 log lines), not the full state. Prevents context collapse.
- **Semantic Entropy (SE) Circuit Breaker**: `VertexFlashJudge` scores agent output uncertainty 0–10. SE > 7.0 triggers circuit breaker and halts. ⚠️ *Known issue: max possible SE with N=5 samples is 2.32 — threshold is unreachable. See `issues.md` ISSUE-03.*
- **Stability Protocol** (`AGENTS.md §1.1`): Architect gets exactly one refactor attempt. If refactor breaks tests, revert to Green and tag `#TODO: Tech Debt`.
- **ESL-1 vs ESL-2**: Product evolution (`product/*`) is automatic. Studio evolution (`studio/*`) requires manual human review.
- **`jules_meta` dual-type**: `EngineeringState.jules_meta` is stored as `Dict` for LangGraph serialization but read as `JulesMetadata`. Every node must handle both types via `JulesMetadata(**raw) if isinstance(raw, dict) else raw`.

### Configuration

Settings loaded via `studio/config.py` using `pydantic-settings`. Source from `.env` or environment variables:
- `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_REGION` (not `PROJECT_ID` or `LOCATION` — old names not read)
- `GITHUB_TOKEN`, `GITHUB_REPOSITORY`, `JULES_USERNAME`
- `VECTOR_SEARCH_INDEX_ID`, `VECTOR_SEARCH_ENDPOINT_ID`, `VECTOR_SEARCH_GCS_BUCKET` (optional)

Default models: `thinking_model = "gemini-2.5-pro"`, `doing_model = "gemini-2.5-flash"`.

### State Persistence

- `studio_state.json` — runtime state (single source of truth, written atomically by `StudioManager`)
- `studio_state.seed.json` — initial seed loaded on first run if `studio_state.json` absent
- `studio_checkpoints.db` — SQLite LangGraph checkpoint DB (crash recovery)

### Known Friction Points

See `issues.md` for a full diagnosis. Most critical before autopilot operation:
- **ISSUE-01**: Context slicer is a hardcoded mock (always returns `drivers/gpu/msm/mdss.c`)
- **ISSUE-03**: SE circuit breaker threshold (7.0) is mathematically unreachable (max ≈ 2.32)
- **ISSUE-04**: WatchTower has no polling timeout — can loop forever if Jules never creates a PR
- **ISSUE-05**: PO agent crashes the graph on LLM failure (raises instead of returning empty)
- **ISSUE-08**: Factory stops after one batch of 3 tickets — requires manual restart for large blueprints
