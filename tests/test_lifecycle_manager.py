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

@patch("studio.orchestrator.VertexFlashJudge")
@patch("studio.orchestrator.GenerativeModel")
@patch("studio.orchestrator.run_po_cycle")
@patch("studio.orchestrator.run_scrum_retrospective")
def test_orchestrator_lifecycle_manager(mock_run_retrospective, mock_run_po, mock_gen_model, mock_vertex_judge):
    # Setup state
    orch_state = OrchestrationState(
        session_id="test_lifecycle",
        user_intent="SPRINT",
        triage_status=TriageStatus(is_log_available=True, suspected_domain="drivers")
    )
    eng_state = EngineeringState()
    state = StudioState(orchestration=orch_state, engineering=eng_state)

    # 1. Mock Product Owner to return 2 tickets
    mock_run_po.return_value = [
        Ticket(id="TKT-1", title="Task 1", description="Desc 1", priority="HIGH", source_section_id="1.1"),
        Ticket(id="TKT-2", title="Task 2", description="Desc 2", priority="MEDIUM", source_section_id="1.2")
    ]

    # 2. Mock Engineer Subgraph
    mock_engineer_app = MagicMock()
    # First call: TKT-1 COMPLETED, Second call: TKT-2 FAILED
    mock_engineer_app.ainvoke = AsyncMock()
    mock_engineer_app.ainvoke.side_effect = [
        {"jules_metadata": JulesMetadata(status="COMPLETED", generated_artifacts=[CodeChangeArtifact(diff_content="Patch 1")])},
        {"jules_metadata": JulesMetadata(status="FAILED", feedback_log=["Error in Task 2"])}
    ]

    # 3. Mock Scrum Master
    mock_run_retrospective.return_value = MagicMock()

    # 4. Mock Calculator
    orchestrator = Orchestrator(engineer_app=mock_engineer_app)
    mock_metric = SemanticHealthMetric(
        entropy_score=0.5,
        threshold=7.0,
        sample_size=5,
        is_tunneling=False,
        cluster_distribution={}
    )
    orchestrator.calculator.measure_uncertainty = AsyncMock(return_value=mock_metric)

    # Run the graph
    final_state = asyncio.run(orchestrator.app.ainvoke(state))

    # Assertions
    if isinstance(final_state, dict):
        orch = final_state["orchestration"]
    else:
        orch = final_state.orchestration

    # Check if both tickets were processed
    if isinstance(orch, dict):
        assert len(orch["completed_tasks_log"]) == 1
        assert orch["completed_tasks_log"][0].id == "TKT-1"
        assert len(orch["failed_tasks_log"]) == 1
        assert orch["failed_tasks_log"][0].id == "TKT-2"
        assert len(orch["task_queue"]) == 0
    else:
        assert len(orch.completed_tasks_log) == 1
        assert orch.completed_tasks_log[0].id == "TKT-1"
        assert len(orch.failed_tasks_log) == 1
        assert orch.failed_tasks_log[0].id == "TKT-2"
        assert len(orch.task_queue) == 0

    # Verify PO and SM were called
    mock_run_po.assert_called_once()
    mock_run_retrospective.assert_called_once()

    # Verify Engineer was called twice
    assert mock_engineer_app.ainvoke.call_count == 2
