# Autopilot Friction Point Diagnosis

**Date:** 2026-03-06
**Scope:** Full static analysis of `studio/`, `main.py`, all `tests/` files, and supporting modules for autopilot readiness.

Issues are grouped by category and severity. Each entry includes: symptom, root cause, exact file/line reference, and recommended fix.

---

## PART 1 — TEST SUITE ISSUES (Immediate Danger to Local State)

These test bugs are the most urgent because running the test suite modifies the host git repository and can destroy uncommitted local work.

---

### TEST-01 🔴 CRITICAL: Tests Invoke Real `sync_main_branch()` — Destroys Uncommitted Changes

**Files (confirmed missing patch, COMPLETED outcome):**
- `tests/test_context_slicing.py`
- `tests/test_tdd_loop.py`
- `tests/test_architect_veto.py`
- `tests/test_router_diversion.py` (function `test_router_case_a_coding_with_log`)
- `tests/test_lifecycle_manager.py`

**Symptom:** When any of these tests run, `sync_main_branch()` is called on the live host repository. This executes `git stash` (silently hiding local changes), `git reset --hard origin/main`, and `git clean -fd`. Changes that have not been pushed to upstream are lost in the stash with no `git stash pop` to restore them.

**Root cause (shared):** Each test invokes the full Orchestrator graph via `orchestrator.app.ainvoke(state)` and the mock engineer returns at least one ticket with `status="COMPLETED"`. This causes `node_backlog_dispatcher` (`orchestrator.py:222`) to call `await asyncio.to_thread(sync_main_branch)`. All five tests are missing `@patch("studio.orchestrator.sync_main_branch")`.

Specific triggering paths:
- `test_context_slicing.py` — mock engineer returns `status="COMPLETED"` for the one ticket
- `test_tdd_loop.py` — second QA pass returns `status="COMPLETED"`, propagated via `_engineer_wrapper`
- `test_architect_veto.py` — architect approves, task completes as `COMPLETED`
- `test_router_diversion.py::test_router_case_a_coding_with_log` — mock engineer returns `status="COMPLETED"`
- `test_lifecycle_manager.py` — TKT-1 completes as `COMPLETED` (TKT-2 fails, but the first task already triggered the call)

**Fix:** Add `@patch("studio.orchestrator.sync_main_branch")` to all five tests. Establish it as a project-wide convention: any test that invokes the Orchestrator full graph MUST patch both `sync_main_branch` and (where `current_branch` is set) `checkout_pr_branch`.

---

### TEST-02 🔴 CRITICAL: `test_recovery.py` Deletes and Overwrites Production State Files

**File:** `tests/test_recovery.py:18-25`
**Symptom:** The test unconditionally deletes `studio_state.json` and `studio_checkpoints.db` from the project root — the same files the running factory depends on. After deletion it creates a new `StudioManager()` and saves a test state ("RECOVERY-TEST"), overwriting any real sprint progress.

**Root cause:** The test uses `STATE_FILE` and `CHECKPOINT_DB` constants imported directly from `main.py`, which point to the project root. No isolation is applied.

**Fix:** Use pytest's `tmp_path` fixture and `monkeypatch` to redirect file paths:
```python
def test_recovery_logic(tmp_path, monkeypatch):
    monkeypatch.setattr("main.STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr("main.CHECKPOINT_DB", str(tmp_path / "checkpoints.db"))
```
This ensures all file operations are scoped to a temporary directory that pytest cleans up automatically.

---

### TEST-03 🟠 HIGH: `test_issue_01_gcp_config.py` Hard-Fails Without a `.env` File

**File:** `tests/test_issue_01_gcp_config.py:25-31`
**Symptom:** `test_env_uses_google_cloud_region_not_location` unconditionally opens `.env` with `open(env_path)`. On a fresh checkout or CI environment where `.env` is not committed, this raises `FileNotFoundError` and the entire test module fails to collect, blocking all other tests in the file.

