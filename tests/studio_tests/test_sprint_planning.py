import pytest
import asyncio
import os
from unittest.mock import MagicMock, AsyncMock, patch
from studio.memory import (
    StudioState, OrchestrationState, EngineeringState, Ticket
)
from studio.orchestrator import Orchestrator

# Set mock project to avoid Google Auth errors
os.environ["GOOGLE_CLOUD_PROJECT"] = "mock-project"

@pytest.mark.asyncio
@patch("studio.orchestrator.VertexFlashJudge")
@patch("studio.orchestrator.GenerativeModel")
async def test_node_sprint_planning_moves_tickets(mock_gen_model, mock_vertex_judge):
    """
    Test that node_sprint_planning moves up to 3 tickets from task_queue to sprint_backlog.
    """
    tickets = [
        Ticket(id=f"TKT-{i}", title=f"Task {i}", description=f"Desc {i}", priority="HIGH", source_section_id="1")
        for i in range(5)
    ]

    orch_state = OrchestrationState(
        session_id="test_session",
        user_intent="CODING",
        task_queue=tickets,
        sprint_backlog=[]
    )
    state = StudioState(orchestration=orch_state, engineering=EngineeringState())

    orchestrator = Orchestrator()

    # Run node_sprint_planning
    result = await orchestrator.node_sprint_planning(state)

    updated_orch = result["orchestration"]
    assert len(updated_orch.sprint_backlog) == 3
    assert len(updated_orch.task_queue) == 2
    assert updated_orch.sprint_goal is not None
    assert "batch of 3" in updated_orch.sprint_goal

    # Verify which tickets were moved (the first 3)
    moved_ids = {t.id for t in updated_orch.sprint_backlog}
    assert moved_ids == {"TKT-0", "TKT-1", "TKT-2"}

    remaining_ids = {t.id for t in updated_orch.task_queue}
    assert remaining_ids == {"TKT-3", "TKT-4"}

@pytest.mark.asyncio
@patch("studio.orchestrator.VertexFlashJudge")
@patch("studio.orchestrator.GenerativeModel")
async def test_node_sprint_planning_skips_if_not_empty(mock_gen_model, mock_vertex_judge):
    """
    Test that node_sprint_planning returns unchanged state if sprint_backlog is not empty.
    """
    existing_ticket = Ticket(id="TKT-EXISTING", title="Existing", description="Desc", priority="HIGH", source_section_id="1")
    queued_ticket = Ticket(id="TKT-QUEUED", title="Queued", description="Desc", priority="HIGH", source_section_id="1")

    orch_state = OrchestrationState(
        session_id="test_session",
        user_intent="CODING",
        task_queue=[queued_ticket],
        sprint_backlog=[existing_ticket]
    )
    state = StudioState(orchestration=orch_state, engineering=EngineeringState())

    orchestrator = Orchestrator()

    result = await orchestrator.node_sprint_planning(state)

    # Should be empty dict or same state
    assert result == {} or result.get("orchestration") is None

@pytest.mark.asyncio
@patch("studio.orchestrator.VertexFlashJudge")
@patch("studio.orchestrator.GenerativeModel")
async def test_graph_topology_rewiring(mock_gen_model, mock_vertex_judge):
    """
    Test that the graph is rewired correctly.
    """
    orchestrator = Orchestrator()

    # Check edges in the workflow
    edges = orchestrator.workflow.edges

    # product_owner -> sprint_planning
    assert ("product_owner", "sprint_planning") in edges

    # sprint_planning -> backlog_dispatcher
    assert ("sprint_planning", "backlog_dispatcher") in edges

    # Check that product_owner -> backlog_dispatcher is REMOVED
    assert ("product_owner", "backlog_dispatcher") not in edges

    # Check conditional edges from intent_router
    # This is harder to check directly on the builder without internal knowledge,
    # but we can try to find them.
    # Alternatively, we can run a mock state through the graph and see where it goes.
