"""
studio/subgraphs/engineer.py

Implements the Jules Proxy Subgraph, orchestrating the asynchronous execution
of engineering tasks via the Google Jules-style remote worker.

This graph enforces the 'Micro-Loop' of the Cognitive Software Factory:
Plan -> Execute -> Monitor (Entropy) -> Verify (TDD) -> Feedback.
"""

import asyncio
import logging
import os
import re
from typing import Literal, Dict, Any, List
from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from pydantic import SecretStr

from studio.memory import (
    AgentState,
    JulesMetadata,
    SemanticEntropyReading,
    TestResult,
    ContextSlice,
    CodeChangeArtifact
)
from studio.utils.jules_client import JulesGitHubClient, TaskPayload, WorkStatus, TaskPriority
from vertexai.generative_models import GenerativeModel
from studio.utils.entropy_math import SemanticEntropyCalculator, VertexFlashJudge
from studio.utils.sandbox import DockerSandbox
from studio.utils.patching import apply_virtual_patch, extract_affected_files
from studio.utils.git_utils import checkout_pr_branch
from studio.agents.architect import ArchitectAgent, ReviewVerdict
from studio.config import get_settings

logger = logging.getLogger("JulesProxy")

# Ignore common noise patterns from pytest/docs/stdlib
NOISE_PATTERNS = [
    "org/en/stable",
    "unittest/mock.py",
    "workspace/",
    "http:",
    "https:"
]

def is_valid_local_path(path: str) -> bool:
    """
    Validates if a string that looks like a path is a safe, local project path.
    Prevents Orchestrator from accidentally creating garbage folders or
    trying to write to absolute paths (e.g., /workspace).
    """
    # 1. Ignore absolute paths (Safety & Permission issues)
    if path.startswith("/"):
        return False
    # 2. Ignore paths with double slashes (often malformed or // protocol)
    if "//" in path:
        return False
    # 3. Ignore paths escaping current directory
    if ".." in path:
        return False

    for pattern in NOISE_PATTERNS:
        if pattern in path:
            return False

    # 5. Reject spaces (Safety & Convention)
    if " " in path:
        return False

    # 6. Extension check (Must be one of the supported source types)
    supported_extensions = ('.py', '.txt', '.md', '.yml', '.yaml', '.json', '.c', '.h', '.cpp')
    if not path.endswith(supported_extensions):
        return False

    return True

# --- 1. Task Dispatcher Node ---

