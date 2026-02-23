import os
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch, call
from studio.memory import (
    StudioState, OrchestrationState, EngineeringState, TriageStatus,
    SemanticHealthMetric, JulesMetadata, CodeChangeArtifact, ContextSlice,
    TestResult, ReviewVerdict, Violation, Ticket
)
from studio.orchestrator import Orchestrator
from studio.utils.jules_client import WorkStatus, TaskPayload

# Set mock project to avoid Google Auth errors
os.environ["GOOGLE_CLOUD_PROJECT"] = "mock-project"

@pytest.mark.asyncio
async def test_refactor_loop():
    """
    "Refactor Loop" Test (重構迴圈測試)
    目的： 驗證 Architect 的否決權是否真的能驅動 Engineer 進行修正，而不是直接失敗。
    情境：
    1. Engineer 提交代碼 (QA Pass, 但違反 SOLID)。
    2. Architect 拒絕 (REJECTED) 並給出建議。
    驗證點：
    - 系統 沒有 結束。
    - retry_count 增加。
    - 下一次給 Engineer 的 Prompt 中，必須包含 Architect 的 feedback。
    3. 第二次 Engineer 提交修正後的代碼。
    4. Architect 批准 (APPROVED)。
    驗證點： 狀態變為 COMPLETED，流程結束。
    """

    # 1. Setup Initial State
    jules_meta = JulesMetadata(
        session_id="refactor-session",
        max_retries=2,
        status="QUEUED"
    )

    orch_state = OrchestrationState(
        session_id="refactor-session",
        user_intent="CODING",
        triage_status=TriageStatus(is_log_available=True, suspected_domain="app"),
        current_context_slice=ContextSlice(intent="CODING", files=["src/app.py"]),
        task_queue=[
            Ticket(id="TKT-REF", title="Feature X", description="Implement X", priority="HIGH", source_section_id="1.1")
        ]
    )

    eng_state = EngineeringState(
        jules_meta=jules_meta
    )

    state = StudioState(
        orchestration=orch_state,
        engineering=eng_state
    )

    # 2. Mocking

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

    # Mock Entropy Calculator to return LOW ENTROPY
    low_entropy_metric = SemanticHealthMetric(
        entropy_score=0.5,
        threshold=7.0,
        sample_size=5,
        is_tunneling=False,
        cluster_distribution={"Cluster_0": 1.0}
    )

    # Patching necessary components
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
         patch("studio.subgraphs.engineer.apply_virtual_patch") as mock_apply_patch, \
         patch("studio.subgraphs.engineer.JulesGitHubClient") as mock_client_class:

        mock_measure_sub.return_value = low_entropy_metric
        mock_measure_orch.return_value = low_entropy_metric

        mock_architect = mock_architect_class.return_value

        # State machine for review: first REJECT, then APPROVE
        review_responses = [rejected_verdict, approved_verdict]
        def review_side_effect(*args, **kwargs):
            if review_responses:
                return review_responses.pop(0)
            return approved_verdict
        mock_architect.review_code.side_effect = review_side_effect

        # Mock Jules Client
        mock_client = mock_client_class.return_value
        mock_client.dispatch_task.return_value = "task-refactor"

        # Mock get_status to return COMPLETED each time (to move past WatchTower)
        mock_client.get_status.return_value = WorkStatus(
            tracking_id="task-refactor",
            status="COMPLETED",
            raw_diff="Some code",
            pr_url="http://github.com/pr/refactor"
        )

        mock_apply_patch.return_value = {"src/app.py": "some code content"}

        # Setup Sandbox mock (always PASS)
        mock_sandbox_instance = mock_sandbox_class.return_value
        mock_sandbox_instance.setup_workspace.return_value = True
        mock_sandbox_instance.run_pytest.return_value = MagicMock(passed=True, error_log=None)

        # 3. Initialize Orchestrator and Run
        orchestrator = Orchestrator()
        final_state = await orchestrator.app.ainvoke(state)

        # 4. Assertions

        # Check final status
        if isinstance(final_state, dict):
            engineering = final_state.get("engineering")
            if hasattr(engineering, "jules_meta"):
                jules_meta = engineering.jules_meta
            else:
                jules_meta = engineering["jules_meta"]
        else:
            jules_meta = final_state.engineering.jules_meta

        assert jules_meta.status == "COMPLETED"
        assert jules_meta.retry_count == 1

        # Check that dispatch_task was called ONCE (True PR Feedback Loop)
        assert mock_client.dispatch_task.call_count == 1

        # Check that post_feedback was called for the retry
        assert mock_client.post_feedback.call_count == 1

        # Verify the first call's payload contains the TDD constraint
        first_call_args = mock_client.dispatch_task.call_args_list[0]
        first_payload = first_call_args[0][0]
        assert any("TDD" in c for c in first_payload.constraints)

        # Verify the post_feedback call contains the architect's feedback
        feedback_call_args = mock_client.post_feedback.call_args_list[0]
        feedback_text = feedback_call_args[0][1]
        assert "ARCHITECTURAL REVIEW FAILED" in feedback_text
        assert "Class is doing too much" in feedback_text
        assert "Split class into two" in feedback_text

        print("Refactor Loop Test Passed Successfully!")

if __name__ == "__main__":
    asyncio.run(test_refactor_loop())