**Root cause:** No existence guard before opening the file.

**Fix:** Add a `pytest.skip` guard:
```python
if not os.path.exists(env_path):
    pytest.skip(".env file not present — skipping env key validation")
```

---

### TEST-04 🟠 HIGH: `test_tdd_loop.py` Missing `checkout_pr_branch` Patch (Latent Risk)

**File:** `tests/test_tdd_loop.py`
**Symptom:** The test does not patch `studio.subgraphs.engineer.checkout_pr_branch`. Currently safe because `WorkStatus(status="COMPLETED")` does not set `branch_name`, so `jules_data.current_branch` is `None` and the `if jules_data.current_branch:` guard in `node_qa_verifier` prevents the call. However, if a future test variant uses `REVIEW_READY` status with a `branch_name`, this will silently trigger a real `git checkout` on the host.

**Fix:** Add the patch defensively: `patch("studio.subgraphs.engineer.checkout_pr_branch")`. This makes the test's isolation contract explicit and protects against future regressions.

---

### TEST-05 🟠 HIGH: `test_qa_verifier_infra.py` Patches `os.path.exists` Globally — Side Effects on Other Modules

**File:** `tests/test_qa_verifier_infra.py:31`
**Symptom:** `patch("os.path.exists")` replaces the built-in `os.path.exists` globally for the duration of the test. Any other code executing in the same process (including LangGraph internals, other pytest fixtures, or threading) will use the mocked version. This can cause confusing failures in unrelated tests running in the same session.

**Fix:** Scope the patch to the specific module: `patch("studio.subgraphs.engineer.os.path.exists")`. This only replaces `os.path.exists` as seen by the engineer subgraph module, leaving all other modules unaffected.

---

### TEST-06 🟡 MEDIUM: `test_garbage_folder_prevention.py` File Cleanup Not in `finally`

**File:** `tests/test_garbage_folder_prevention.py:133-134`
**Symptom:** `tests/new_valid_test.py` is created during the test and cleaned up at the end of the test body. If an assertion fails before the cleanup line, the file is left on disk, polluting the repository and potentially causing unrelated test failures (e.g., pytest auto-discovers it as a test file).

**Fix:** Wrap the test body in `try/finally`:
```python
try:
    result = await node_task_dispatcher(state)
    # assertions...
finally:
    if os.path.exists("tests/new_valid_test.py"):
        os.remove("tests/new_valid_test.py")
```
Or use `tmp_path` to scope all file creation to a temp directory.

---

### TEST-07 🟡 MEDIUM: `test_engineer_dynamic_fixes.py` Creates Real Files in Project CWD

**File:** `tests/test_engineer_dynamic_fixes.py:89-125`
**Symptom:** `test_qa_verifier_dynamic_sandbox_sync` creates `sync_test.py` directly in the project working directory, not in a temp location. The `finally` block cleans it up, but the file is visible to the git index during the test run and could trigger unexpected behavior (e.g., accidental `git add .` in another terminal).

**Fix:** Use `tmp_path` and `monkeypatch.chdir(tmp_path)` to isolate file operations, or move the file creation into a pytest `tmpdir`-scoped fixture.

---

### TEST-08 🟡 MEDIUM: Inconsistent `asyncio.run()` vs `@pytest.mark.asyncio` Pattern

**Files:** `tests/test_orchestrator.py`, `tests/test_context_slicing.py`, `tests/test_lifecycle_manager.py`
**Symptom:** Some tests use `asyncio.run(orchestrator.app.ainvoke(state))` inside synchronous test functions decorated with `@patch`. Others use `@pytest.mark.asyncio` with `await`. The `asyncio.run()` pattern creates a new event loop per call, which can conflict with `pytest-asyncio`'s event loop management when mixing both patterns in the same test session (especially with `scope="session"` or `scope="module"` asyncio modes).

**Fix:** Standardize on `@pytest.mark.asyncio` with `async def test_*`. Replace `asyncio.run(...)` calls with `await ...`. Stack `@patch` decorators above `@pytest.mark.asyncio`.