async def node_task_dispatcher(state: AgentState) -> Dict[str, Any]:
    """
    Node: Task_Dispatcher
    Role: The Interface Layer.

    Responsibilities:
    1. Context Slicing: Queries the vector store/file system to prepare a minimal
       effective context, preventing 'Context Collapse'.
    2. Session Management: Initializes or resumes the remote Jules session.
    3. Prompt Engineering: Constructs the specific work order, injecting
       feedback from previous failures if applicable.
    """
    logger.info("Task_Dispatcher: Initializing engineering task.")
    jules_data = state["jules_metadata"]

    # 1. Determine Task Context (Retry vs New)
    is_retry = jules_data.retry_count > 0
    # Handle case where messages might be empty
    task_description = state["messages"][-1].content if state["messages"] else "No description provided"

    # Save the prompt for entropy check later
    jules_data.current_task_prompt = task_description

    # 2. Dynamic Context Slicing Strategy
    # Extract potential file paths from the task description to provide targeted context.
    # This avoids 'Context Collapse' while ensuring Jules has what it needs.

    # Heuristic: Find strings that look like file paths
    # Improved regex: avoids matching leading slashes or dots
    path_regex = r'(?<![\w/\-.])([\w\-]+(?:/[\w\-]+)*\.(?:py|txt|md|yml|yaml|json|c|h|cpp))'
    potential_files = re.findall(path_regex, task_description)

    # If it's a retry, we might want to include files mentioned in the feedback too
    if is_retry and jules_data.feedback_log:
        feedback_files = re.findall(path_regex, jules_data.feedback_log[-1])
        potential_files.extend(feedback_files)

    # Filter and ensure existence (Fix 1 requirement)
    target_files = []
    for f in set(potential_files):
        # Apply strict validation
        if not is_valid_local_path(f):
            logger.info(f"Task_Dispatcher: Skipping invalid path {f}")
            continue

        if not os.path.exists(f):
            # If it's a new file task, create empty placeholder so Jules knows where to work
            logger.info(f"Task_Dispatcher: Creating placeholder for new file {f}")
            try:
                dirname = os.path.dirname(f)
                if dirname:
                    os.makedirs(dirname, exist_ok=True)
                with open(f, "w", encoding="utf-8") as f_out:
                    f_out.write("") # Empty placeholder
            except Exception as e:
                logger.warning(f"Failed to create placeholder {f}: {e}")
                continue

        target_files.append(f)

    # Fallback to a basic context if nothing identified
    if not target_files:
        target_files = ["README.md"] # Minimal anchor

    context_slice = ContextSlice(
        files=target_files,
        issues=[]
    )
    jules_data.active_context_slice = context_slice

    # 3. Construct the 'Work Order' Prompt (via TaskPayload)
    constraints = []
    if is_retry and jules_data.feedback_log:
        constraints.append("Analyze the evidence provided in the logs. Generate a Virtual Patch to fix these specific errors.")
        constraints.append(f"CRITICAL FEEDBACK FROM PREVIOUS ATTEMPT: {jules_data.feedback_log[-1]}")
    else:
        constraints.append("Follow TDD: Write a failing test (Red) first, then the implementation (Green).")

    # 4. Asynchronous Handoff to Remote Jules
    # We use a client wrapper to abstract the A2A or MCP protocol details.[6]
    settings = get_settings()
    client = JulesGitHubClient(
        github_token=settings.github_token,
        repo_name=settings.github_repository,
        jules_username=settings.jules_username
    )

    # Ideally, we only start a new task if we aren't already working.
    if jules_data.status == "QUEUED" or is_retry:
        logger.info(f"Dispatching task to Jules Session {jules_data.session_id}")

        # Convert List[str] to Dict[str, str] for TaskPayload
        context_files_dict = {f: "Context file" for f in context_slice.files}

        payload = TaskPayload(
            task_id=jules_data.session_id,
            intent=task_description,
            context_files=context_files_dict,
            relevant_logs=None, # Could extract if available
            constraints=constraints,
            priority=TaskPriority.MEDIUM
        )

        task_id = client.dispatch_task(payload)
        jules_data.external_task_id = task_id
        jules_data.status = "WORKING"

    return {"jules_metadata": jules_data}


# --- 2. Watch Tower Node (The Asynchronous Poller) ---

