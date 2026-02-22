import os
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from studio.memory import (
    StudioState, OrchestrationState, EngineeringState, TriageStatus,
    SemanticHealthMetric, JulesMetadata, CodeChangeArtifact, Ticket
)
from studio.orchestrator import Orchestrator

# Set mock project to avoid Google Auth errors
os.environ["GOOGLE_CLOUD_PROJECT"] = "mock-project"

@pytest.mark.asyncio
@patch("studio.orchestrator.VertexFlashJudge")
@patch("studio.orchestrator.GenerativeModel")
async def test_router_case_a_coding_with_log(mock_gen_model, mock_vertex_judge):
    """
    Case A: 用戶意圖 "Fix Bug"，附帶 Log -> 進入 Engineer Subgraph。
    """
    # Setup state for CODING intent with Log
    orch_state = OrchestrationState(
        session_id="test_case_a",
        user_intent="Fix Bug",
        triage_status=TriageStatus(is_log_available=True, suspected_domain="drivers"),
        task_queue=[
            Ticket(id="TKT-1", title="Fix the bug", description="Fix it", priority="HIGH", source_section_id="1.1")
        ]
    )
    eng_state = EngineeringState()
    state = StudioState(orchestration=orch_state, engineering=eng_state)

    # Mock the engineer subgraph to avoid external IO
    mock_engineer_app = MagicMock()
    mock_engineer_app.ainvoke = AsyncMock(return_value={
        "jules_metadata": JulesMetadata(
            status="COMPLETED",
            generated_artifacts=[CodeChangeArtifact(diff_content="Patch applied.")]
        )
    })

    orchestrator = Orchestrator(engineer_app=mock_engineer_app)

    # Mock the calculator to avoid network calls
    mock_metric = SemanticHealthMetric(
        entropy_score=0.5,
        threshold=2.0,
        sample_size=5,
        is_tunneling=False,
        cluster_distribution={}
    )
    orchestrator.calculator.measure_uncertainty = AsyncMock(return_value=mock_metric)

    # Track executed nodes
    executed_nodes = []
    async for event in orchestrator.app.astream(state):
        for node_name in event.keys():
            executed_nodes.append(node_name)

    # Assertions
    assert "intent_router" in executed_nodes
    assert "backlog_dispatcher" in executed_nodes
    assert "context_slicer" in executed_nodes
    assert "engineer_subgraph" in executed_nodes
    assert "sop_guide_subgraph" not in executed_nodes

@pytest.mark.asyncio
@patch("studio.orchestrator.VertexFlashJudge")
@patch("studio.orchestrator.GenerativeModel")
async def test_router_case_b_sop_no_log(mock_gen_model, mock_vertex_judge):
    """
    Case B: 用戶意圖 "My phone is hot"，無 Log -> 進入 SOP Guide。
    """
    # Setup state for NO_LOG intent
    orch_state = OrchestrationState(
        session_id="test_case_b",
        user_intent="My phone is hot",
        triage_status=TriageStatus(is_log_available=False, suspected_domain="unknown")
    )
    eng_state = EngineeringState()
    state = StudioState(orchestration=orch_state, engineering=eng_state)

    orchestrator = Orchestrator()

    # Track executed nodes
    executed_nodes = []
    async for event in orchestrator.app.astream(state):
        for node_name in event.keys():
            executed_nodes.append(node_name)

    # Assertions
    assert "intent_router" in executed_nodes
    assert "sop_guide_subgraph" in executed_nodes
    assert "backlog_dispatcher" not in executed_nodes
    assert "engineer_subgraph" not in executed_nodes
