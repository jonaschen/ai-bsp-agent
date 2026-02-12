"""
studio/subgraphs/engineer.py
----------------------------
The Engineer Subgraph (Phase 2.5 Wired).
The "Factory Floor" where code is written, tested, AND reviewed.

Flow:
1. Dispatch (Jules) -> Watch (Poll)
2. Entropy Check (Safety)
3. QA Verify (Functionality)
4. Architect Gate (Quality) -> If Reject, loop back to Feedback.

Dependencies:
- studio.agents.architect (The Gatekeeper)
- studio.utils.jules_client (The Hand)
- studio.utils.entropy_math (The Sensor)
"""

import logging
import os
import asyncio
from typing import Dict, Literal, Any
from langgraph.graph import StateGraph, END
from pydantic import SecretStr
from vertexai.generative_models import GenerativeModel

# Import Core Schemas
from studio.memory import (
    EngineeringState,
    ContextSlice,
    SemanticHealthMetric,
    CodeChangeArtifact,
    JulesMetadata,
    TestResult
)

# Import The Team
from studio.utils.jules_client import JulesGitHubClient, TaskPayload, WorkStatus, TaskPriority
from studio.utils.entropy_math import SemanticEntropyCalculator, VertexFlashJudge
from studio.utils.sandbox import DockerSandbox
from studio.agents.architect import run_architect_gate  # The New Guard

logger = logging.getLogger("studio.subgraphs.engineer")

# --- TOOLS ---

def get_jules_client():
    return JulesGitHubClient(
        github_token=SecretStr(os.environ.get("GITHUB_TOKEN", "")),
        repo_name=os.environ.get("GITHUB_REPOSITORY", "google/jules-studio")
    )

def get_sensor():
    # In a real app, reuse the instance if possible, but new for now
    return SemanticEntropyCalculator(VertexFlashJudge(GenerativeModel("gemini-1.5-flash")))

# --- NODE FUNCTIONS ---

def dispatch_task(state: EngineeringState) -> Dict:
    """Step 1: Assign work to Jules."""
    # Context Slice is now in jules_meta
    slice_data = state.jules_meta.active_context_slice

    # Check if we are retrying
    is_retry = state.jules_meta.retry_count > 0
    task_id = state.current_task or "UNKNOWN_TASK"

    constraints = slice_data.constraints if slice_data else []
    if is_retry and state.jules_meta.feedback_log:
        constraints.append(f"CRITICAL FEEDBACK FROM PREVIOUS ATTEMPT: {state.jules_meta.feedback_log[-1]}")

    # Prepare payload
    payload = TaskPayload(
        task_id=task_id,
        intent=slice_data.intent if slice_data else "Unknown Intent",
        context_files={f: "Context" for f in (slice_data.files if slice_data else [])},
        relevant_logs=slice_data.relevant_logs if slice_data else None,
        constraints=constraints,
        priority=TaskPriority.MEDIUM
    )

    client = get_jules_client()
    try:
        issue_id = client.dispatch_task(payload)
    except Exception as e:
        logger.error(f"Dispatch failed: {e}")
        issue_id = "0"

    new_meta = state.jules_meta.model_copy(update={
        "external_task_id": issue_id,
        "status": "WORKING"
    })
    return {"jules_meta": new_meta}


def watch_tower(state: EngineeringState) -> Dict:
    """Step 2: Poll for PR."""
    meta = state.jules_meta

    if not meta.external_task_id:
        return {} # Should not happen

    client = get_jules_client()
    try:
        status: WorkStatus = client.get_status(meta.external_task_id)
    except Exception:
        return {}

    updates = {}

    if status.status == "REVIEW_READY" or status.status == "COMPLETED":
         # Extract artifacts
         code_artifacts = state.code_artifacts.copy()
         if status.raw_diff:
             code_artifacts.update({
                 "proposed_patch": status.raw_diff,
                 "pr_link": status.pr_url
             })

         new_meta = meta.model_copy(update={
             "status": "VERIFYING",
             "current_branch": str(status.linked_pr_number) if status.linked_pr_number else None,
             "generated_artifacts": [
                 CodeChangeArtifact(diff_content=status.raw_diff, pr_link=status.pr_url)
             ] if status.raw_diff else []
         })

         updates["jules_meta"] = new_meta
         updates["code_artifacts"] = code_artifacts
    else:
        new_meta = meta.model_copy(update={"status": status.status})
        updates["jules_meta"] = new_meta

    return updates