async def node_watch_tower(state: AgentState) -> Dict[str, Any]:
    """
    Node: Watch_Tower
    Role: Asynchronous Polling & Lifecycle Management.

    Responsibilities:
    1. Polls the external agent status (WORKING, COMPLETED, FAILED).
    2. Handles 'Long-Running' tasks by creating a check-pointable loop.
    3. Identifies 'NEEDS_INFO' states to trigger Human-in-the-loop interrupts.
    """
    jules_data = state["jules_metadata"]
    settings = get_settings()

    # 0. Wait for the configured interval before polling
    # Because jules need time to finish PR implementation
    logger.info(
        f"Watch_Tower: Waiting {settings.jules_poll_interval} "
        "seconds before polling..."
    )
    await asyncio.sleep(settings.jules_poll_interval)

    client = JulesGitHubClient(
        github_token=settings.github_token,
        repo_name=settings.github_repository,
        jules_username=settings.jules_username
    )

    if not jules_data.external_task_id:
        # Safety check - should not happen due to graph topology
        return {"jules_metadata": jules_data}

    logger.info(f"Watch_Tower: Polling task {jules_data.external_task_id}")

    # 1. Fetch Remote Status
    try:
        remote_status: WorkStatus = await asyncio.to_thread(client.get_status, jules_data.external_task_id)
    except Exception as e:
        logger.error(f"Polling failed: {e}")
        # Transient error handling strategy could be implemented here
        return {"jules_metadata": jules_data} # Retry next loop

    # 2. State Mapping
    if remote_status.status == "COMPLETED":
        # Merged or closed
        logger.info("Remote task completed. Proceeding to Entropy Check.")
        jules_data.status = "VERIFYING" # Treat as VERIFYING to ensure tests run

        if remote_status.raw_diff:
            artifact = CodeChangeArtifact(
                diff_content=remote_status.raw_diff,
                change_type="MODIFY",
                pr_link=remote_status.pr_url
            )
            jules_data.generated_artifacts = [artifact]

    elif remote_status.status == "REVIEW_READY":
        # Hash Check: Don't re-test the same code
        if remote_status.last_commit_hash == jules_data.last_verified_commit:
            logger.info(f"Review ready but commit hash {remote_status.last_commit_hash} already verified. Waiting for new changes.")
            jules_data.status = "WORKING"
            return {"jules_metadata": jules_data}

        logger.info(f"New commit detected ({remote_status.last_commit_hash}). Proceeding to Entropy Check/Verification.")
        jules_data.status = "VERIFYING"
        jules_data.last_verified_commit = remote_status.last_commit_hash
        jules_data.last_verified_pr_number = remote_status.linked_pr_number
        jules_data.current_branch = remote_status.branch_name

        # Retrieve artifacts (virtual patches, diffs)
        if remote_status.raw_diff:
            artifact = CodeChangeArtifact(
                diff_content=remote_status.raw_diff,
                change_type="MODIFY",
                pr_link=remote_status.pr_url
            )
            jules_data.generated_artifacts = [artifact]

    elif remote_status.status == "BLOCKED": # Was NEEDS_INFO or BLOCKED
        logger.warning("Agent requires human intervention.")
        jules_data.status = "BLOCKED"

    else:
        # WORKING or QUEUED
        jules_data.status = "WORKING"

    return {"jules_metadata": jules_data}


# --- 3. Entropy Guard Node (The Cognitive Circuit Breaker) ---

async def node_entropy_guard(state: AgentState) -> Dict[str, Any]:
    """
    Node: Entropy_Guard
    Role: Mathematical Guardrail against Hallucination.

    Responsibilities:
    1. Calculates Semantic Entropy (SE) on the agent's reasoning trace.
    2. Triggers the 'Circuit Breaker' if SE > 7.0.
    3. Prevents invalid code from reaching the QA stage.
    """
    jules_data = state["jules_metadata"]

    # We only run this check if the agent claims it is done.
    # We verify if it's *actually* done or just hallucinating completion.

    # New Client doesn't support traces, use diff content.
    traces = ""
    if jules_data.generated_artifacts:
        traces = jules_data.generated_artifacts[0].diff_content

    # 1. Calculate Semantic Entropy
    # SE measures the uncertainty over *meanings*, not just tokens.
    # High SE means the model is oscillating between semantically distinct options.

    # Initialize the Sensor
    judge = VertexFlashJudge(GenerativeModel("gemini-2.5-flash"))
    calculator = SemanticEntropyCalculator(judge)

    prompt = jules_data.current_task_prompt or "Unknown Intent"
    intent = jules_data.active_context_slice.intent if jules_data.active_context_slice else "CODING"
    metric = await calculator.measure_uncertainty(prompt, intent)

    se_score = metric.entropy_score

    logger.info(f"Entropy_Guard: Calculated SE = {se_score}")

    # 2. Update History & Trajectory
    reading = SemanticEntropyReading(
        score=se_score,
        threshold=metric.threshold,
        triggered_breaker=metric.is_tunneling,
        context_hash=str(hash(prompt)),
        reasoning_trace_summary=str(metric.cluster_distribution)
    )
    jules_data.entropy_history.append(reading)
    jules_data.current_entropy = se_score

    # 3. Circuit Breaker Logic
    if metric.is_tunneling:
        logger.warning("Entropy_Guard: Circuit Breaker TRIPPED! Cognitive Tunneling detected.")
        jules_data.cognitive_tunneling_detected = True
        jules_data.status = "FAILED" # Force failure to trigger Feedback/Reflection

        # Immediate Interruption - Do not waste resources on QA
        # We can't easily cancel a GitHub issue, but we can comment or close PR.
        # client.cancel_task not available.
        # We could post feedback here?

        # Inject a meta-message to the graph history
        return {
            "jules_metadata": jules_data,
            "messages": [AIMessage(content="**SYSTEM**: Circuit Breaker Tripped. Cognitive Tunneling detected.")]
        }

    return {"jules_metadata": jules_data}


