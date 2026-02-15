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
async def test_max_retry_containment():
    """
    The "Max Retry" Containment Test (止損測試)
    測試目標： 防止系統進入無限迴圈燒錢。
    情境： AI 徹底卡關，怎麼修都修不好。
    """

    # 1. Setup Initial State
    jules_meta = JulesMetadata(
        session_id="max-retry-session",
        max_retries=3,
        status="QUEUED"
    )

    orch_state = OrchestrationState(
        session_id="max-retry-session",
        user_intent="CODING",
        triage_status=TriageStatus(is_log_available=True, suspected_domain="app"),
        current_context_slice=ContextSlice(intent="CODING", files=["src/app.py", "tests/test_app.py"]),
        task_queue=[
            Ticket(id="TKT-RETRY", title="Fix impossible bug", description="Fix it", priority="HIGH", source_section_id="1.1")
        ]
    )

    eng_state = EngineeringState(
        # current_task="Fix impossible bug",
        jules_meta=jules_meta
    )

    state = StudioState(
        orchestration=orch_state,
        engineering=eng_state
    )

    # 2. Mocking

    with patch("studio.subgraphs.engineer.JulesGitHubClient") as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.dispatch_task.return_value = "task-retry"
        mock_client.get_status.return_value = WorkStatus(
            tracking_id="task-retry",
            status="COMPLETED",
            raw_diff="Failing Diff",
            pr_url="http://github.com/pr/retry"
        )

        low_entropy_metric = SemanticHealthMetric(
            entropy_score=0.5,
            threshold=7.0,
            sample_size=5,
            is_tunneling=False,
            cluster_distribution={"Cluster_0": 1.0}
        )

        with patch("studio.orchestrator.run_po_cycle"), \
             patch("studio.orchestrator.run_scrum_retrospective"), \
             patch("studio.subgraphs.engineer.SemanticEntropyCalculator.measure_uncertainty", new_callable=AsyncMock) as mock_measure_sub, \
             patch("studio.orchestrator.SemanticEntropyCalculator.measure_uncertainty", new_callable=AsyncMock) as mock_measure_orch, \
             patch("studio.subgraphs.engineer.ArchitectAgent"), \
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

            mock_apply_patch.return_value = {"src/app.py": "code", "tests/test_app.py": "test"}

            mock_sandbox_instance = mock_sandbox_class.return_value
            mock_sandbox_instance.setup_workspace.return_value = True

            # Always fail
            fail_result = TestRunResult(
                test_id="tests/test_app.py",
                passed=False,
                total_tests=1,
                failed_tests=1,
                error_log="AssertionError: Still failing",
                duration_ms=100
            )
            # We expect 4 attempts total (retry_count: 0, 1, 2, 3)
            mock_sandbox_instance.run_pytest.return_value = fail_result

            # 3. Initialize Orchestrator and Run
            orchestrator = Orchestrator()
            # We use a try-except or just run it, but it might fail on pydantic validation if we add fields
            final_state = await orchestrator.app.ainvoke(state)

            # 4. Assertions
            if isinstance(final_state, dict):
                engineering = final_state.get("engineering")
                if isinstance(engineering, dict):
                    jules_meta = engineering.get("jules_meta")
                else:
                    jules_meta = engineering.jules_meta

                # Check escalation_triggered flag
                escalation_triggered = final_state.get("escalation_triggered", False)
            else:
                jules_meta = final_state.engineering.jules_meta
                # This will fail until we add the field to StudioState
                escalation_triggered = getattr(final_state, "escalation_triggered", False)

            if isinstance(jules_meta, dict):
                retry_count = jules_meta.get("retry_count")
                status = jules_meta.get("status")
            else:
                retry_count = jules_meta.retry_count
                status = jules_meta.status

            # A. retry_count 應該達到 max_retries (3)
            assert retry_count >= 3

            # B. 最終狀態應為 FAILED
            assert status == "FAILED"

            # C. 應該觸發 Escalation 訊號
            assert escalation_triggered is True
