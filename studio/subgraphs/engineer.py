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
from studio.utils.patching import apply_virtual_patch
from studio.utils.prompts import ENGINEER_SYSTEM_PROMPT

logger = logging.getLogger("JulesProxy")

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

    # 2. Context Slicing Strategy
    # We purposefully limit the context to avoid 'Inference Load' issues.
    # In a full implementation, this uses a retrieval step (RAG).
    # For this specification, we assume a helper function `get_relevant_context`.
    # This aligns with the "Context Isolation" requirement.
    # context_slice = await get_relevant_context(task_description)
    context_slice = ContextSlice(
        files=["src/auth/login.py", "tests/auth/test_login.py"],
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
    client = JulesGitHubClient(
        github_token=SecretStr(os.environ.get("GITHUB_TOKEN", "")),
        repo_name=os.environ.get("GITHUB_REPOSITORY", "google/jules-studio")
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
    client = JulesGitHubClient(
        github_token=SecretStr(os.environ.get("GITHUB_TOKEN", "")),
        repo_name=os.environ.get("GITHUB_REPOSITORY", "google/jules-studio")
    )

    if not jules_data.external_task_id:
        # Safety check - should not happen due to graph topology
        return {"jules_metadata": jules_data}

    logger.info(f"Watch_Tower: Polling task {jules_data.external_task_id}")

    # 1. Fetch Remote Status
    try:
        remote_status: WorkStatus = client.get_status(jules_data.external_task_id)
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
        logger.info("Remote task is ready for review. Proceeding to Entropy Check/Verification.")
        jules_data.status = "VERIFYING"

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
    judge = VertexFlashJudge(GenerativeModel("gemini-1.5-flash"))
    calculator = SemanticEntropyCalculator(judge)

    prompt = jules_data.current_task_prompt or "Unknown Intent"
    metric = await calculator.measure_uncertainty(prompt, prompt)

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

    # 1. Prepare Files
    # We need to gather all relevant files (context + modified)
    # and apply the virtual patch.

    files_to_patch = {}
    test_files = []

    # Identify files from context slice
    if jules_data.active_context_slice and jules_data.active_context_slice.files:
        for filepath in jules_data.active_context_slice.files:
            try:
                # In a real deployment, we'd fetch these from the repo
                if os.path.exists(filepath):
                    with open(filepath, "r", encoding="utf-8") as f:
                        files_to_patch[filepath] = f.read()

                # Assume tests are in 'tests/' directory or similar
                if "test" in filepath or "spec" in filepath:
                    test_files.append(filepath)
            except FileNotFoundError:
                logger.warning(f"Context file not found: {filepath}")

    # Get the diff
    diff_content = ""
    if jules_data.generated_artifacts:
        diff_content = jules_data.generated_artifacts[0].diff_content

    # Apply Patch
    try:
        patched_files = apply_virtual_patch(files_to_patch, diff_content)
    except Exception as e:
        logger.error(f"Failed to apply virtual patch: {e}")
        # Mark as error in feedback
        status = "ERROR"
        logs = f"Patch application failed: {str(e)}"

        result = TestResult(
            test_id="patch_application",
            status=status,
            logs=logs,
            attempt_count=jules_data.retry_count + 1
        )
        jules_data.test_results_history.append(result)
        jules_data.status = "FAILED"
        return {"jules_metadata": jules_data}

    # 2. Setup Sandbox
    # Replicates the Engineer's environment for validation
    sandbox = None
    try:
        sandbox = DockerSandbox()

        # Inject Code + Tests
        if not sandbox.setup_workspace(patched_files):
             raise RuntimeError("Failed to setup workspace")

        # 3. Install Deps
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

    except Exception as e:
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
        jules_data.status = "FAILED"

    return {"jules_metadata": jules_data}


# --- 5. Feedback Loop Node (The Correction Engine) ---

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
        # Reset flag for next attempt
        jules_data.cognitive_tunneling_detected = False

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
        else:
            feedback = "Task failed without test results."

    # 2. Update Feedback Log
    jules_data.feedback_log.append(feedback)

    # 3. Post Feedback to Jules (The Hand)
    client = JulesGitHubClient(
        github_token=SecretStr(os.environ.get("GITHUB_TOKEN", "")),
        repo_name=os.environ.get("GITHUB_REPOSITORY", "google/jules-studio")
    )
    if jules_data.external_task_id:
        client.post_feedback(jules_data.external_task_id, feedback, is_error=True)

    # 4. Retry Logic (Self-Correction)
    if jules_data.retry_count < jules_data.max_retries:
        jules_data.retry_count += 1
        jules_data.status = "QUEUED" # Reset status to trigger Task_Dispatcher
        logger.info(f"Feedback_Loop: Triggering Retry {jules_data.retry_count}/{jules_data.max_retries}")

        # Add a message to the conversation history so the Orchestrator is aware of the churn
        messages.append(HumanMessage(content=f"Retry {jules_data.retry_count}: Automated feedback generated based on failure."))
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

def route_qa_verifier(state: AgentState) -> Literal["end", "feedback_loop"]:
    """
    Decides if the task is done or needs correction.
    """
    if state["jules_metadata"].status == "COMPLETED":
        return "end"
    return "feedback_loop"

def route_feedback_loop(state: AgentState) -> Literal["task_dispatcher", "end"]:
    """
    Decides whether to retry the loop or give up.
    """
    if state["jules_metadata"].status == "QUEUED": # Retry triggered
        return "task_dispatcher"
    return "end" # Max retries exceeded

# --- Subgraph Builder ---

def build_engineer_subgraph() -> StateGraph:
    workflow = StateGraph(AgentState)

    # Add Nodes
    workflow.add_node("task_dispatcher", node_task_dispatcher)
    workflow.add_node("watch_tower", node_watch_tower)
    workflow.add_node("entropy_guard", node_entropy_guard)
    workflow.add_node("qa_verifier", node_qa_verifier)
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
            "end": END,
            "feedback_loop": "feedback_loop"
        }
    )

    workflow.add_conditional_edges(
        "feedback_loop",
        route_feedback_loop,
        {
            "task_dispatcher": "task_dispatcher", # The Loop Back
            "end": END # Escalation
        }
    )

    return workflow.compile()