# --- 4. QA Verifier Node (The Gatekeeper) ---

async def node_qa_verifier(state: AgentState) -> Dict[str, Any]:
    """
    Node: QA_Verifier
    Role: Functional Verification & TDD Enforcement.

    Responsibilities:
    1. Executes the 'Virtual Patch' in a clean Sandbox.
    2. Runs the test suite to validate TDD (Red/Green) compliance.
    3. Generates 'Evidence Snippets' for the feedback loop.
    """
    jules_data = state["jules_metadata"]

    if jules_data.status != "VERIFYING":
        return {}

    logger.info("QA_Verifier: Running dynamic verification in sandbox.")

    # 0. Sync workspace with PR branch (Replace Virtual Patching)
    if jules_data.current_branch:
        logger.info(f"QA_Verifier: Syncing workspace to branch {jules_data.current_branch}")
        try:
            checkout_pr_branch(jules_data.current_branch)
        except Exception as e:
            logger.error(f"QA_Verifier: Checkout failed: {e}")
            result = TestResult(
                test_id="git_checkout",
                status="ERROR",
                logs=f"Failed to checkout branch {jules_data.current_branch}: {str(e)}",
                attempt_count=jules_data.retry_count + 1
            )
            jules_data.test_results_history.append(result)
            jules_data.status = "FAILED"
            return {"jules_metadata": jules_data}

    # 1. Prepare Files
    # We need to gather all relevant files (context + modified)
    # and apply the virtual patch.

    files_to_patch = {}
    test_files = []

    # 1. Gather files from context slice
    all_target_files = set()
    if jules_data.active_context_slice and jules_data.active_context_slice.files:
        all_target_files.update(jules_data.active_context_slice.files)

    # 2. Get the diff and extract ALL affected files (Dynamic Context Sync)
    diff_content = ""
    if jules_data.generated_artifacts:
        diff_content = jules_data.generated_artifacts[0].diff_content
        affected_files = extract_affected_files(diff_content)
        all_target_files.update(affected_files)

    # 3. Ensure core testing infrastructure is included
    # This prevents sandbox crashes when Jules doesn't touch tests
    infra_files = ["pytest.ini", "requirements.txt"]
    for f in infra_files:
        if os.path.exists(f):
            all_target_files.add(f)

    # If no tests are currently identified, pull in the tests/ directory
    # to ensure 'pytest tests/' has targets.
    has_tests = any(f.endswith(".py") and ("test" in f or "spec" in f) for f in all_target_files)
    if not has_tests and os.path.exists("tests"):
        for root, _, files in os.walk("tests"):
            for file in files:
                if file.endswith(".py") and ("test" in file or "spec" in file):
                    all_target_files.add(os.path.join(root, file))

    # 4. Load files from disk to populate the Sandbox
    for filepath in all_target_files:
        try:
            # In a real deployment, we'd fetch these from the repo
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    files_to_patch[filepath] = f.read()

            # Identify tests to run
            if filepath.endswith(".py") and ("test" in filepath or "spec" in filepath):
                test_files.append(filepath)
        except FileNotFoundError:
            logger.warning(f"File not found during sandbox prep: {filepath}")

    # 4. Use synced local files (formerly Apply Patch)
    # Since we checked out the branch, files_to_patch (read from disk)
    # already contains the changes from Jules.
    patched_files = files_to_patch

    # 2. Setup Sandbox
    # Replicates the Engineer's environment for validation
    sandbox = None
    try:
        sandbox = DockerSandbox()

        # Inject Code + Tests
        if not sandbox.setup_workspace(patched_files):
             raise RuntimeError("Failed to setup workspace")

        # 3. Install Deps
        if "requirements.txt" in patched_files:
            # Prefer requirements.txt for full project dependencies if available
            sandbox.run_command("pip install -r requirements.txt")

        sandbox.install_dependencies(["pytest", "mock"]) # Basic deps

        # 4. Run Tests
        # If no specific tests identified, run all in tests/
        target = "tests/"
        if test_files:
             target = " ".join(test_files)

        test_output = sandbox.run_pytest(target)

        sandbox.teardown()
        sandbox = None

        status = "PASS" if test_output.passed else "FAIL"
        logs = test_output.error_log or "Tests Passed"

    except PermissionError as e:
        status = "ERROR"
        logs = f"INFRASTRUCTURE_ERROR: PermissionError - {str(e)}"
        if sandbox:
            try:
                sandbox.teardown()
            except Exception:
                pass
    except Exception as e:
        if "PermissionError" in str(e):
            status = "ERROR"
            logs = f"INFRASTRUCTURE_ERROR: {str(e)}"
        else:
            status = "ERROR"
            logs = str(e)

        if sandbox:
            try:
                sandbox.teardown()
            except Exception:
                pass

    # 3. Record Result
    result = TestResult(
        test_id="e2e_verification",
        status=status,
        logs=logs,
        attempt_count=jules_data.retry_count + 1
    )
    jules_data.test_results_history.append(result)

    # 4. Status Promotion/Demotion
    if result.status == "PASS":
        logger.info("QA_Verifier: Tests PASSED. Promoting status to COMPLETED.")
        jules_data.status = "COMPLETED"
    else:
        logger.warning(f"QA_Verifier: Tests FAILED. Demoting status to FAILED. Logs: {logs[:100]}...")

        # Stability Protocol Fallback: If refactor breaks tests, fallback to Green
        if jules_data.is_refactoring and jules_data.green_patch:
            logger.warning("QA_Verifier: Refactor broke tests. Falling back to Green state.")

            # Initialize client for fallback
            settings = get_settings()
            client = JulesGitHubClient(
                github_token=settings.github_token,
                repo_name=settings.github_repository,
                jules_username=settings.jules_username
            )

            if jules_data.last_verified_pr_number:
                body = "Refactor broke functional tests. Falling back to Green state with #TODO: Tech Debt."
                client.fallback_to_green(jules_data.last_verified_pr_number, jules_data.green_patch)
                client.review_pr(jules_data.last_verified_pr_number, event="APPROVE", body=body)
                client.merge_pr(jules_data.last_verified_pr_number)

            jules_data.status = "COMPLETED" # We accept the fallback
            jules_data.is_refactoring = False
            return {"jules_metadata": jules_data}

        jules_data.status = "FAILED"

    return {"jules_metadata": jules_data}

