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
from typing import Dict, Literal, Any
from langgraph.graph import StateGraph, END
from pydantic import SecretStr

# Import Core Schemas
from studio.memory import (
    EngineeringState,
    ContextSlice,
    SemanticHealthMetric,
    CodeArtifacts,
    JulesMetadata
)

# Import The Team
from studio.utils.jules_client import JulesGitHubClient, TaskPayload, WorkStatus, TaskPriority
from studio.utils.entropy_math import SemanticEntropyCalculator, VertexFlashJudge
from studio.utils.sandbox import DockerSandbox
from studio.agents.architect import run_architect_gate  # The New Guard

logger = logging.getLogger("studio.subgraphs.engineer")

# --- MOCK TOOLS FOR SCAFFOLDING (Replace with real instances in PROD) ---
# In a real app, these are injected via config or context.
CLIENT = None
SENSOR = None

def get_jules_client():
    # Singleton pattern or Dependency Injection here
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "google/jules-studio")
    return JulesGitHubClient(github_token=SecretStr(token), repo_name=repo)

def get_sensor():
    # Mock or Real implementation depending on context
    # This would typically be initialized once in Orchestrator
    # For now, we return None or rely on mocking in tests
    return None

# --- NODE FUNCTIONS ---

def dispatch_task(state: EngineeringState) -> Dict:
    """Step 1: Assign work to Jules."""
    slice_data = state.jules_meta.active_context_slice

    # In Phase 2, we use the specific ticket details
    # Fallback if slice_data is None/Empty
    intent = slice_data.intent if slice_data else "CODING"
    files = slice_data.active_files if slice_data else {}
    logs = slice_data.relevant_logs if slice_data else ""
    constraints = slice_data.constraints if slice_data else []

    payload = TaskPayload(
        task_id=state.current_task or "unknown",
        intent=intent,
        context_files=files,
        relevant_logs=logs,
        constraints=constraints,
        priority=TaskPriority.MEDIUM
    )

    # Mock for Simulation if client not configured
    # client = get_jules_client()
    # issue_id = client.dispatch_task(payload)
    issue_id = "101"

    # We update jules_meta using model_copy if needed, but here we return a dict update
    # The LangGraph merge strategy for Pydantic models usually requires returning the new model
    # OR a dict that can be merged.
    # EngineeringState uses Pydantic V2.

    new_meta = state.jules_meta.model_copy(update={
        "external_task_id": issue_id,
        "status": "WORKING"
    })

    return {
        "jules_meta": new_meta
    }

def watch_tower(state: EngineeringState) -> Dict:
    """Step 2: Poll for PR."""
    meta = state.jules_meta

    # Mocking the PR arrival for Simulation
    # In real life: client.get_status(meta.linked_issue_id)
    # We simulate a "Ready" state after 1 tick

    # For now, we simulate finding a PR
    new_meta = meta.model_copy(update={
        "status": "VERIFYING", # review_requested equivalent
    })

    new_artifacts = CodeArtifacts(
        proposed_patch="+ def secure_code(): ...",
        justification_refs=["Auto-Jules"]
    )

    return {
        "jules_meta": new_meta,
        "code_artifacts": new_artifacts
    }

def entropy_guard(state: EngineeringState) -> Dict:
    """Step 3: Check for Hallucinations."""
    # Mocking Low Entropy (Healthy)
    return {
        "jules_meta": state.jules_meta.model_copy(update={
            "current_entropy": 0.5,
            "cognitive_tunneling_detected": False
        })
    }

def qa_verifier(state: EngineeringState) -> Dict:
    """Step 4: Functional Testing (Pytest)."""
    # Mocking a Pass
    return {
        "verification_gate": {
            "status": "GREEN"
        }
    }

def architect_node(state: EngineeringState) -> Dict:
    """
    Step 5: The Quality Gate (NEW).
    Calls the Architect Agent to enforce SOLID/Security.
    """
    logger.info("Engaging Architect for Structural Review...")

    # We unpack the EngineeringState to match the helper's signature
    # Note: In LangGraph, 'state' here is the dictionary of the subgraph state
    # if using TypedDict, but here we use Pydantic.
    # We pass the dict representation.
    eng_state_dict = state.dict()

    # Run the Gate
    # This uses the 'run_architect_gate' helper we fixed in the previous turn
    updates = run_architect_gate(eng_state_dict)

    # The helper returns partial updates (code_artifacts, verification_gate)
    # We must map them back to the state structure

    # Ensure code_artifacts is a model
    new_artifacts = state.code_artifacts.model_copy(update=updates.get("code_artifacts", {}))

    return {
        "code_artifacts": new_artifacts,
        "verification_gate": updates.get("verification_gate", state.verification_gate)
    }

def feedback_loop(state: EngineeringState) -> Dict:
    """
    Failure Path: Send errors (Test or Architect) back to Jules.
    """
    gate = state.verification_gate
    meta = state.jules_meta

    error_msg = gate.blocking_reason
    logger.info(f"Returning Feedback to Jules: {error_msg}")

    # In real life: client.post_feedback(meta.linked_issue_id, error_msg)

    new_meta = meta.model_copy(update={
        "status": "WORKING", # Reset to working
        "retry_count": meta.retry_count + 1
    })

    return {
        "jules_meta": new_meta, # Reset to waiting
        "verification_gate": {"status": "PENDING"} # Reset gate
    }

# --- THE WIRED GRAPH ---

def build_engineer_subgraph():
    workflow = StateGraph(EngineeringState)

    # 1. Add Nodes
    workflow.add_node("dispatch", dispatch_task)
    workflow.add_node("watch", watch_tower)
    workflow.add_node("entropy", entropy_guard)
    workflow.add_node("qa", qa_verifier)
    workflow.add_node("architect_gate", architect_node) # <--- NEW NODE (Renamed to match Design)
    workflow.add_node("feedback", feedback_loop)

    # 2. Define Edges (The Factory Line)
    workflow.set_entry_point("dispatch")
    workflow.add_edge("dispatch", "watch")

    # Wait for PR
    # Using jules_meta.status instead of interaction_status
    workflow.add_conditional_edges(
        "watch",
        lambda x: "review" if x.jules_meta.status == "VERIFYING" else "wait",
        {"wait": "watch", "review": "entropy"}
    )

    workflow.add_edge("entropy", "qa")

    # QA Check (Red/Green)
    workflow.add_conditional_edges(
        "qa",
        lambda x: x.verification_gate.status,
        {
            "GREEN": "architect_gate", # <--- Proceed to Architect
            "RED": "feedback"     # <--- Loop back on Test Fail
        }
    )

    # Architect Check (Approved/Rejected)
    workflow.add_conditional_edges(
        "architect_gate",
        lambda x: x.verification_gate.status,
        {
            "GREEN": END,        # <--- Success! Leaves Subgraph
            "RED": "feedback"    # <--- Loop back on Bad Design
        }
    )

    workflow.add_edge("feedback", "watch")

    return workflow.compile()
