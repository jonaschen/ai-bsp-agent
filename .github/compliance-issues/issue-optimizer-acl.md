## Summary

The `OptimizerAgent` (in `studio/optimizer.py` and `studio/agents/optimizer.py`) currently writes output to `studio/_candidate/` **without any access-control checks**. This directly violates **AGENTS.md §4 — Data Sovereignty & Containment Protocol**, which states:

> *The Optimizer Agent MUST be executed in a container/sandbox where it has **Write Permission ONLY** to the `product/prompts/` directory. Any attempt to write to `studio/` must result in a `PermissionDenied` OS error.*

---

## Problem Details

```python
# studio/optimizer.py — CURRENT (non-compliant)
def apply_prompt_update(self, target_file_path: str, new_content: str):
    candidate_dir = Path("studio/_candidate")   # writes to studio/!
    candidate_path = candidate_dir / original_path.name
    os.makedirs(candidate_dir, exist_ok=True)   # no ACL check
    candidate_path.write_text(new_content)       # can write anywhere
```

**Root causes:**
1. No sandboxing container enforced.
2. No ACL checks — Optimizer will happily write to `studio/` or any other path.
3. No `PermissionError` raised on constraint violation.
4. Output destination hardcoded to `studio/_candidate/` instead of `product/prompts/`.

---

## Required Fix (AGENTS.md §4)

- Add an `ALLOWED_WRITE_PATH = Path("product/prompts").resolve()` constant.
- In `apply_prompt_update()`, resolve the target path and raise `PermissionError` if it falls outside `ALLOWED_WRITE_PATH`.
- Update `optimize_prompt()` to route output explicitly to `product/prompts/<filename>`.
- Add `write_prompt_file()` method with ACL guard to `studio/agents/optimizer.py`.

---

## 📜 Developer Checklist (MUST FOLLOW)

> ⚠️ This project operates under **AGENTS.md** as the supreme governing constitution. All changes **MUST** comply.

- [ ] **Follow TDD (AGENTS.md §1 — Prime Directive):**
  1. 🔴 **Red** — Write a failing test that covers the ACL violation (e.g., assert `PermissionError` is raised when writing to `studio/`).
  2. 🟢 **Green** — Implement the minimal ACL check to pass the test.
  3. 🔵 **Refactor** — Clean up per SOLID principles (the Architect will review).
- [ ] **Stay compliant with AGENTS.md §4:** The fix must raise a real OS-level `PermissionError` — not just log a warning.
- [ ] **Tests must cover:**
  - Writing to `studio/` raises `PermissionError`.
  - Writing to an arbitrary path raises `PermissionError`.
  - Writing to `product/prompts/` succeeds.

---

## References

- **AGENTS.md §4 — Data Sovereignty & Containment Protocol** (Point 4 — ACL Enforcement)
- **Affected files:** `studio/optimizer.py`, `studio/agents/optimizer.py`
- **Compliance audit finding:** FIX-001 (Priority 1 — CRITICAL)
- **Audit date:** 2026-02-25