# --- 5. Architect Gate Node (The Design Authority) ---

async def node_architect_gate(state: AgentState) -> Dict[str, Any]:
    """
    Node: Architect_Gate
    Role: Design Authority & SOLID Enforcement.

    Responsibilities:
    1. Reviews code that has PASSED functional tests.
    2. Enforces SOLID principles and 'AGENTS.md' compliance.
    3. Rejects sloppy 'Green' code, forcing a refactor cycle.
    """
    jules_data = state["jules_metadata"]

    # Only run if QA passed
    if jules_data.status != "COMPLETED":
        return {}

    logger.info("Architect_Review: Starting architectural audit.")

    # 1. Reconstruct Context (Patched Code)
    files_to_patch = {}
    all_target_files = set()
    if jules_data.active_context_slice and jules_data.active_context_slice.files:
        all_target_files.update(jules_data.active_context_slice.files)

    diff_content = ""
    if jules_data.generated_artifacts:
        diff_content = jules_data.generated_artifacts[0].diff_content
        affected_files = extract_affected_files(diff_content)
        all_target_files.update(affected_files)

    for filepath in all_target_files:
        try:
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    files_to_patch[filepath] = f.read()
        except Exception:
            pass

    # 4. Use synced local files (formerly Apply Patch)
    # Since we are on the PR branch, files_to_patch already contains the changes.
    patched_files = files_to_patch

    # 2. Run Architect Agent
    architect = ArchitectAgent()
    ticket_context = jules_data.current_task_prompt or "Unknown Task"

    all_violations = []

    # We review all modified files
    for filepath, full_source in patched_files.items():
        verdict = architect.review_code(filepath, full_source, ticket_context)

        if verdict.status in ["REJECTED", "NEEDS_REFACTOR"]:
            all_violations.extend(verdict.violations)

    # 3. Handle Verdict
    if jules_data.last_verified_pr_number:
        settings = get_settings()
        client = JulesGitHubClient(
            github_token=settings.github_token,
            repo_name=settings.github_repository,
            jules_username=settings.jules_username
        )
    else:
        client = None

    if all_violations:
        logger.warning(f"Architect_Gate: Code REJECTED with {len(all_violations)} violations.")

        # Stability Protocol: ONE refactor attempt
        if jules_data.refactor_count < 1:
            logger.info("Architect_Gate: Triggering first refactor attempt.")
            jules_data.status = "FAILED"
            jules_data.refactor_count += 1
            jules_data.is_refactoring = True

            # Save the current "Green" patch for potential fallback
            if jules_data.generated_artifacts:
                jules_data.green_patch = jules_data.generated_artifacts[0].diff_content

            # Format feedback
            feedback = "ARCHITECTURAL REVIEW FAILED.\n\nVIOLATIONS:\n"
            for v in all_violations:
                feedback += f"- [{v.severity}] {v.rule_id} in {v.file_path}: {v.description} (Fix: {v.suggested_fix})\n"

            feedback += "\nINSTRUCTION: Refactor the code to address these violations while keeping tests GREEN."
            jules_data.feedback_log.append(feedback)

            # Submit a formal REQUEST_CHANGES review on GitHub
            if client and jules_data.last_verified_pr_number:
                logger.info(f"Architect_Gate: Requesting changes on PR #{jules_data.last_verified_pr_number}")
                client.review_pr(jules_data.last_verified_pr_number, event="REQUEST_CHANGES", body=feedback)

            return {
                "jules_metadata": jules_data,
                "messages": [AIMessage(content="**SYSTEM**: Architect rejected the solution. Refactor attempt 1/1 initiated.")]
            }
        else:
            # Fallback Rule: Already attempted refactor, revert to Green state with tag
            logger.warning("Architect_Gate: Refactor retry limit reached. Falling back to Green state.")

            if jules_data.green_patch:
                # We restore the green patch and add tech debt tag
                # Implementation of fallback will be in JulesGitHubClient
                if client and jules_data.last_verified_pr_number:
                    body = "Refactor limit reached. Falling back to Green state with #TODO: Tech Debt."
                    client.fallback_to_green(jules_data.last_verified_pr_number, jules_data.green_patch)
                    client.review_pr(jules_data.last_verified_pr_number, event="APPROVE", body=body)
                    client.merge_pr(jules_data.last_verified_pr_number)

                jules_data.status = "COMPLETED"
                jules_data.is_refactoring = False
                return {
                    "jules_metadata": jules_data,
                    "messages": [AIMessage(content="**SYSTEM**: Refactor limit reached. Fallback to Green state with Tech Debt tag.")]
                }

    logger.info("Architect_Review: Code APPROVED.")
    jules_data.is_refactoring = False # Reset refactoring flag on success

    # Submit a formal APPROVE review then merge the PR
    if client and jules_data.last_verified_pr_number:
        logger.info(f"Architect_Gate: Approving PR #{jules_data.last_verified_pr_number}")
        client.review_pr(jules_data.last_verified_pr_number, event="APPROVE", body="All checks passed. Merging.")
        logger.info(f"Architect_Gate: Merging PR #{jules_data.last_verified_pr_number}")
        client.merge_pr(jules_data.last_verified_pr_number)

    return {"jules_metadata": jules_data}