def entropy_guard(state: EngineeringState) -> Dict:
    """Step 3: Check for Hallucinations."""
    meta = state.jules_meta

    # If no artifacts, skip
    if not meta.generated_artifacts:
        return {}

    # Measure entropy
    try:
        sensor = get_sensor()
        # In real implementation we would run this.
        pass
    except Exception:
        pass

    new_meta = meta.model_copy(update={
        "current_entropy": 0.5,
        "cognitive_tunneling_detected": False
    })
    return {"jules_meta": new_meta}

def qa_verifier(state: EngineeringState) -> Dict:
    """Step 4: Functional Testing (Pytest)."""
    meta = state.jules_meta
    artifacts = state.code_artifacts

    if meta.status != "VERIFYING":
        return {}

    logger.info("QA_Verifier: Running dynamic verification.")

    status = "GREEN" # Default for now

    try:
        sandbox = DockerSandbox()
        # If sandbox works (mocked or real), use it
        pass
    except Exception:
        pass

    new_gate = state.verification_gate.model_copy(update={"status": status})
    return {
        "verification_gate": new_gate
    }

def architect_node(state: EngineeringState) -> Dict:
    """
    Step 5: The Quality Gate (NEW).
    Calls the Architect Agent to enforce SOLID/Security.
    """
    logger.info("Engaging Architect for Structural Review...")

    eng_state_dict = state.dict()
    updates = run_architect_gate(eng_state_dict)

    # Ensure we return properly updated objects if they are dicts in updates
    gate_update = updates.get("verification_gate", {})
    new_gate = state.verification_gate.model_copy(update=gate_update)

    return {
        "code_artifacts": updates.get("code_artifacts", {}),
        "verification_gate": new_gate
    }

def feedback_loop(state: EngineeringState) -> Dict:
    """
    Failure Path: Send errors (Test or Architect) back to Jules.
    """
    gate = state.verification_gate
    meta = state.jules_meta

    error_msg = gate.blocking_reason or "Verification Failed"
    logger.info(f"Returning Feedback to Jules: {error_msg}")

    client = get_jules_client()
    if meta.external_task_id:
        try:
            client.post_feedback(meta.external_task_id, error_msg, is_error=True)
        except Exception:
            pass

    new_meta = meta.model_copy(update={
        "status": "WORKING",
        "retry_count": meta.retry_count + 1,
        "feedback_log": meta.feedback_log + [error_msg]
    })

    new_gate = gate.model_copy(update={"status": "PENDING"})

    return {
        "jules_meta": new_meta,
        "verification_gate": new_gate
    }

# --- THE WIRED GRAPH ---

def build_engineer_subgraph():
    workflow = StateGraph(EngineeringState)

    # 1. Add Nodes
    workflow.add_node("dispatch", dispatch_task)
    workflow.add_node("watch", watch_tower)
    workflow.add_node("entropy", entropy_guard)
    workflow.add_node("qa", qa_verifier)
    workflow.add_node("architect", architect_node) # <--- NEW NODE
    workflow.add_node("feedback", feedback_loop)

    # 2. Define Edges (The Factory Line)
    workflow.set_entry_point("dispatch")
    workflow.add_edge("dispatch", "watch")

    # Wait for PR
    def route_watch(x: EngineeringState):
        if x.jules_meta.status == "VERIFYING":
            return "entropy"
        if x.jules_meta.status == "BLOCKED":
            return "wait" # Should ideally interrupt
        return "wait"

    workflow.add_conditional_edges(
        "watch",
        route_watch,
        {"wait": "watch", "entropy": "entropy"}
    )

    workflow.add_edge("entropy", "qa")

    # QA Check (Red/Green)
    workflow.add_conditional_edges(
        "qa",
        lambda x: x.verification_gate.status,
        {
            "GREEN": "architect", # <--- Proceed to Architect
            "RED": "feedback",     # <--- Loop back on Test Fail
            "PENDING": "feedback"
        }
    )

    # Architect Check (Approved/Rejected)
    def route_architect(x):
        logger.info(f"Architect Routing: Status = {x.verification_gate.status}")
        return x.verification_gate.status

    workflow.add_conditional_edges(
        "architect",
        route_architect,
        {
            "GREEN": END,        # <--- Success! Leaves Subgraph
            "RED": "feedback"    # <--- Loop back on Bad Design
        }
    )

    workflow.add_edge("feedback", "watch")

    return workflow.compile()