---

### TEST-09 🟡 MEDIUM: `test_cognitive_tunneling.py` Missing `sync_main_branch` Patch (Latent Risk)

**File:** `tests/test_cognitive_tunneling.py`
**Symptom:** The test currently terminates with `status="FAILED"` (circuit breaker triggered, `max_retries=0`), so `sync_main_branch` is never reached. But the mock is absent. If test parameters change (e.g., `max_retries=1` and the second attempt succeeds), the test would suddenly call real git operations without warning.

**Fix:** Add `patch("studio.orchestrator.sync_main_branch")` to the patch context manager for defensive isolation.

---

## PART 2 — CRITICAL PRODUCTION BLOCKERS (System Cannot Run Autonomously)

---

### PROD-01 🔴 CRITICAL: Context Slicer Is a Hardcoded Mock

**File:** `studio/orchestrator.py:453-454`
**Symptom:** Every engineering task receives identical fake context: `{"drivers/gpu/msm/mdss.c": "void main() { ... }"}`. Jules has no real information about what to build or fix. Every dispatched task is effectively blind.

**Root cause:** `slice_context()` contains a TODO comment: _"In a real app, we would query a VectorDB here"_. The ChromaDB integration in `product/bsp_agent/core/vector_store.py` exists but is never called.

**Fix:** Replace the hardcoded dict with a real query to the ChromaDB vector store using the current ticket's `title + description` as the query string. Extract actual project file paths from the results. Fall back to `["README.md"]` only if the vector store returns nothing.

---

### PROD-02 🔴 CRITICAL: SE Circuit Breaker Threshold Is Mathematically Unreachable

**File:** `studio/utils/entropy_math.py:27-30`
**Symptom:** The cognitive safety circuit breaker never fires based on real entropy calculations. The system believes it has a hallucination guardrail but it is permanently disabled.

**Root cause:** `ENTROPY_THRESHOLD = 7.0`, but with `DEFAULT_SAMPLE_SIZE = 5`, the maximum possible Shannon entropy is `log₂(5) ≈ 2.32`. The code's own comment confirms this: _"For N=5, max entropy is log2(5) ~= 2.32"_. No real output will ever exceed 7.0.

**Fix:** Change `ENTROPY_THRESHOLD` to `1.5` (≈65% of max entropy for N=5, indicating genuine semantic divergence). Update the comment. Update affected tests that check `threshold=7.0` in `SemanticHealthMetric` assertions.

---

### PROD-03 🔴 CRITICAL: WatchTower Has No Poll Timeout — Infinite Loop Risk

**File:** `studio/subgraphs/engineer.py:780-791`
**Symptom:** If Jules never creates a PR (e.g., GitHub issue is ignored, Jules is down, or the repo has branch protection that blocks PR creation), `route_watch_tower` returns `"watch_tower"` indefinitely. With `jules_poll_interval = 600s` in production, this loops silently until LangGraph's recursion limit (100) is exhausted, which itself takes 600 × 100 = 60,000 seconds (16+ hours).

**Root cause:** `JulesMetadata` has `retry_count`/`max_retries` for functional failures, but the WatchTower polling loop has no independent counter or wall-clock timeout.

**Fix:** Add `watch_count: int = 0` and `max_watch_polls: int = 20` to `JulesMetadata`. Increment `watch_count` in `node_watch_tower`. When `watch_count >= max_watch_polls`, set `status = "FAILED"` with a log message like _"Polling timeout — Jules did not produce a PR within 20 polls"_ and return, routing to `feedback_loop`.

---

### PROD-04 🔴 CRITICAL: PO Agent Crashes the Entire Graph on Any LLM Failure

**File:** `studio/agents/product_owner.py:99-101`
**Symptom:** Any transient Vertex AI error (rate limit, quota exhaustion, network timeout) during blueprint analysis propagates as an unhandled exception through `node_product_owner`, crashing the entire LangGraph run with no recovery.

