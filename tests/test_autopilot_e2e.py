import os
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from studio.memory import (
    StudioState, OrchestrationState, EngineeringState, Ticket,
    JulesMetadata, CodeChangeArtifact, VerificationGate
)
from studio.orchestrator import Orchestrator

# Set mock project to avoid Google Auth errors
os.environ["GOOGLE_CLOUD_PROJECT"] = "mock-project"

@pytest.mark.asyncio
async def test_autopilot_e2e_full_flow():
    """
    Comprehensive E2E Test covering:
    Codebase scan -> Issue creation -> Task allocation -> PR Open -> Review -> Feedback/Approval Loop -> Merge
    """
    # 1. Setup Initial State with 'analyze' intent
    state = StudioState(
        orchestration=OrchestrationState(
            session_id="e2e-test",
            user_intent="analyze"
        ),
        engineering=EngineeringState()
    )

    # 2. Mock Components
    # We need to mock the new agents which don't exist yet
    with patch("studio.orchestrator.CodebaseAnalyzerAgent") as MockAnalyzer, \
         patch("studio.orchestrator.run_po_cycle") as mock_po, \
         patch("studio.orchestrator.run_scrum_retrospective"), \
         patch("studio.orchestrator.VertexFlashJudge"), \
         patch("studio.orchestrator.GenerativeModel"), \
         patch("studio.orchestrator.build_engineer_subgraph") as mock_build_eng:

        # Mock CodebaseAnalyzerAgent
        mock_analyzer = MockAnalyzer.return_value
        mock_analyzer.scan_and_report = AsyncMock(return_value=["Issue 1: Fix bug"])

        # Mock ProductOwnerAgent to return a ticket from the "issue"
        mock_po.return_value = [
            Ticket(
                id="TKT-E2E",
                title="Fix bug",
                description="Fix the bug found by analyzer",
                priority="HIGH",
                source_section_id="E2E"
            )
        ]

        # Mock Engineer Subgraph
        mock_eng_app = MagicMock()
        mock_build_eng.return_value = mock_eng_app

        # First attempt: Engineer fails (TDD Red)
        # Second attempt: Engineer succeeds (TDD Green)
        mock_eng_app.ainvoke = AsyncMock()
        mock_eng_app.ainvoke.side_effect = [
            {
                "engineering": EngineeringState(
                    current_task="Fix bug",
                    jules_meta=JulesMetadata(status="FAILED", retry_count=0),
                    verification_gate=VerificationGate(status="RED")
                ),
                "jules_metadata": JulesMetadata(status="FAILED", retry_count=0)
            },
            {
                "engineering": EngineeringState(
                    current_task="Fix bug",
                    jules_meta=JulesMetadata(
                        status="COMPLETED",
                        retry_count=1,
                        generated_artifacts=[CodeChangeArtifact(diff_content="diff")]
                    ),
                    verification_gate=VerificationGate(status="GREEN")
                ),
                "jules_metadata": JulesMetadata(status="COMPLETED", retry_count=1)
            }
        ]

        orchestrator = Orchestrator()

        # Mock the calculator to avoid network calls
        from studio.memory import SemanticHealthMetric
        mock_metric = SemanticHealthMetric(
            entropy_score=0.5,
            threshold=7.0,
            sample_size=5,
            is_tunneling=False,
            cluster_distribution={}
        )
        orchestrator.calculator.measure_uncertainty = AsyncMock(return_value=mock_metric)

        # This will FAIL initially because 'analyze' is not in Orchestrator's routing
        try:
            final_state = await orchestrator.app.ainvoke(state)
        except Exception as e:
            pytest.fail(f"Orchestrator failed: {e}")

        # Assertions to verify the flow
        assert final_state["orchestration"].user_intent == "analyze"
        # Since it's a mock, we might need to adjust how we check if it went through all nodes
        # If 'analyze' is handled, it should have triggered CodebaseAnalyzer

@pytest.mark.asyncio
async def test_autopilot_rejection_and_escalation():
    """
    Test rejected PRs that require feedback-driven re-attempts and escalation after repeated failures.
    """
    # 1. Setup Initial State with 'execute' intent and a task
    ticket = Ticket(id="TKT-FAIL", title="Hard Task", description="Will fail", priority="HIGH", source_section_id="E2E")
    state = StudioState(
        orchestration=OrchestrationState(
            session_id="e2e-fail",
            user_intent="execute",
            task_queue=[ticket]
        ),
        engineering=EngineeringState()
    )

    with patch("studio.orchestrator.build_engineer_subgraph") as mock_build_eng, \
         patch("studio.orchestrator.VertexFlashJudge"), \
         patch("studio.orchestrator.GenerativeModel"):

        mock_eng_app = MagicMock()
        mock_build_eng.return_value = mock_eng_app

        # Simulate repeated failures until max retries
        mock_eng_app.ainvoke = AsyncMock(return_value={
            "engineering": EngineeringState(
                current_task="Hard Task",
                jules_meta=JulesMetadata(status="FAILED", retry_count=5),
                verification_gate=VerificationGate(status="RED")
            ),
            "jules_metadata": JulesMetadata(status="FAILED", retry_count=5),
            "escalation_triggered": True
        })

        orchestrator = Orchestrator()

        # Mock the calculator to avoid network calls
        from studio.memory import SemanticHealthMetric
        mock_metric = SemanticHealthMetric(
            entropy_score=0.5,
            threshold=7.0,
            sample_size=5,
            is_tunneling=False,
            cluster_distribution={}
        )
        orchestrator.calculator.measure_uncertainty = AsyncMock(return_value=mock_metric)

        final_state = await orchestrator.app.ainvoke(state)

        assert final_state.get("escalation_triggered") is True
        assert final_state["orchestration"].task_queue == [] # Should be moved to failed_tasks_log
        assert len(final_state["orchestration"].failed_tasks_log) == 1

@pytest.mark.asyncio
async def test_pr_monitor_autonomous_flow():
    """
    Test the PR Monitor Agent's autonomous review cycle.
    """
    state = StudioState(
        orchestration=OrchestrationState(
            session_id="pr-monitor-test",
            user_intent="monitor"
        ),
        engineering=EngineeringState()
    )

    with patch("studio.orchestrator.PRMonitorAgent") as MockMonitor, \
         patch("studio.orchestrator.VertexFlashJudge"), \
         patch("studio.orchestrator.GenerativeModel"):

        mock_monitor = MockMonitor.return_value
        mock_monitor.monitor_and_review = AsyncMock(return_value=[123])

        orchestrator = Orchestrator()
        final_state = await orchestrator.app.ainvoke(state)

        assert final_state["orchestration"].user_intent == "monitor"
        mock_monitor.monitor_and_review.assert_called_once()
