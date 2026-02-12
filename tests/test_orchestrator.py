import os
import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from studio.memory import StudioState, OrchestrationState, EngineeringState, TriageStatus, SemanticHealthMetric
from studio.orchestrator import Orchestrator

# Set mock project to avoid Google Auth errors
os.environ["GOOGLE_CLOUD_PROJECT"] = "mock-project"

@patch("studio.orchestrator.VertexFlashJudge")
@patch("studio.orchestrator.GenerativeModel")
def test_orchestrator_coding_flow(mock_gen_model, mock_vertex_judge):
    # Setup state for CODING intent
    orch_state = OrchestrationState(
        session_id="test_1",
        user_intent="UNKNOWN", # Router should set this
        triage_status=TriageStatus(is_log_available=True, suspected_domain="drivers")
    )
    eng_state = EngineeringState()
    state = StudioState(orchestration=orch_state, engineering=eng_state)

    orchestrator = Orchestrator()

    # Mock the calculator to avoid network calls and return a safe metric
    mock_metric = SemanticHealthMetric(
        entropy_score=0.5,
        threshold=7.0,
        sample_size=5,
        is_tunneling=False,
        cluster_distribution={}
    )
    orchestrator.calculator.measure_uncertainty = AsyncMock(return_value=mock_metric)

    # Run the graph using async API because it contains async nodes
    final_state = asyncio.run(orchestrator.app.ainvoke(state))

    # If final_state is a dict, we access keys.
    if isinstance(final_state, dict):
        orch = final_state["orchestration"]
        eng = final_state["engineering"]
        cb = final_state.get("circuit_breaker_triggered", False)
    else:
        orch = final_state.orchestration
        eng = final_state.engineering
        cb = final_state.circuit_breaker_triggered

    # Assertions
    # 1. Intent should be CODING
    if isinstance(orch, dict):
         assert orch["user_intent"] == "CODING"
         assert orch["current_context_slice"] is not None
         assert orch["current_context_slice"]["slice_id"].startswith("slice_")
         assert eng["proposed_patch"] == "Patch applied."
         # assert orch["latest_entropy"] == 0.5 # Removed
    else:
         assert orch.user_intent == "CODING"
         assert orch.current_context_slice is not None
         assert orch.current_context_slice.slice_id.startswith("slice_")
         assert eng.proposed_patch == "Patch applied."
         # assert orch.latest_entropy == 0.5 # Removed

    # Check Circuit Breaker (Should be False as entropy is 0.5 < 7.0)
    assert not cb

@patch("studio.orchestrator.VertexFlashJudge")
@patch("studio.orchestrator.GenerativeModel")
def test_orchestrator_sop_flow(mock_gen_model, mock_vertex_judge):
    # Setup state for SOP intent (No Log)
    orch_state = OrchestrationState(
        session_id="test_2",
        user_intent="UNKNOWN",
        triage_status=TriageStatus(is_log_available=False, suspected_domain="unknown")
    )
    eng_state = EngineeringState()
    state = StudioState(orchestration=orch_state, engineering=eng_state)

    orchestrator = Orchestrator()

    # Run the graph using async API because it contains async nodes
    final_state = asyncio.run(orchestrator.app.ainvoke(state))

    if isinstance(final_state, dict):
        orch = final_state["orchestration"]
    else:
        orch = final_state.orchestration

    if isinstance(orch, dict):
        assert orch["user_intent"] == "INTERACTIVE_GUIDE"
        sop = orch["guidance_sop"]
        assert sop is not None
        assert sop["active_sop_id"] == "NO_LOG_DEBUG"
        assert sop["current_step_index"] == 1
    else:
        assert orch.user_intent == "INTERACTIVE_GUIDE"
        sop = orch.guidance_sop
        assert sop is not None
        assert sop.active_sop_id == "NO_LOG_DEBUG"
        assert sop.current_step_index == 1