**Root cause:** `analyze_specs()` does `raise e` on all exceptions. `node_product_owner` uses `asyncio.to_thread(run_po_cycle, ...)` without a try/except.

**Fix:** Wrap the `run_po_cycle` call in `node_product_owner` in a try/except:
```python
try:
    new_tickets = await asyncio.to_thread(run_po_cycle, state_dict)
except Exception as e:
    self.logger.error(f"PO cycle failed: {e}. Proceeding with existing backlog.")
    new_tickets = []
```
Also change `analyze_specs()` to return an empty `BlueprintAnalysis` on failure instead of re-raising.

---

### PROD-05 🔴 CRITICAL: Factory Stops After One Batch of 3 Tickets — Requires Manual Restart

**File:** `studio/orchestrator.py:154-180`, `main.py`
**Symptom:** After the sprint backlog is exhausted, the graph routes to `scrum_master` and then `END`. Even if `task_queue` still has hundreds of unprocessed tickets, the factory stops completely. Each subsequent batch requires a manual `python main.py run`.

**Root cause:** `node_sprint_planning` moves only 3 tickets into `sprint_backlog` and is never re-invoked after the sprint completes. The outer graph has no "refill sprint and continue" loop.

**Fix:** Add a conditional edge from `scrum_master`: if `state.orchestration.task_queue` has remaining OPEN tickets, route back to `sprint_planning` instead of `END`. This creates a true continuous autopilot loop across sprint boundaries.

---

### PROD-06 🔴 CRITICAL: `git_utils.py` Runs Destructive Commands on the Host Repo

**File:** `studio/utils/git_utils.py:6-87`
**Symptom:** `checkout_pr_branch()` and `sync_main_branch()` run `git stash`, `git reset --hard`, and `git clean -fd` on the repository where the studio code lives. In autopilot mode, this destroys any in-progress work on the host. The stash is never popped.

**Root cause:** The QA verifier was refactored from virtual-patching-in-Docker to checkout-on-host, but the host repo is also the studio's own working directory.

**Fix:** Use `git worktree add` to create a dedicated worktree for QA operations:
```bash
git worktree add /tmp/studio-qa-worker <branch>
```
The QA verifier runs tests inside this isolated worktree. The main repo is never touched. Remove `sync_main_branch` from the task completion flow; the worktree can simply be torn down after QA.

---

### PROD-07 🔴 CRITICAL: `StudioState.get_agent_slice()` Is Unimplemented (Returns `None`)

**File:** `studio/memory.py:323-331`
**Symptom:** `StudioManager.get_view_for_agent(role)` calls `state.get_agent_slice(role)`, which is a stub (`pass`) returning `None`. Any agent or external caller using this API will receive `None` instead of a `ContextSlice`.

**Root cause:** The method was defined as an interface placeholder and never implemented.

**Fix:** Implement `get_agent_slice()` with the same logic currently in `Orchestrator.slice_context()`, parameterized by role. This decouples context slicing from the orchestrator and makes it testable independently.

---

## PART 3 — HIGH PRIORITY PRODUCTION ISSUES

---

### PROD-08 🟠 HIGH: Orchestrator's Secondary Entropy Check Measures the Wrong Thing

**File:** `studio/orchestrator.py:363`
**Symptom:** The entropy check in `_engineer_wrapper` measures the uncertainty of the **task description** (deterministic PO text), not the engineer's output. It always returns near-zero entropy, making the secondary circuit breaker permanently dormant.

**Root cause:** `await self.calculator.measure_uncertainty(state.engineering.current_task or "Fix the bug", ...)` — the prompt is the task text, not the generated patch.

**Fix:** Either (a) pass `proposed_patch` as the measurement target, or (b) remove this redundant check entirely since the engineer subgraph already runs `node_entropy_guard` internally.

---

### PROD-09 🟠 HIGH: `run_po_cycle` Accesses Wrong State Key — Silent Fallback Always Triggers

