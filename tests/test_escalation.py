import os
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from studio.memory import (
    StudioState, OrchestrationState, EngineeringState, TriageStatus,
    SemanticHealthMetric, JulesMetadata, ContextSlice, Ticket
)
from studio.orchestrator import Orchestrator
from studio.utils.jules_client import WorkStatus
from studio.utils.sandbox import TestRunResult

# Set mock project to avoid Google Auth errors
os.environ["GOOGLE_CLOUD_PROJECT"] = "mock-project"

@pytest.mark.asyncio
async def test_escalation_logic():
    """
    The "Escalation" Test (止損機制測試)
    目的： 驗證 Feedback_Loop 中的 max_retries 邏輯，防止系統陷入無限迴圈燒錢。
    情境：
    設定 max_retries = 2。
    Engineer 連續 3 次提交都無法通過 QA 或 Architect。
    驗證點：
    在第 3 次失敗後，狀態 不應 變回 QUEUED。
    狀態應變為 FAILED (Escalation)。
    Orchestrator 的 failed_tasks_log 應收到此任務。
    """

    # 1. Setup Initial State
    jules_meta = JulesMetadata(
        session_id="escalation-session",
        max_retries=2, # 設定 max_retries = 2
        status="QUEUED"
    )

    ticket = Ticket(
        id="TKT-ESCALATE",
        title="Fix impossible bug",
        description="Fix it",
        priority="HIGH",
        source_section_id="1.1"
    )

    orch_state = OrchestrationState(
        session_id="escalation-session",
        user_intent="CODING",
        triage_status=TriageStatus(is_log_available=True, suspected_domain="app"),
        current_context_slice=ContextSlice(intent="CODING", files=["src/app.py"]),
        task_queue=[ticket],
        task_max_retries=2 # 設定 task_max_retries = 2
    )

    eng_state = EngineeringState(
        jules_meta=jules_meta
    )

    state = StudioState(
        orchestration=orch_state,
        engineering=eng_state
    )

    # 2. Mocking
    with patch("studio.subgraphs.engineer.JulesGitHubClient") as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.dispatch_task.return_value = "task-escalate"
        mock_client.get_status.return_value = WorkStatus(
            tracking_id="task-escalate",
            status="COMPLETED",
            raw_diff="Failing Diff",
            pr_url="http://github.com/pr/escalate"
        )

        low_entropy_metric = SemanticHealthMetric(
            entropy_score=0.5,
            threshold=2.0,
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

            mock_apply_patch.return_value = {"src/app.py": "code"}

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
            # Engineer will run 3 times (retry_count 0, 1, 2)
            mock_sandbox_instance.run_pytest.return_value = fail_result

            # 3. Initialize Orchestrator and Run
            orchestrator = Orchestrator()
            final_state = await orchestrator.app.ainvoke(state)

            # 4. Assertions
            if isinstance(final_state, dict):
                orch = final_state.get("orchestration")
                eng = final_state.get("engineering")
                escalation_triggered = final_state.get("escalation_triggered", False)

                # Depending on how it's returned, it might be objects or dicts
                if isinstance(eng, dict):
                    jules_meta = eng.get("jules_meta")
                else:
                    jules_meta = eng.jules_meta

                if isinstance(orch, dict):
                    failed_tasks_log = orch.get("failed_tasks_log", [])
                else:
                    failed_tasks_log = orch.failed_tasks_log
            else:
                jules_meta = final_state.engineering.jules_meta
                failed_tasks_log = final_state.orchestration.failed_tasks_log
                escalation_triggered = final_state.escalation_triggered

            if isinstance(jules_meta, dict):
                retry_count = jules_meta.get("retry_count")
                status = jules_meta.get("status")
            else:
                retry_count = jules_meta.retry_count
                status = jules_meta.status

            # A. retry_count 應該達到 max_retries (2)
            assert retry_count == 2

            # B. 最終狀態應為 FAILED (不是 QUEUED)
            assert status == "FAILED"

            # C. 應該觸發 Escalation 訊號
            assert escalation_triggered is True

            # D. Orchestrator 的 failed_tasks_log 應收到此任務
            assert len(failed_tasks_log) > 0
            assert any(t.id == "TKT-ESCALATE" for t in failed_tasks_log)
