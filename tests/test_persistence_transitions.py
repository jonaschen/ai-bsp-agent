import os
import json
import pytest
import asyncio
import tempfile
from unittest.mock import MagicMock, AsyncMock, patch
from studio.memory import (
    StudioState, OrchestrationState, EngineeringState, Ticket,
    JulesMetadata, SemanticHealthMetric
)
from studio.orchestrator import Orchestrator
from studio.manager import StudioManager

# Set mock project to avoid Google Auth errors
os.environ["GOOGLE_CLOUD_PROJECT"] = "mock-project"

@patch("studio.orchestrator.sync_main_branch")
@patch("studio.orchestrator.VertexFlashJudge")
@patch("studio.orchestrator.GenerativeModel")
@pytest.mark.asyncio
async def test_persistence_on_task_completion(mock_gen_model, mock_vertex_judge, mock_sync):
    with tempfile.TemporaryDirectory() as temp_dir:
        # Initialize Manager and State
        manager = StudioManager(root_dir=temp_dir)
        ticket = Ticket(id="TKT-1", title="Task 1", description="Desc", priority="HIGH", source_section_id="1.1", status="IN_PROGRESS")
        manager.state.orchestration.sprint_backlog = [ticket]
        manager.state.engineering.current_task = "Task 1: Desc"
        manager.state.engineering.jules_meta = JulesMetadata(status="COMPLETED")

        # Setup Orchestrator with Manager
        mock_engineer_app = MagicMock()
        orchestrator = Orchestrator(engineer_app=mock_engineer_app, manager=manager)

        # Invoke node_backlog_dispatcher
        await orchestrator.node_backlog_dispatcher(manager.state)

        # Verify studio_state.json on disk matches in-memory state
        state_path = os.path.join(temp_dir, "studio_state.json")
        assert os.path.exists(state_path)
        with open(state_path, "r") as f:
            saved_data = json.load(f)
            # Ticket should be removed from backlog and added to completed_tasks_log
            assert len(saved_data["orchestration"]["sprint_backlog"]) == 0
            assert len(saved_data["orchestration"]["completed_tasks_log"]) == 1
            assert saved_data["orchestration"]["completed_tasks_log"][0]["id"] == "TKT-1"

@patch("studio.orchestrator.VertexFlashJudge")
@patch("studio.orchestrator.GenerativeModel")
@pytest.mark.asyncio
async def test_persistence_on_circuit_breaker(mock_gen_model, mock_vertex_judge):
    with tempfile.TemporaryDirectory() as temp_dir:
        # Initialize Manager and State
        manager = StudioManager(root_dir=temp_dir)
        manager.state.orchestration.user_intent = "CODING"
        manager.state.engineering.current_task = "Fix bug"

        # Setup Orchestrator with Manager and Mock Entropy
        mock_engineer_app = MagicMock()
        mock_engineer_app.ainvoke = AsyncMock(return_value={
            "jules_metadata": JulesMetadata(status="WORKING", generated_artifacts=[])
        })

        orchestrator = Orchestrator(engineer_app=mock_engineer_app, manager=manager)

        # Mock high entropy to trigger circuit breaker
        mock_metric = SemanticHealthMetric(
            entropy_score=9.5,
            threshold=7.0,
            sample_size=5,
            is_tunneling=True,
            cluster_distribution={}
        )
        orchestrator.calculator.measure_uncertainty = AsyncMock(return_value=mock_metric)

        # Invoke _engineer_wrapper
        await orchestrator._engineer_wrapper(manager.state)

        # Verify studio_state.json on disk
        state_path = os.path.join(temp_dir, "studio_state.json")
        assert os.path.exists(state_path)
        with open(state_path, "r") as f:
            saved_data = json.load(f)
            assert saved_data["circuit_breaker_triggered"] is True
            assert saved_data["engineering"]["jules_meta"]["status"] == "WORKING"

@patch("studio.orchestrator.sync_main_branch")
@patch("studio.orchestrator.VertexFlashJudge")
@patch("studio.orchestrator.GenerativeModel")
@pytest.mark.asyncio
async def test_no_redispatch_after_recovery(mock_gen_model, mock_vertex_judge, mock_sync):
    """Verifies that a completed task is not re-dispatched if the system restarts."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 1. First Run: Task completes
        manager = StudioManager(root_dir=temp_dir)
        ticket = Ticket(id="TKT-1", title="Task 1", description="Desc", priority="HIGH", source_section_id="1.1", status="IN_PROGRESS")
        manager.state.orchestration.sprint_backlog = [ticket]
        manager.state.engineering.current_task = "Task 1: Desc"
        manager.state.engineering.jules_meta = JulesMetadata(status="COMPLETED")

        mock_engineer_app = MagicMock()
        orchestrator = Orchestrator(engineer_app=mock_engineer_app, manager=manager)

        await orchestrator.node_backlog_dispatcher(manager.state)

        # 2. Simulate Crash/Restart: Initialize new Manager and Orchestrator
        new_manager = StudioManager(root_dir=temp_dir)
        assert len(new_manager.state.orchestration.completed_tasks_log) == 1
        assert len(new_manager.state.orchestration.sprint_backlog) == 0

        new_orchestrator = Orchestrator(engineer_app=mock_engineer_app, manager=new_manager)

        # 3. Call dispatcher again
        result = await new_orchestrator.node_backlog_dispatcher(new_manager.state)

        # 4. Assert no new task is dispatched
        assert "engineering" not in result or result["engineering"] is None
        # OR if it returns orchestration only
        if "engineering" in result:
             # If it returned a new engineering state it would have a current_task
             # node_backlog_dispatcher returns {"orchestration": orch, "engineering": new_eng} if a task is found
             # otherwise it returns {"orchestration": orch}
             pass

        # Check that no task in sprint_backlog is IN_PROGRESS
        assert all(t.status != "IN_PROGRESS" for t in new_manager.state.orchestration.sprint_backlog)