**File:** `studio/agents/product_owner.py:170-174`
**Symptom:** `orchestration_layer` is never a key in serialized `StudioState` (Pydantic serializes it as `"orchestration"`). The primary `.get("orchestration_layer", {})` always returns `{}` and triggers the fallback. The code works but is misleading and masks schema drift.

**Root cause:** Legacy key name `orchestration_layer` retained from a migration that is now complete.

**Fix:** Delete the `orchestration_layer` branch entirely. Access `orchestrator_state.get("orchestration", {})` directly on the first attempt.

---

### PROD-10 🟠 HIGH: `_find_linked_pr` Only Checks Timeline Events — Jules PRs Often Not Found

**File:** `studio/utils/jules_client.py:388-400`
**Symptom:** If Jules creates a PR without a GitHub `cross-referenced` timeline event, `_find_linked_pr` returns `None` and `get_status` reports `"WORKING"` indefinitely, feeding directly into the WatchTower infinite loop (PROD-03).

**Root cause:** GitHub's `cross-referenced` event only appears when Jules explicitly mentions the issue number in the PR description. Different commit message formats skip it.

**Fix:** Add a fallback strategy: after timeline search fails, call `repo.get_pulls(state="open")` and filter PRs by label `"jules"` or by `head.ref` matching a known naming pattern, using the task creation timestamp as a lower bound.

---

### PROD-11 🟠 HIGH: Architect Gate Reviews Files From Disk, Not From the Actual Patch

**File:** `studio/subgraphs/engineer.py:560-581`
**Symptom:** `node_architect_gate` reads files with `os.path.exists(filepath)` from the CWD. If the git branch state is inconsistent (PROD-06 fallout, or branch checkout failed silently), the architect reviews the wrong version of the code.

**Fix:** Always apply `jules_data.generated_artifacts[0].diff_content` in-memory using `apply_virtual_patch` before passing source to the architect. This makes the review deterministic and independent of git branch state.

---

### PROD-12 🟠 HIGH: `DockerSandbox.run_pytest` Has No Timeout Enforcement

**File:** `studio/utils/sandbox.py:155-181`
**Symptom:** A hung test (infinite loop, deadlock) blocks `container.exec_run()` forever. `self.timeout = 60` is stored in `__init__` but never passed to `exec_run()`.

**Fix:** Pass `timeout=self.timeout` to `container.exec_run(...)`. Catch `docker.errors.APIError` on timeout and return `CommandResult(exit_code=-1, stderr="TIMEOUT")`.

---

### PROD-13 🟠 HIGH: Session and Thread IDs Are Static — Checkpointer Accumulates Stale State

**File:** `main.py:29`, `studio/manager.py:31`
**Symptom:** Every run of `python main.py run` uses `thread_id = "studio-session-v1"` and `session_id = "SESSION-00"`. The LangGraph checkpointer accumulates state from all previous runs under the same key. Crash recovery may resume a stale, inconsistent state from a prior sprint.

**Fix:** Generate `thread_id` dynamically: `f"studio-{datetime.now().strftime('%Y%m%d-%H%M%S')}"`. Give `OrchestrationState.session_id` a `default_factory=lambda: str(uuid.uuid4())`. Add a `--resume <thread_id>` flag to opt into resuming a specific checkpoint.

---

### PROD-14 🟠 HIGH: `PRODUCT_BLUEPRINT.md` Absence Is Only a Warning — Factory Crashes Later

**File:** `main.py:25-26`
**Symptom:** Missing `PRODUCT_BLUEPRINT.md` logs a warning and continues. The PO agent then throws `FileNotFoundError` inside `run_po_cycle`, which (absent PROD-04 fix) crashes the orchestrator with a cryptic error.

**Fix:** Treat a missing blueprint as a hard pre-flight failure: log a clear setup message and call `sys.exit(1)`.

---

### PROD-15 🟠 HIGH: `sync_main_branch` Race Condition — Merged PR May Not Be Visible Yet

