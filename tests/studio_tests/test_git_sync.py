import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from studio.memory import (
    StudioState, OrchestrationState, EngineeringState, JulesMetadata, Ticket
)
from studio.orchestrator import Orchestrator

@pytest.mark.asyncio
@patch("studio.orchestrator.VertexFlashJudge")
@patch("studio.orchestrator.GenerativeModel")
@patch("studio.orchestrator.asyncio.to_thread")
async def test_node_backlog_dispatcher_syncs_git_on_completion(mock_to_thread, mock_gen_model, mock_vertex_judge):
    # Setup state where a task has just COMPLETED
    completed_ticket = Ticket(
        id="TKT-1",
        title="Test Task",
        description="A test task",
        priority="HIGH",
        source_section_id="1.1",
        status="OPEN"
    )

    orch_state = OrchestrationState(
        session_id="test_session",
        user_intent="CODING",
        sprint_backlog=[completed_ticket]
    )

    eng_state = EngineeringState(
        current_task="Test Task: A test task",
        jules_meta=JulesMetadata(status="COMPLETED")
    )

    state = StudioState(orchestration=orch_state, engineering=eng_state)

    # We need to import the sync_main_branch function to mock it
    # Even if it doesn't exist yet, we can patch the path where it will be called.
    with patch("studio.orchestrator.sync_main_branch", create=True) as mock_sync:
        orchestrator = Orchestrator()

        # We need to mock to_thread to actually call the mocked sync_main_branch if we use to_thread
        async def side_effect(func, *args, **kwargs):
            if func == mock_sync:
                return func(*args, **kwargs)
            return MagicMock()

        mock_to_thread.side_effect = side_effect

        await orchestrator.node_backlog_dispatcher(state)

        # Verify sync_main_branch was called
        mock_sync.assert_called_once()

@pytest.mark.asyncio
@patch("studio.orchestrator.VertexFlashJudge")
@patch("studio.orchestrator.GenerativeModel")
@patch("studio.orchestrator.asyncio.to_thread")
async def test_node_backlog_dispatcher_does_not_sync_git_on_failure(mock_to_thread, mock_gen_model, mock_vertex_judge):
    # Setup state where a task has FAILED
    failed_ticket = Ticket(
        id="TKT-2",
        title="Failed Task",
        description="A task that failed",
        priority="HIGH",
        source_section_id="1.1",
        status="OPEN"
    )

    orch_state = OrchestrationState(
        session_id="test_session",
        user_intent="CODING",
        sprint_backlog=[failed_ticket]
    )

    eng_state = EngineeringState(
        current_task="Failed Task: A task that failed",
        jules_meta=JulesMetadata(status="FAILED")
    )

    state = StudioState(orchestration=orch_state, engineering=eng_state)

    with patch("studio.orchestrator.sync_main_branch", create=True) as mock_sync:
        orchestrator = Orchestrator()
        await orchestrator.node_backlog_dispatcher(state)

        # Verify sync_main_branch was NOT called
        mock_sync.assert_not_called()
