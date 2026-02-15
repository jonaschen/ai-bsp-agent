import os
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from studio.memory import (
    StudioState, OrchestrationState, EngineeringState, TriageStatus,
    SemanticHealthMetric, JulesMetadata, CodeChangeArtifact, Ticket
)
from studio.orchestrator import Orchestrator

# Set mock project to avoid Google Auth errors
os.environ["GOOGLE_CLOUD_PROJECT"] = "mock-project"

@patch("studio.orchestrator.VertexFlashJudge")
@patch("studio.orchestrator.GenerativeModel")
@patch("studio.orchestrator.run_po_cycle")
@patch("studio.orchestrator.run_scrum_retrospective")
def test_context_slicing_large_log(mock_run_retrospective, mock_run_po, mock_gen_model, mock_vertex_judge):
    """
    測試目標： 驗證 Orchestrator 的 Context Slicing 邏輯是否生效 (特別是針對大檔案)。
    情境： 用戶上傳了一個 100MB 的 Log 檔案。
    """
    # Create a log with many lines to test the 500 line limit.
    # 10,000 lines.
    log_content = "\n".join([f"Line {i}: Log message" for i in range(10000)])

    orch_state = OrchestrationState(
        session_id="test_slicing",
        user_intent="UNKNOWN",
        full_logs=log_content,
        triage_status=TriageStatus(is_log_available=True, suspected_domain="drivers"),
        task_queue=[
            Ticket(id="TKT-SLICE", title="Test Task", description="Test", priority="LOW", source_section_id="1.1")
        ]
    )
    eng_state = EngineeringState()
    state = StudioState(orchestration=orch_state, engineering=eng_state)

    # Mock dependencies
    mock_engineer_app = MagicMock()
    mock_engineer_app.ainvoke = AsyncMock(return_value={
        "jules_metadata": JulesMetadata(
            status="COMPLETED",
            generated_artifacts=[CodeChangeArtifact(diff_content="Patch applied.")]
        )
    })

    orchestrator = Orchestrator(engineer_app=mock_engineer_app)

    # Mock calculator
    mock_metric = SemanticHealthMetric(
        entropy_score=0.5,
        threshold=7.0,
        sample_size=5,
        is_tunneling=False,
        cluster_distribution={}
    )
    orchestrator.calculator.measure_uncertainty = AsyncMock(return_value=mock_metric)

    # Run the graph
    final_state = asyncio.run(orchestrator.app.ainvoke(state))

    # Verify results
    if isinstance(final_state, dict):
        orch = final_state["orchestration"]
    else:
        orch = final_state.orchestration

    if isinstance(orch, dict):
        slice_obj = orch["current_context_slice"]
    else:
        slice_obj = orch.current_context_slice

    assert slice_obj is not None

    relevant_logs = slice_obj["relevant_logs"] if isinstance(slice_obj, dict) else slice_obj.relevant_logs

    lines = relevant_logs.splitlines()
    assert len(lines) == 500
    assert lines[-1] == "Line 9999: Log message"
    assert lines[0] == "Line 9500: Log message"