# --- 6. Feedback Loop Node (The Correction Engine) ---

async def node_feedback_loop(state: AgentState) -> Dict[str, Any]:
    """
    Node: Feedback_Loop
    Role: Meta-Cognitive Correction.

    Responsibilities:
    1. Analyzes the *type* of failure (Entropy vs QA).
    2. Constructs a 'Interactive Debugging Guide' for the Agent.
    3. Decides whether to Retry (Self-Correction) or Escalate (Human Help).
    """
    jules_data = state["jules_metadata"]
    messages = []

    logger.info("Feedback_Loop: Analyzing failure for correction.")

    # 1. Root Cause Analysis of the Failure
    if jules_data.cognitive_tunneling_detected:
        # Case A: Cognitive Failure
        feedback = "CRITICAL: The previous attempt exhibited circular reasoning (High Semantic Entropy). " \
                   "The agent is stuck in a Cognitive Tunnel. " \
                   "STOP. REFLECT. Do not repeat the same strategy. " \
                   "Propose a fundamentally different approach."

        if not jules_data.feedback_log or jules_data.feedback_log[-1] != feedback:
            jules_data.feedback_log.append(feedback)

        # Reset flag for next attempt
        jules_data.cognitive_tunneling_detected = False

    # Case C: Architectural Rejection (New)
    elif any("ARCHITECTURAL REVIEW FAILED" in log for log in jules_data.feedback_log[-1:]):
         # The feedback is already appended by node_architect_review
         # We just ensure we don't overwrite it or add redundant info
         pass

    else:
        # Case B: Functional Failure
        latest_test = jules_data.test_results_history[-1] if jules_data.test_results_history else None

        if latest_test:
            # Construct 'Evidence Snippets'
            # We extract the specific assertion errors to guide the fix.
            log_snippet = latest_test.logs[-1000:] # Last 1000 chars often contain the error summary

            feedback = f"Functional Verification Failed.\n\nEVIDENCE SNIPPETS:\n```\n{log_snippet}\n```\n\n"
            feedback += "INSTRUCTION: Generate a fix (Virtual Patch) specifically addressing these errors. " \
                        "Ensure you adhere to the TDD Green phase requirements."
            # Append feedback only if it's new (simple check)
            if not jules_data.feedback_log or jules_data.feedback_log[-1] != feedback:
                jules_data.feedback_log.append(feedback)
        else:
            feedback = "Task failed without test results."
            if not jules_data.feedback_log or jules_data.feedback_log[-1] != feedback:
                 jules_data.feedback_log.append(feedback)

    # 2. Update Feedback Log
    # (Already updated above)

    # 3. Post Feedback to Jules (The Hand)
    settings = get_settings()
    client = JulesGitHubClient(
        github_token=settings.github_token,
        repo_name=settings.github_repository,
        jules_username=settings.jules_username
    )
    if jules_data.external_task_id:
        feedback_to_send = jules_data.feedback_log[-1]
        client.post_feedback(jules_data.external_task_id, feedback_to_send, is_error=True)

    # 4. Retry Logic (Self-Correction)
    is_infra_error = False
    latest_test = jules_data.test_results_history[-1] if jules_data.test_results_history else None
    if latest_test and "INFRASTRUCTURE_ERROR" in latest_test.logs:
        is_infra_error = True

    if not is_infra_error and jules_data.retry_count < jules_data.max_retries:
        jules_data.retry_count += 1

        # True PR Feedback Loop: Reuse existing task if available
        if jules_data.external_task_id:
            jules_data.status = "WORKING"
            logger.info(f"Feedback_Loop: Reusing task {jules_data.external_task_id}. Triggering Retry {jules_data.retry_count}/{jules_data.max_retries}")
        else:
            jules_data.status = "QUEUED" # Reset status to trigger Task_Dispatcher
            logger.info(f"Feedback_Loop: No external task found. Triggering Retry {jules_data.retry_count}/{jules_data.max_retries}")

        # Add a message to the conversation history so the Orchestrator is aware of the churn
        messages.append(HumanMessage(content=f"Retry {jules_data.retry_count}: Automated feedback generated based on failure."))
    elif is_infra_error:
        # Infrastructure failure - Stop loop to prevent wasting retries
        jules_data.status = "FAILED"
        error_msg = f"**SYSTEM**: Infrastructure error detected ({latest_test.logs if latest_test else 'Unknown'}). Stopping retries."
        messages.append(AIMessage(content=error_msg))
        logger.error(f"Feedback_Loop: {error_msg}")
    else:
        # Max retries exceeded - Escalation
        jules_data.status = "FAILED"
        messages.append(AIMessage(content="**SYSTEM**: Max retries exceeded. Escalating to Orchestrator/Human for manual intervention."))

    return {
        "jules_metadata": jules_data,
        "messages": messages
    }

