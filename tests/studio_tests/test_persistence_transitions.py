import os
import json
import pytest
import asyncio
import tempfile
import shutil
from unittest.mock import MagicMock, AsyncMock, patch
from studio.memory import (
    StudioState, OrchestrationState, EngineeringState, TriageStatus,
    SemanticHealthMetric, JulesMetadata, CodeChangeArtifact, Ticket, VerificationGate
)
from studio.orchestrator import Orchestrator
from studio.manager import StudioManager

# Set mock project to avoid Google Auth errors
os.environ["GOOGLE_CLOUD_PROJECT"] = "mock-project"

class TestPersistenceTransitions:
    @pytest.fixture
    def temp_studio_dir(self):
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def manager(self, temp_studio_dir):
        return StudioManager(root_dir=temp_studio_dir)

    @pytest.mark.asyncio
    @patch("studio.orchestrator.VertexFlashJudge")
    @patch("studio.orchestrator.GenerativeModel")
    @patch("studio.orchestrator.sync_main_branch")
    async def test_persistence_on_task_completion(self, mock_sync, mock_gen_model, mock_vertex_judge, manager):
        # Setup state with an IN_PROGRESS task
        ticket = Ticket(id="TKT-1", title="Test Task", description="Desc", priority="HIGH", source_section_id="1")
        orch_state = OrchestrationState(
            session_id="test_session",
            user_intent="CODING",
            sprint_backlog=[ticket]
        )
        eng_state = EngineeringState(
            current_task="TKT-1",
            jules_meta=JulesMetadata(status="COMPLETED")
        )
        state = StudioState(orchestration=orch_state, engineering=eng_state)
        manager.state = state
        manager._save_state()

        orchestrator = Orchestrator(manager=manager)

        # We want to test node_backlog_dispatcher specifically
        await orchestrator.node_backlog_dispatcher(state)

        # Verify disk state
        with open(manager.state_path, "r") as f:
            disk_data = json.load(f)
            disk_state = StudioState.model_validate(disk_data)

        # Task should be in completed_tasks_log and removed from sprint_backlog
        assert len(disk_state.orchestration.completed_tasks_log) == 1
        assert disk_state.orchestration.completed_tasks_log[0].id == "TKT-1"
        assert len(disk_state.orchestration.sprint_backlog) == 0

    @pytest.mark.asyncio
    @patch("studio.orchestrator.VertexFlashJudge")
    @patch("studio.orchestrator.GenerativeModel")
    async def test_persistence_on_circuit_breaker(self, mock_gen_model, mock_vertex_judge, manager):
        # Setup state
        orch_state = OrchestrationState(
            session_id="test_session",
            user_intent="CODING",
            current_context_slice=None # Will be handled by wrapper
        )
        eng_state = EngineeringState(current_task="Test Task")
        state = StudioState(orchestration=orch_state, engineering=eng_state)
        manager.state = state
        manager._save_state()

        # Mock engineer app to return something
        mock_engineer_app = MagicMock()
        mock_engineer_app.ainvoke = AsyncMock(return_value={
            "jules_metadata": JulesMetadata(status="WORKING")
        })

        orchestrator = Orchestrator(engineer_app=mock_engineer_app, manager=manager)

        # Mock calculator to trigger circuit breaker
        mock_metric = SemanticHealthMetric(
            entropy_score=8.5,
            threshold=7.0,
            sample_size=5,
            is_tunneling=True,
            cluster_distribution={}
        )
        orchestrator.calculator.measure_uncertainty = AsyncMock(return_value=mock_metric)

        await orchestrator._engineer_wrapper(state)

        # Verify disk state
        with open(manager.state_path, "r") as f:
            disk_data = json.load(f)
            disk_state = StudioState.model_validate(disk_data)

        assert disk_state.circuit_breaker_triggered is True
        assert disk_state.engineering.jules_meta.status == "WORKING"

    @pytest.mark.asyncio
    @patch("studio.orchestrator.VertexFlashJudge")
    @patch("studio.orchestrator.GenerativeModel")
    @patch("studio.orchestrator.sync_main_branch")
    async def test_recovery_from_persisted_state(self, mock_sync, mock_gen_model, mock_vertex_judge, manager, temp_studio_dir):
        # 1. Setup initial state with a completed task
        ticket = Ticket(id="TKT-FINAL", title="Final Task", description="Done", priority="LOW", source_section_id="1")
        orch_state = OrchestrationState(
            session_id="recovery_session",
            user_intent="CODING",
            sprint_backlog=[ticket]
        )
        eng_state = EngineeringState(
            current_task="TKT-FINAL",
            jules_meta=JulesMetadata(status="COMPLETED")
        )
        state = StudioState(orchestration=orch_state, engineering=eng_state)
        manager.state = state
        manager._save_state()

        orchestrator = Orchestrator(manager=manager)

        # 2. Execute dispatcher - should move TKT-FINAL to completed_tasks_log and persist
        await orchestrator.node_backlog_dispatcher(state)

        # Verify it was completed in the manager's state
        assert len(manager.state.orchestration.completed_tasks_log) == 1
        assert manager.state.orchestration.completed_tasks_log[0].id == "TKT-FINAL"

        # 3. Simulate Crash/Restart: Re-initialize manager and orchestrator from same dir
        new_manager = StudioManager(root_dir=temp_studio_dir)
        new_orchestrator = Orchestrator(manager=new_manager)

        # Verify the new manager loaded the completed state
        assert len(new_manager.state.orchestration.completed_tasks_log) == 1
        assert new_manager.state.orchestration.completed_tasks_log[0].id == "TKT-FINAL"
        assert len(new_manager.state.orchestration.sprint_backlog) == 0

        # 4. Run dispatcher again - it should not find any tasks to dispatch
        result = await new_orchestrator.node_backlog_dispatcher(new_manager.state)

        # Result should show no new engineering state (meaning no new task dispatched)
        # Because sprint_backlog is empty
        assert "engineering" not in result
        assert len(new_manager.state.orchestration.sprint_backlog) == 0