**File:** `studio/utils/git_utils.py:48-87`, `studio/orchestrator.py:222-223`
**Symptom:** After `architect_gate` calls `client.merge_pr()`, `backlog_dispatcher` immediately calls `sync_main_branch()`. GitHub is eventually consistent — `origin/main` may not yet contain the just-merged commit. `git reset --hard origin/main` then lands on a stale state.

**Fix:** (Superseded by PROD-06 fix which removes this call entirely.) If the worktree approach is not adopted, add a retry loop in `sync_main_branch` that verifies the expected commit SHA is present on `origin/main` before resetting.

---

## PART 4 — MEDIUM PRIORITY ISSUES

---

### PROD-16 🟡 MEDIUM: Entropy Measurement Costs ~15 Vertex AI Calls Per Task Completion

**File:** `studio/utils/entropy_math.py:70`, `studio/subgraphs/engineer.py:310-315`
**Symptom:** Each entropy check: 5 sample calls + up to 10 pairwise entailment calls = 15 Vertex AI calls. This fires once inside `node_entropy_guard` and again in `_engineer_wrapper` (PROD-08). Every completed task triggers ~30 calls just for entropy overhead.

**Fix:** (a) Remove the duplicate orchestrator-level check (PROD-08). (b) Cache entailment results: if `hash(a) == hash(b)` return `True`. (c) Consider reducing to N=3 samples with threshold=1.0 for the MVP.

---

### PROD-17 🟡 MEDIUM: `OptimizerSandbox` Injects Prompt via `python3 -c "..."` — Injection Risk

**File:** `studio/agents/optimizer.py:113`
**Symptom:** A Python script containing `role` (f-string interpolated) is passed via shell `python3 -c "..."`. If a novel role name slips through `self.role_mapping` with shell metacharacters, it can break the command or inject code.

**Fix:** Write the script to a temp file inside the sandbox via `sandbox.setup_workspace({"update_prompt.py": py_script})` then run `sandbox.run_command("python3 update_prompt.py")`. This eliminates all shell quoting issues.

---

### PROD-18 🟡 MEDIUM: All Agents Hardcode Model Names Instead of Using `Settings`

**Files:** `studio/agents/architect.py:34`, `studio/agents/scrum_master.py:33`, `studio/agents/product_owner.py:43`
**Symptom:** All agents hardcode `"gemini-2.5-pro"` instead of reading `get_settings().thinking_model`. Changing the model for experimentation requires editing multiple files.

**Fix:** Default `model_name=None` in each agent's `__init__` and fall back to `get_settings().thinking_model` (or `doing_model` for lighter agents).

---

### PROD-19 🟡 MEDIUM: `JulesMetadata` Dict/Object Dual-Type Is a Persistent Source of Bugs

**Files:** Throughout `orchestrator.py`, `engineer.py`, `memory.py:302`
**Symptom:** `EngineeringState.jules_meta` is `Optional[Union[Dict, JulesMetadata]]`. Eight or more `isinstance(raw, dict)` guards exist across the codebase. A mutation to the reconstructed object is silently lost if `.model_dump(mode='json')` is forgotten before returning state.

**Fix:** Declare `jules_meta: Optional[Dict[str, Any]]` only (always a dict). Create a module-level helper `def _jules(state) -> JulesMetadata` that wraps the dict construction. This makes the contract explicit and removes all isinstance branches.

---

### PROD-20 🟡 MEDIUM: `SOP Guide` Node Is a No-op Mock

**File:** `studio/orchestrator.py:42-44`
**Symptom:** The SOP Interactive Guide (for "No-Log" scenarios) just increments a counter and exits. No useful debugging guidance is provided to the user.

**Fix:** Implement a real SOP decision tree that walks through Android debugging steps (`adb logcat`, `dmesg`, `bugreport`) based on `SOPState.active_sop_id`, producing structured instructions per step.

---

