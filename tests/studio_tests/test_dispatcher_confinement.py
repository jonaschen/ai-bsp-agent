import pytest
import asyncio
import os
from unittest.mock import MagicMock, AsyncMock, patch
from studio.memory import (
    StudioState, OrchestrationState, EngineeringState, Ticket, JulesMetadata
)
from studio.orchestrator import Orchestrator

# Set mock project to avoid Google Auth errors
os.environ["GOOGLE_CLOUD_PROJECT"] = "mock-project"

@pytest.mark.asyncio
@patch("studio.orchestrator.VertexFlashJudge")
@patch("studio.orchestrator.GenerativeModel")
async def test_dispatcher_pulls_from_sprint_backlog_only(mock_gen_model, mock_vertex_judge):
    """
    TDD: Proves that the dispatcher ignores task_queue and only pulls from sprint_backlog.
    """
    # Setup: task_queue has TKT-GLOBAL, sprint_backlog has TKT-SPRINT
    tkt_global = Ticket(id="TKT-GLOBAL", title="Global Task", description="In global queue", priority="LOW", source_section_id="0")
    tkt_sprint = Ticket(id="TKT-SPRINT", title="Sprint Task", description="In sprint backlog", priority="HIGH", source_section_id="1")

    orch_state = OrchestrationState(
        session_id="test_session",
        user_intent="CODING",
        task_queue=[tkt_global],
        sprint_backlog=[tkt_sprint]
    )
    eng_state = EngineeringState()
    state = StudioState(orchestration=orch_state, engineering=eng_state)

    orchestrator = Orchestrator()

    # 1. Test node_backlog_dispatcher
    result = await orchestrator.node_backlog_dispatcher(state)

    # After the fix, it should pick TKT-SPRINT.
    # Currently it picks TKT-GLOBAL (because it looks at task_queue).
    new_eng = result["engineering"]
    assert new_eng.current_task == "Sprint Task: In sprint backlog"
    assert new_eng.current_task != "Global Task: In global queue"

@pytest.mark.asyncio
@patch("studio.orchestrator.VertexFlashJudge")
@patch("studio.orchestrator.GenerativeModel")
async def test_decide_loop_route_uses_sprint_backlog(mock_gen_model, mock_vertex_judge):
    """
    TDD: Proves that _decide_loop_route checks sprint_backlog instead of task_queue.
    """
    tkt_global = Ticket(id="TKT-GLOBAL", title="Global Task", description="In global queue", priority="LOW", source_section_id="0")

    # Case: task_queue NOT empty, but sprint_backlog IS empty
    orch_state = OrchestrationState(
        session_id="test_session",
        user_intent="CODING",
        task_queue=[tkt_global],
        sprint_backlog=[]
    )
    state = StudioState(orchestration=orch_state, engineering=EngineeringState())

    orchestrator = Orchestrator()

    # After the fix, it should return "done" because sprint_backlog is empty.
    # Currently it returns "next" because task_queue is not empty.
    route = orchestrator._decide_loop_route(state)
    assert route == "done"

@pytest.mark.asyncio
@patch("studio.orchestrator.VertexFlashJudge")
@patch("studio.orchestrator.GenerativeModel")
async def test_status_updates_apply_to_sprint_backlog(mock_gen_model, mock_vertex_judge):
    """
    TDD: Proves that completed/failed status updates apply to sprint_backlog.
    """
    tkt_sprint = Ticket(id="TKT-SPRINT", title="Sprint Task", description="In sprint backlog", priority="HIGH", source_section_id="1", status="IN_PROGRESS")

    orch_state = OrchestrationState(
        session_id="test_session",
        user_intent="CODING",
        sprint_backlog=[tkt_sprint]
    )

    # Simulate a completed task
    eng_state = EngineeringState(
        current_task="Sprint Task: In sprint backlog",
        jules_meta=JulesMetadata(session_id="test_session", status="COMPLETED")
    )
    state = StudioState(orchestration=orch_state, engineering=eng_state)

    orchestrator = Orchestrator()

    result = await orchestrator.node_backlog_dispatcher(state)

    updated_orch = result["orchestration"]
    # TKT-SPRINT should be removed from sprint_backlog and added to completed_tasks_log
    assert len(updated_orch.sprint_backlog) == 0
    assert len(updated_orch.completed_tasks_log) == 1
    assert updated_orch.completed_tasks_log[0].id == "TKT-SPRINT"
