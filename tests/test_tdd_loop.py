import os
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from studio.memory import (
    StudioState, OrchestrationState, EngineeringState, TriageStatus,
    SemanticHealthMetric, JulesMetadata, CodeChangeArtifact, ContextSlice,
    TestResult, ReviewVerdict, Violation, Ticket
)
from studio.orchestrator import Orchestrator
from studio.utils.jules_client import WorkStatus
from studio.utils.sandbox import TestRunResult

# Set mock project to avoid Google Auth errors
os.environ["GOOGLE_CLOUD_PROJECT"] = "mock-project"

@pytest.mark.asyncio
async def test_red_green_refactor_loop():
    """
    "Red-Green-Refactor" Loop Test (TDD 循環測試)
    測試目標： 驗證 Engineer Subgraph 的 自我修正 (Reflex Arc) 能力。
    情境： AI 第一次寫的 Code 沒過測試，但第二次修正後過了。
    """

    # 1. Setup Initial State
    jules_meta = JulesMetadata(
        session_id="tdd-session",
        max_retries=1, # Allow one retry
        status="QUEUED"
    )

    orch_state = OrchestrationState(
        session_id="tdd-session",
        user_intent="CODING",
        triage_status=TriageStatus(is_log_available=True, suspected_domain="app"),
        current_context_slice=ContextSlice(intent="CODING", files=["src/app.py", "tests/test_app.py"]),
        sprint_backlog=[
            Ticket(id="TKT-TDD", title="Implement feature X", description="Follow TDD", priority="HIGH", source_section_id="1.1")
        ]
    )

    eng_state = EngineeringState(
        # current_task="Implement feature X",
        jules_meta=jules_meta
    )

    state = StudioState(
        orchestration=orch_state,
        engineering=eng_state
    )

    # 2. Mocking

    # Mock Jules Client
    with patch("studio.subgraphs.engineer.JulesGitHubClient") as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.dispatch_task.return_value = "task-tdd"
        mock_client.get_status.return_value = WorkStatus(
            tracking_id="task-tdd",
            status="COMPLETED",
            raw_diff="Initial Diff",
            pr_url="http://github.com/pr/tdd"
        )

        # Mock Entropy Calculator to return LOW ENTROPY
        low_entropy_metric = SemanticHealthMetric(
            entropy_score=0.5,
            threshold=7.0,
            sample_size=5,
            is_tunneling=False,
            cluster_distribution={"Cluster_0": 1.0}
        )

        # Mock Architect to return APPROVED
        mock_verdict = ReviewVerdict(
            status="APPROVED",
            quality_score=9.0,
            violations=[]
        )

        # Patching necessary components
        # We need to use AsyncMock for measure_uncertainty since it's an async method
        with patch("studio.orchestrator.run_po_cycle"), \
             patch("studio.orchestrator.run_scrum_retrospective"), \
             patch("studio.subgraphs.engineer.SemanticEntropyCalculator.measure_uncertainty", new_callable=AsyncMock) as mock_measure_sub, \
             patch("studio.orchestrator.SemanticEntropyCalculator.measure_uncertainty", new_callable=AsyncMock) as mock_measure_orch, \
             patch("studio.subgraphs.engineer.ArchitectAgent") as mock_architect_class, \
             patch("studio.subgraphs.engineer.VertexFlashJudge"), \
             patch("studio.orchestrator.VertexFlashJudge"), \
             patch("studio.subgraphs.engineer.GenerativeModel"), \
             patch("studio.orchestrator.GenerativeModel"), \
             patch("studio.subgraphs.engineer.DockerSandbox") as mock_sandbox_class, \
             patch("studio.subgraphs.engineer.os.path.exists", return_value=True), \
             patch("studio.subgraphs.engineer.open", MagicMock()), \
             patch("studio.subgraphs.engineer.apply_virtual_patch") as mock_apply_patch:

            mock_measure_sub.return_value = low_entropy_metric
            mock_measure_orch.return_value = low_entropy_metric

            mock_architect = mock_architect_class.return_value
            mock_architect.review_code.return_value = mock_verdict

            mock_apply_patch.return_value = {"src/app.py": "code", "tests/test_app.py": "test"}

            # Setup Sandbox mock with side_effect for run_pytest
            mock_sandbox_instance = mock_sandbox_class.return_value
            mock_sandbox_instance.setup_workspace.return_value = True

            # First call fails, second call passes
            fail_result = TestRunResult(
                test_id="tests/test_app.py",
                passed=False,
                total_tests=1,
                failed_tests=1,
                error_log="AssertionError: expected True but got False",
                duration_ms=100
            )
            pass_result = TestRunResult(
                test_id="tests/test_app.py",
                passed=True,
                total_tests=1,
                failed_tests=0,
                error_log=None,
                duration_ms=100
            )
            mock_sandbox_instance.run_pytest.side_effect = [fail_result, pass_result]

            # 3. Initialize Orchestrator and Run
            orchestrator = Orchestrator()
            final_state = await orchestrator.app.ainvoke(state)

            # 4. Assertions
            if isinstance(final_state, dict):
                engineering = final_state.get("engineering")
                if isinstance(engineering, dict):
                    jules_meta = engineering.get("jules_meta")
                else:
                    jules_meta = engineering.jules_meta
            else:
                jules_meta = final_state.engineering.jules_meta

            if isinstance(jules_meta, dict):
                retry_count = jules_meta.get("retry_count")
                status = jules_meta.get("status")
                feedback_log = jules_meta.get("feedback_log")
            else:
                retry_count = jules_meta.retry_count
                status = jules_meta.status
                feedback_log = jules_meta.feedback_log

            # A. retry_count 應該從 0 變為 1
            assert retry_count == 1

            # B. feedback_log 應該包含第一次的錯誤訊息
            assert any("AssertionError: expected True but got False" in log for log in feedback_log)

            # C. 最終狀態應為 COMPLETED
            assert status == "COMPLETED"
