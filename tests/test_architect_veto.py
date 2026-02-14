import os
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from studio.memory import (
    StudioState, OrchestrationState, EngineeringState, TriageStatus,
    SemanticHealthMetric, JulesMetadata, CodeChangeArtifact, ContextSlice,
    TestResult, ReviewVerdict, Violation
)
from studio.orchestrator import Orchestrator
from studio.utils.jules_client import WorkStatus
from studio.utils.sandbox import TestRunResult

# Set mock project to avoid Google Auth errors
os.environ["GOOGLE_CLOUD_PROJECT"] = "mock-project"

@pytest.mark.asyncio
async def test_architect_veto():
    """
    "Architect's Veto" Test (架構否決測試)
    測試目標： 驗證新增的 Architect_Review 節點是否生效。
    情境： 功能正常 (QA Pass)，但寫得很髒 (SOLID Violation)。
    Mock 設定：
    QA_Verifier 回傳 PASS。
    Mock ArchitectAgent 回傳 ReviewVerdict(status="REJECTED", violations=[...])。
    預期結果：
    流程 不能 結束在 END (因為會被踢回 Feedback_Loop)。
    feedback_log 中必須包含 "ARCHITECTURAL REVIEW FAILED" 字樣。
    這確保了爛代碼不會因為「能動」就被合併。
    """

    # 1. Setup Initial State
    jules_meta = JulesMetadata(
        session_id="veto-session",
        max_retries=1, # Allow one retry
        status="QUEUED"
    )

    orch_state = OrchestrationState(
        session_id="veto-session",
        user_intent="CODING",
        triage_status=TriageStatus(is_log_available=True, suspected_domain="app"),
        current_context_slice=ContextSlice(intent="CODING", files=["src/app.py", "tests/test_app.py"])
    )

    eng_state = EngineeringState(
        current_task="Refactor feature X",
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
        mock_client.dispatch_task.return_value = "task-veto"
        mock_client.get_status.return_value = WorkStatus(
            tracking_id="task-veto",
            status="COMPLETED",
            raw_diff="Dirty but functional code",
            pr_url="http://github.com/pr/veto"
        )

        # Mock Entropy Calculator to return LOW ENTROPY
        low_entropy_metric = SemanticHealthMetric(
            entropy_score=0.5,
            threshold=7.0,
            sample_size=5,
            is_tunneling=False,
            cluster_distribution={"Cluster_0": 1.0}
        )

        # Mock Architect Verdicts
        rejected_verdict = ReviewVerdict(
            status="REJECTED",
            quality_score=3.0,
            violations=[Violation(
                rule_id="SOLID-SRP",
                severity="MAJOR",
                description="Class is doing too much",
                file_path="src/app.py",
                suggested_fix="Split class into two"
            )]
        )
        approved_verdict = ReviewVerdict(
            status="APPROVED",
            quality_score=9.5,
            violations=[]
        )

        # Patching necessary components
        with patch("studio.subgraphs.engineer.SemanticEntropyCalculator.measure_uncertainty", new_callable=AsyncMock) as mock_measure_sub, \
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

            # Counter for review_code calls to handle multiple files and retries
            review_call_count = [0]
            def review_side_effect(file_path, *args, **kwargs):
                current_count = review_call_count[0]
                review_call_count[0] += 1
                # First call (src/app.py) -> Reject
                if current_count == 0:
                    return rejected_verdict
                # All other calls -> Approve
                return approved_verdict

            mock_architect.review_code.side_effect = review_side_effect

            mock_apply_patch.return_value = {"src/app.py": "dirty code", "tests/test_app.py": "test"}

            # Setup Sandbox mock (always PASS)
            mock_sandbox_instance = mock_sandbox_class.return_value
            mock_sandbox_instance.setup_workspace.return_value = True

            pass_result = TestRunResult(
                test_id="tests/test_app.py",
                passed=True,
                total_tests=1,
                failed_tests=0,
                error_log=None,
                duration_ms=100
            )
            mock_sandbox_instance.run_pytest.return_value = pass_result

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

            if hasattr(jules_meta, "retry_count"):
                retry_count = jules_meta.retry_count
                feedback_log = jules_meta.feedback_log
                status = jules_meta.status
            else:
                retry_count = jules_meta["retry_count"]
                feedback_log = jules_meta["feedback_log"]
                status = jules_meta["status"]

            # A. retry_count 應該從 0 變為 1
            assert retry_count == 1

            # B. feedback_log 應該包含 "ARCHITECTURAL REVIEW FAILED"
            assert any("ARCHITECTURAL REVIEW FAILED" in log for log in feedback_log)
            assert any("Class is doing too much" in log for log in feedback_log)

            # C. 最終狀態應為 COMPLETED
            assert status == "COMPLETED"