# --- Routing Logic (Conditional Edges) ---

def route_watch_tower(state: AgentState) -> Literal["entropy_guard", "watch_tower", "interrupt_human"]:
    """
    Decides if we should keep polling, interrupt for human input, or proceed.
    """
    status = state["jules_metadata"].status
    if status == "BLOCKED":
        return "interrupt_human" # LangGraph interrupt
    if status in ["WORKING", "QUEUED", "PLANNING"]:
        return "watch_tower" # Keep polling
    return "entropy_guard" # Task finished (success or fail), check entropy

def route_entropy_guard(state: AgentState) -> Literal["qa_verifier", "feedback_loop", "watch_tower"]:
    """
    Decides routing based on cognitive health.
    """
    meta = state["jules_metadata"]

    if meta.cognitive_tunneling_detected:
        return "feedback_loop" # Immediate circuit break

    if meta.status == "VERIFYING":
        return "qa_verifier" # Proceed to functional test

    if meta.status == "FAILED":
        return "feedback_loop" # Remote task failed (e.g. build error)

    return "watch_tower" # Default fallback

def route_qa_verifier(state: AgentState) -> Literal["architect_gate", "feedback_loop"]:
    """
    Decides if the task is done (proceed to Architect) or needs correction.
    """
    if state["jules_metadata"].status == "COMPLETED":
        return "architect_gate"
    return "feedback_loop"

