## Summary

The `node_architect_gate()` function in `studio/subgraphs/engineer.py` does **not** limit the Architect to a single refactor attempt. This directly violates **AGENTS.md §1.1 — The Stability Protocol (Anti-Loop Mechanism)**, which states:

> *The Architect is allowed **ONE (1)** attempt to refactor a "Green" solution. If the refactored code fails the test (Red), the system **MUST** revert to the "Green" (messy but working) state. The reverted code is committed with a `#TODO: Tech Debt` tag.*

Without this limit the system can loop indefinitely on architect rejections, burning API calls and blocking the pipeline.

---

## Problem Details

```python
# studio/subgraphs/engineer.py — CURRENT (non-compliant)
def route_architect_gate(state: AgentState) -> Literal["end", "feedback_loop"]:
    if state["jules_metadata"].status == "COMPLETED":
        return "end"
    return "feedback_loop"   # no retry counter — loops forever
```

**Root causes:**
1. No state field tracking how many architect-driven refactor attempts have occurred.
2. No fallback rule: if refactor fails, the system must revert to the last Green state.
3. No `#TODO: Tech Debt` tagging mechanism when the fallback is applied.

---

## Required Fix (AGENTS.md §1.1)

- Add `architect_refactor_attempts: int = 0` to `JulesMetadata` in `studio/memory.py`.
- In `node_architect_gate()`:
  - On first rejection: increment `architect_refactor_attempts`, set `status = "FAILED"`, send refactor feedback.
  - On second rejection (`architect_refactor_attempts >= 1`): apply **Stability Protocol fallback** — set `status = "COMPLETED"`, append `#TODO: Tech Debt` note with deferred violations.
- Add `"APPROVED_WITH_TECH_DEBT"` to `ReviewVerdict.status` and a `tech_debt_tag` field to carry the note.

---

## 📜 Developer Checklist (MUST FOLLOW)

> ⚠️ This project operates under **AGENTS.md** as the supreme governing constitution. All changes **MUST** comply.

- [ ] **Follow TDD (AGENTS.md §1 — Prime Directive):**
  1. 🔴 **Red** — Write a failing test that verifies the Stability Protocol: after one rejected refactor, a second Architect rejection MUST result in `status = "COMPLETED"` (fallback to Green), **not** another loop.
  2. 🟢 **Green** — Add the `architect_refactor_attempts` counter and fallback logic to pass the test.
  3. 🔵 **Refactor** — Architect reviews the implementation for SOLID compliance.
- [ ] **Stay compliant with AGENTS.md §1.1:** The fallback must leave the system in a valid `COMPLETED` state with a `#TODO: Tech Debt` log entry — the pipeline must NOT be blocked.
- [ ] **Tests must cover:**
  - First architect rejection increments counter and sets `status = "FAILED"`.
  - Second architect rejection triggers fallback: `status = "COMPLETED"` + `#TODO: Tech Debt` tag.
  - Tech debt log entry contains the deferred violation details.
  - Clean approval (no violations) leaves counter at 0.

---

## References

- **AGENTS.md §1.1 — The Stability Protocol (Anti-Loop Mechanism)**
- **AGENTS.md §1 — The Prime Directive: TDD is Law**
- **Affected files:** `studio/subgraphs/engineer.py`, `studio/memory.py`, `studio/agents/architect.py`
- **Compliance audit finding:** FIX-002 (Priority 1 — CRITICAL)
- **Audit date:** 2026-02-25
