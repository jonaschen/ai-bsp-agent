# Contributing to Android BSP Diagnostic Expert

Thank you for your interest in improving the tool. This project is currently in **alpha**, and real-hardware feedback is exactly what drives the roadmap.

---

## Table of Contents

1. [Ways to contribute](#1-ways-to-contribute)
2. [Reporting a skill miss or gap](#2-reporting-a-skill-miss-or-gap)
3. [Development environment setup](#3-development-environment-setup)
4. [Project architecture at a glance](#4-project-architecture-at-a-glance)
5. [Adding a new Skill](#5-adding-a-new-skill)
6. [Adding a new Supervisor route](#6-adding-a-new-supervisor-route)
7. [Extending an existing skill at runtime](#7-extending-an-existing-skill-at-runtime)
8. [Testing conventions](#8-testing-conventions)
9. [Code style](#9-code-style)
10. [Pull-request checklist](#10-pull-request-checklist)
11. [What NOT to touch](#11-what-not-to-touch)

---

## 1. Ways to contribute

| Contribution type | How |
|---|---|
| Report a skill miss on real hardware | [Open a GitHub Issue](#2-reporting-a-skill-miss-or-gap) |
| Extend a skill for your SoC format | Use the [runtime extension workflow](#7-extending-an-existing-skill-at-runtime) first; then open a PR to promote it to a built-in pattern |
| Add a new diagnostic skill | Follow [§5 Adding a new Skill](#5-adding-a-new-skill) |
| Improve documentation | Edit `README.md`, `docs/`, or `QUICKSTART.md`; no test required |
| Report a crash or unhandled exception | Open a GitHub Issue with the full stack trace and the log that triggered it |

---

## 2. Reporting a skill miss or gap

When a skill returns `failure_detected: false` or `confidence < 0.5` for a log you know is a real failure, open an issue with:

1. **The log snippet** — paste the relevant lines (redact serial numbers / IP addresses / proprietary firmware names as needed).
2. **The skill output** — run `python cli.py --dmesg <log> --output result.json` and attach `result.json`.
3. **Expected behaviour** — describe what the agent *should* have detected.
4. **SoC / board** — e.g. `Qualcomm SM8550`, `MediaTek MT6985`, `Samsung Exynos 2400`.

See `docs/emulator-spec.md §5 (Known Emulator Gaps)` — if your pattern class is listed there, it is a *known* gap and the preferred fix is the runtime extension workflow (§7) first.

---

## 3. Development environment setup

```bash
# Clone
git clone https://github.com/jonaschen/ai-bsp-agent.git
cd ai-bsp-agent

# Python 3.11+ is required (pyproject.toml enforces this)
python3 -m venv venv
source venv/bin/activate

# Install all dependencies (includes mcp, anthropic, pydantic, pytest)
pip install -r requirements.txt

# Verify: run the full isolated test suite (no API key needed)
python -m pytest tests/product_tests/ -q
# Expected: 539 passed
```

Set `ANTHROPIC_API_KEY` only when you need to run the agent end-to-end or the CLI:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

---

## 4. Project architecture at a glance

```
The Brain (agent.py + supervisor.py)
    │  calls
    ▼
The Skill Registry (skills/registry.py)
    │  dispatches to
    ▼
Pure Python Skills (skills/bsp_diagnostics/*.py)
    │  tested by
    ▼
Isolated pytest suite (tests/product_tests/)
```

**Key rule — Skills must be pure functions.** No LLM calls, no I/O, no global state inside a skill. The one exception is `suggest_pattern_improvement`, which intentionally writes to `~/.bsp-diagnostics/skill_extensions.json` — this is its documented purpose.

See `AGENTS.md` for the full architecture constitution and `CLAUDE.md` for the development roadmap.

---

## 5. Adding a new Skill

Follow **TDD — write the failing test first** (Red → Green → one refactor attempt).

### Step 1 — Write the skill module

Create `skills/bsp_diagnostics/<skill_name>.py`:

```python
from pydantic import BaseModel
from skills.extensions import load_extensions

class MySkillInput(BaseModel):
    dmesg_log: str

class MySkillOutput(BaseModel):
    failure_detected: bool
    error_type: str        # e.g. "my_error_class" or "none"
    root_cause: str
    recommended_action: str
    confidence: float      # 0.0–1.0

def my_new_skill(dmesg_log: str) -> MySkillOutput:
    """
    One-line summary of what this skill detects.

    Returns MySkillOutput with failure_detected=True when <condition>.
    confidence thresholds: 0.85 high-confidence pattern; 0.70 probable.
    """
    # ... detection logic ...

    # Standard no-detection return with extension hook
    extensions = load_extensions().get("skills", {}).get("my_new_skill", {})
    for pattern in extensions.get("patterns", []):
        import re
        if re.search(pattern["match"], dmesg_log, re.IGNORECASE):
            return MySkillOutput(
                failure_detected=True,
                error_type=pattern["category"],
                root_cause=f"[user pattern] {pattern['description']}",
                recommended_action="Check vendor-specific documentation.",
                confidence=0.60,
            )

    return MySkillOutput(
        failure_detected=False,
        error_type="none",
        root_cause="No known failure pattern detected.",
        recommended_action="",
        confidence=0.0,
    )
```

### Step 2 — Write the pytest

Create `tests/product_tests/test_<skill_name>_skill.py`:

```python
"""Tests for my_new_skill — no LLM calls, no I/O."""
import pytest
from skills.bsp_diagnostics.<skill_name> import my_new_skill

KNOWN_FAILURE_LOG = """
<paste a representative failure snippet here>
"""

CLEAN_LOG = """
<log with no failure>
"""

class TestMyNewSkillDetection:
    def test_detects_known_failure(self):
        result = my_new_skill(KNOWN_FAILURE_LOG)
        assert result.failure_detected is True
        assert result.confidence >= 0.70

    def test_clean_log_no_false_positive(self):
        result = my_new_skill(CLEAN_LOG)
        assert result.failure_detected is False
        assert result.confidence == 0.0
```

Run just your test file to iterate quickly:

```bash
source venv/bin/activate
python -m pytest tests/product_tests/test_<skill_name>_skill.py -v
```

### Step 3 — Register in `skills/registry.py`

Add three entries:

1. **`TOOL_DEFINITIONS`** — Anthropic-compatible tool definition dict.
2. **`_DISPATCH_TABLE`** — maps tool name string → Python function.
3. **`ROUTE_TOOLS`** — add the tool name to the appropriate supervisor route set.

### Step 4 — Update `skills/SKILL.md`

Add a row to the current-skills table in `skills/SKILL.md`.

### Step 5 — Update `README.md`

Add a row to the relevant route section in the **Diagnostic Skills** tables.

---

## 6. Adding a new Supervisor route

1. Add the new route token string to `product/bsp_agent/agents/supervisor.py` — both the triage prompt and the short-circuit regex (if applicable).
2. Add a `_is_<route>_log()` function for deterministic short-circuit (bypasses LLM); fall back to the LLM Haiku token for ambiguous cases.
3. Add `ROUTE_TOOLS["<new_route>"]` in `skills/registry.py`.
4. Add an integration-test fixture scenario in `tests/product_tests/test_integration.py`.

---

## 7. Extending an existing skill at runtime

When a skill misses your hardware's log format, use the two built-in improvement skills before opening a code PR:

```
1. validate_skill_extension  — dry-run: tests your regex without writing anything
2. suggest_pattern_improvement — validates (4 gates) then writes to
                                  ~/.bsp-diagnostics/skill_extensions.json
```

After the extension is written, re-run the agent — the skill picks it up automatically with `confidence=0.60` and a `[user pattern]` prefix in `root_cause`.

If the pattern is stable and generalises to the open-source log format (not proprietary), consider promoting it to a built-in pattern by opening a PR that adds it directly to the skill's detection logic.

See `docs/skill-extension-guide.md` for the full walkthrough.

---

## 8. Testing conventions

| Rule | Detail |
|---|---|
| **No LLM in unit tests** | Every test in `tests/product_tests/` must be fully deterministic; mock any `anthropic.Anthropic` call with `unittest.mock` |
| **TDD** | Write the failing test first (Red), then minimal implementation (Green), then one refactor attempt; if refactor breaks tests, revert to Green and tag `#TODO: Tech Debt` |
| **Test file naming** | `tests/product_tests/test_<skill_name>_skill.py` |
| **Fixture data** | Log fixtures go in `tests/product_tests/fixtures/` or inline as module-level constants |
| **Run tests** | `python -m pytest tests/product_tests/ -q` — must be 539+ passed with 0 failures |
| **Integration tests** | The mocked end-to-end tests live in `tests/product_tests/test_integration.py`; add a fixture scenario for any new supervisor route |

---

## 9. Code style

- Python 3.11+
- Pydantic v2 for all Skill `Input`/`Output` schemas
- No external dependencies beyond what is in `requirements.txt` — open an issue before adding a new package
- Type-annotate all function signatures
- Keep skills short: one function, one concern
- Do **not** add logging, print statements, or `sys.exit` inside a skill

---

## 10. Pull-request checklist

Before opening a PR, confirm:

- [ ] `python -m pytest tests/product_tests/ -q` — 0 failures
- [ ] New skill: has Pydantic `Input`/`Output` models, a pure function, and a pytest file
- [ ] New skill: registered in `skills/registry.py` (`TOOL_DEFINITIONS`, `_DISPATCH_TABLE`, `ROUTE_TOOLS`)
- [ ] New skill: row added to `skills/SKILL.md` and `README.md`
- [ ] New skill: extension hook present (see the `load_extensions()` pattern in §5)
- [ ] No changes to `AGENTS.md`, `studio/subgraphs/engineer.py`, or `studio/utils/sandbox.py`
- [ ] PR description includes the log snippet that triggered the change and the before/after skill output

---

## 11. What NOT to touch

| Path | Reason |
|---|---|
| `AGENTS.md` | Architecture constitution — read-only by design |
| `studio/subgraphs/engineer.py` | Deprecated legacy factory — do not modify |
| `studio/utils/sandbox.py` | Deprecated legacy factory — do not modify |
| `~/.bsp-diagnostics/skill_extensions.json` | User-local; never committed to the repo |

---

## Questions?

Open a GitHub Issue or start a Discussion. Alpha feedback — including "this didn't work at all" — is the most valuable contribution at this stage.