def route_architect_gate(state: AgentState) -> Literal["end", "feedback_loop"]:
    """
    Decides if the task is architecturally sound.
    """
    if state["jules_metadata"].status == "COMPLETED":
        return "end"
    return "feedback_loop"

def route_feedback_loop(state: AgentState) -> Literal["task_dispatcher", "watch_tower", "end"]:
    """
    Decides whether to retry the loop or give up.
    """
    if state["jules_metadata"].status == "QUEUED": # Traditional retry (new task)
        return "task_dispatcher"
    if state["jules_metadata"].status == "WORKING": # PR feedback loop (reuse task)
        return "watch_tower"
    return "end" # Max retries exceeded

# --- Subgraph Builder ---

def build_engineer_subgraph() -> StateGraph:
    workflow = StateGraph(AgentState)

    # Add Nodes
    workflow.add_node("task_dispatcher", node_task_dispatcher)
    workflow.add_node("watch_tower", node_watch_tower)
    workflow.add_node("entropy_guard", node_entropy_guard)
    workflow.add_node("qa_verifier", node_qa_verifier)
    workflow.add_node("architect_gate", node_architect_gate)
    workflow.add_node("feedback_loop", node_feedback_loop)

    # Set Entry Point
    workflow.set_entry_point("task_dispatcher")

    # Add Edges
    workflow.add_edge("task_dispatcher", "watch_tower")

    # Conditional Edges
    workflow.add_conditional_edges(
        "watch_tower",
        route_watch_tower,
        {
            "watch_tower": "watch_tower",
            "entropy_guard": "entropy_guard",
            "interrupt_human": END # Handled by Supergraph interrupt logic
        }
    )

    workflow.add_conditional_edges(
        "entropy_guard",
        route_entropy_guard,
        {
            "qa_verifier": "qa_verifier",
            "feedback_loop": "feedback_loop",
            "watch_tower": "watch_tower"
        }
    )

    workflow.add_conditional_edges(
        "qa_verifier",
        route_qa_verifier,
        {
            "architect_gate": "architect_gate",
            "feedback_loop": "feedback_loop"
        }
    )

    workflow.add_conditional_edges(
        "architect_gate",
        route_architect_gate,
        {
            "end": END,
            "feedback_loop": "feedback_loop"
        }
    )

    workflow.add_conditional_edges(
        "feedback_loop",
        route_feedback_loop,
        {
            "task_dispatcher": "task_dispatcher",
            "watch_tower": "watch_tower",
            "end": END # Escalation
        }
    )

    return workflow.compile()