### PROD-21 🟡 MEDIUM: `reflector_node` Is a Mock That Only Sets a Flag

**File:** `studio/orchestrator.py:46-48`
**Symptom:** When cognitive tunneling is detected, `reflector_node` just sets `circuit_breaker_triggered = True`. No root cause summary, no operator alert, no post-mortem written to state.

**Fix:** Implement `reflector_node` to write a structured summary to `orchestration.failed_tasks_log` and emit a structured log event that an operator can monitor or alert on.

---

### PROD-22 🟡 MEDIUM: No `.env` Existence Check at Startup

**File:** `main.py`
**Symptom:** If `.env` is missing (fresh checkout, CI), the factory starts, fails Vertex AI auth with a cryptic error, and crashes without a helpful message.

**Fix:** Add a pre-flight check: verify `.env` exists and contains `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_REGION` before constructing the `Orchestrator`.

---

### TEST-10 🟠 HIGH: `test_main.py` Uses Production `CLEAN_PATH` Without Isolation

**File:** `tests/test_main.py:8-40`
**Symptom:** `test_manager_load_state_new()` and `test_manager_save_and_load_state()` import `CLEAN_PATH` directly from `main.py` (the production `studio_state.json` path) and unconditionally delete or overwrite it. If the factory is running concurrently, this silently corrupts live sprint state. This is the same class of bug as TEST-02 (`test_recovery.py`), just in a different file.

**Root cause:** No path isolation — tests operate on the real project-root state file.

**Fix:** Use `tmp_path` and monkeypatch to redirect the state file location:
```python
def test_manager_load_state_new(tmp_path, monkeypatch):
    monkeypatch.setattr("main.CLEAN_PATH", str(tmp_path / "state.json"))
    manager = StudioManager(root_dir=str(tmp_path))
    ...
```
Or pass `root_dir=tmp_path` to `StudioManager()` directly so it stores state in an isolated temp directory.

---

### TEST-11 🟡 MEDIUM: `test_secure_sandbox.py` Always Fails — `SecureSandbox` Class Does Not Exist

**File:** `tests/test_secure_sandbox.py:17-19`
**Symptom:** The test imports `SecureSandbox` in a `try/except ImportError` block and sets it to `None` if the import fails. Both test functions then call `pytest.fail(...)` immediately when `SecureSandbox is None`. Since the class has not been implemented in `studio/utils/sandbox.py`, these tests always hard-fail and pollute the test report.

**Root cause:** Tests were written TDD-style as a spec for `SecureSandbox`, but the class was never implemented.

**Options:**
- (a) Implement `SecureSandbox(DockerSandbox)` with `read_only=True`, `network_disabled=True`, `mem_limit="256m"`, `auto_remove=True`, and `tmpfs={"/workspace": ""}` constraints in `studio/utils/sandbox.py`.
- (b) Skip the tests with `pytest.mark.skip(reason="SecureSandbox not yet implemented")` until the implementation lands.
Option (a) is the correct fix — the test spec is valid and captures a real security requirement for the QA sandbox.

---

## Recommended Fix Priority

| Sprint | Issues | Goal |
|---|---|---|
| **Sprint 1 — Unbreak Tests** | TEST-01, TEST-02, TEST-10, TEST-03, TEST-04, TEST-05 | Make the test suite safe to run without destroying local work |
| **Sprint 2 — Autopilot Loop** | PROD-03, PROD-04, PROD-05, PROD-14 | Enable unattended multi-ticket runs that don't hang |
| **Sprint 3 — Isolation & Safety** | PROD-06, PROD-11, PROD-12, PROD-13 | Make git operations and QA sandboxed and reliable |
| **Sprint 4 — Intelligence** | PROD-01, PROD-02, PROD-07, PROD-08, PROD-10 | Give Jules real context; make entropy guardrail functional |
| **Sprint 5 — Polish** | TEST-06..09, TEST-11, PROD-16..22 | Reduce cost, eliminate code smells, improve observability |
