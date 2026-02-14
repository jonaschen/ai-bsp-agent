import os
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from studio.memory import (
    StudioState, OrchestrationState, EngineeringState, TriageStatus,
    SemanticHealthMetric, JulesMetadata, CodeChangeArtifact, ContextSlice
)
from studio.orchestrator import Orchestrator
from studio.utils.jules_client import WorkStatus

# Set mock project to avoid Google Auth errors
os.environ["GOOGLE_CLOUD_PROJECT"] = "mock-project"

@pytest.mark.asyncio
async def test_cognitive_tunneling_interception():
    """
    認知隧道測試 (Cognitive Tunneling Test)
    測試目標： 驗證 Entropy_Guard 節點是否真的能攔截幻覺。
    情境： 模擬 AI 陷入迴圈或胡言亂語。
    Mock 設定：
    將 MockSensor 的回傳值設定為 高語意熵 (例如 entropy_score = 8.5)。
    is_tunneling = True。
    預期結果：
    流程 不應該 進入 QA_Verifier (節省資源)。
    流程應該直接跳轉到 Feedback_Loop。
    狀態 circuit_breaker_triggered 應為 True。
    Jules 的 Metadata 中應記錄到一次 FAILED。
    """

    # 1. Setup Initial State
    # We set max_retries to 0 to ensure it stops immediately after the first failure
    # and doesn't loop back to Task_Dispatcher in this test scenario.
    jules_meta = JulesMetadata(
        session_id="test-session",
        max_retries=0,
        status="QUEUED"
    )

    orch_state = OrchestrationState(
        session_id="test-session",
        user_intent="CODING",
        triage_status=TriageStatus(is_log_available=True, suspected_domain="drivers"),
        current_context_slice=ContextSlice(intent="CODING", files=["src/auth.py"])
    )

    eng_state = EngineeringState(
        current_task="Fix the bug",
        jules_meta=jules_meta
    )

    state = StudioState(
        orchestration=orch_state,
        engineering=eng_state
    )

    # 2. Mocking

    # Mock Jules Client to return a completed task immediately
    with patch("studio.subgraphs.engineer.JulesGitHubClient") as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.dispatch_task.return_value = "task-123"

        # Mock status as COMPLETED so it reaches Entropy_Guard
        mock_client.get_status.return_value = WorkStatus(
            tracking_id="task-123",
            status="COMPLETED",
            raw_diff="Some hallucinated diff",
            pr_url="http://github.com/pr/1"
        )

        # Mock Entropy Calculator to return HIGH ENTROPY
        high_entropy_metric = SemanticHealthMetric(
            entropy_score=8.5,
            threshold=7.0,
            sample_size=5,
            is_tunneling=True,
            cluster_distribution={"Cluster_0": 0.2, "Cluster_1": 0.2, "Cluster_2": 0.2, "Cluster_3": 0.2, "Cluster_4": 0.2}
        )

        # Patch the calculator in both engineer subgraph and orchestrator
        # Also patch GenerativeModel and VertexFlashJudge in both modules to avoid Google Auth errors
        with patch("studio.subgraphs.engineer.SemanticEntropyCalculator.measure_uncertainty", new_callable=AsyncMock) as mock_measure_sub, \
             patch("studio.orchestrator.SemanticEntropyCalculator.measure_uncertainty", new_callable=AsyncMock) as mock_measure_orch, \
             patch("studio.subgraphs.engineer.VertexFlashJudge"), \
             patch("studio.orchestrator.VertexFlashJudge"), \
             patch("studio.subgraphs.engineer.GenerativeModel"), \
             patch("studio.orchestrator.GenerativeModel"), \
             patch("studio.subgraphs.engineer.DockerSandbox") as mock_sandbox:

            mock_measure_sub.return_value = high_entropy_metric
            mock_measure_orch.return_value = high_entropy_metric

            # 3. Initialize Orchestrator and Run
            orchestrator = Orchestrator()
            final_state = await orchestrator.app.ainvoke(state)

            # 4. Assertions
            if isinstance(final_state, dict):
                cb_triggered = final_state.get("circuit_breaker_triggered")
                engineering = final_state.get("engineering")
                # Handle both dict and object for engineering if it's mixed
                if isinstance(engineering, dict):
                    jules_meta = engineering.get("jules_meta")
                else:
                    jules_meta = engineering.jules_meta
            else:
                cb_triggered = final_state.circuit_breaker_triggered
                jules_meta = final_state.engineering.jules_meta

            # A. 狀態 circuit_breaker_triggered 應為 True
            assert cb_triggered is True

            # B. Jules 的 Metadata 中應記錄到一次 FAILED
            # Note: Final status will be FAILED because retries are exhausted (max_retries=0)
            # If jules_meta is a dict, access accordingly
            if isinstance(jules_meta, dict):
                status = jules_meta.get("status")
                entropy_history = jules_meta.get("entropy_history")
                feedback_log = jules_meta.get("feedback_log")
            else:
                status = jules_meta.status
                entropy_history = jules_meta.entropy_history
                feedback_log = jules_meta.feedback_log

            assert status == "FAILED"

            # C. 驗證 Entropy_Guard 紀錄了高語意熵
            assert len(entropy_history) == 1
            # If history items are dicts
            first_record = entropy_history[0]
            if isinstance(first_record, dict):
                assert first_record.get("score") == 8.5
                assert first_record.get("triggered_breaker") is True
            else:
                assert first_record.score == 8.5
                assert first_record.triggered_breaker is True

            # D. 流程 不應該 進入 QA_Verifier (DockerSandbox should not be called)
            assert not mock_sandbox.called

            # E. 流程應該跳轉到 Feedback_Loop
            # Check if feedback about cognitive tunneling was added to the log
            assert any("Cognitive Tunnel" in log for log in feedback_log)
