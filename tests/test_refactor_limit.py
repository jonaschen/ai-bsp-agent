import os
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch, call
from studio.memory import (
    StudioState, OrchestrationState, EngineeringState, TriageStatus,
    SemanticHealthMetric, JulesMetadata, CodeChangeArtifact, ContextSlice,
    TestResult, ReviewVerdict, Violation, Ticket, AgentState
)
from studio.subgraphs.engineer import node_architect_gate, node_qa_verifier

@pytest.mark.asyncio
async def test_refactor_retry_limit_reached():
    """
    Tests that the Architect Gate enforces the ONE (1) refactor retry limit.
    """
    # 1. Setup state where refactor_count is already 1
    jules_meta = JulesMetadata(
        session_id="limit-session",
        refactor_count=1,
        is_refactoring=True,
        green_patch="Green Patch Content",
        status="COMPLETED", # Passed QA
        last_verified_pr_number=123,
        generated_artifacts=[CodeChangeArtifact(diff_content="Refactored Patch Content")]
    )

    state: AgentState = {
        "jules_metadata": jules_meta,
        "messages": [],
        "system_constitution": "SOLID",
        "next_agent": None
    }

    # 2. Mock Architect to reject again
    mock_verdict = ReviewVerdict(
        status="REJECTED",
        quality_score=4.0,
        violations=[Violation(
            rule_id="SOLID-SRP",
            severity="MAJOR",
            description="Still too complex",
            file_path="src/app.py",
            suggested_fix="Try harder"
        )]
    )

    with patch("studio.subgraphs.engineer.ArchitectAgent") as mock_architect_class, \
         patch("studio.subgraphs.engineer.JulesGitHubClient") as mock_client_class, \
         patch("studio.subgraphs.engineer.apply_virtual_patch") as mock_apply, \
         patch("studio.subgraphs.engineer.get_settings"):

        mock_architect = mock_architect_class.return_value
        mock_architect.review_code.return_value = mock_verdict

        mock_client = mock_client_class.return_value

        # Mock patching to return some dummy files
        mock_apply.return_value = {"src/app.py": "some content"}

        # 3. Execute node_architect_gate
        result = await node_architect_gate(state)

        # 4. Assertions
        meta = result["jules_metadata"]
        assert meta.status == "COMPLETED" # Should be COMPLETED (fallback)
        assert meta.is_refactoring is False

        # Verify client calls
        mock_client.fallback_to_green.assert_called_once_with(123, "Green Patch Content")
        mock_client.merge_pr.assert_called_once_with(123)

        # Verify message
        assert "Refactor limit reached" in result["messages"][0].content

@pytest.mark.asyncio
async def test_refactor_breaks_qa_fallback():
    """
    Tests that if a refactor breaks QA, it falls back to the Green state.
    """
    # 1. Setup state during refactor
    jules_meta = JulesMetadata(
        session_id="qa-fallback-session",
        refactor_count=1,
        is_refactoring=True,
        green_patch="Green Patch Content",
        status="VERIFYING",
        last_verified_pr_number=124,
        generated_artifacts=[CodeChangeArtifact(diff_content="Broken Refactor Patch")]
    )

    state: AgentState = {
        "jules_metadata": jules_meta,
        "messages": []
    }

    with patch("studio.subgraphs.engineer.DockerSandbox") as mock_sandbox_class, \
         patch("studio.subgraphs.engineer.JulesGitHubClient") as mock_client_class, \
         patch("studio.subgraphs.engineer.apply_virtual_patch") as mock_apply, \
         patch("studio.subgraphs.engineer.get_settings"), \
         patch("studio.subgraphs.engineer.os.path.exists", return_value=True), \
         patch("studio.subgraphs.engineer.open", MagicMock()):

        # Mock Sandbox to FAIL
        mock_sandbox = mock_sandbox_class.return_value
        mock_sandbox.setup_workspace.return_value = True
        mock_sandbox.run_pytest.return_value = MagicMock(passed=False, error_log="Tests Failed!")

        mock_client = mock_client_class.return_value

        # 3. Execute node_qa_verifier
        result = await node_qa_verifier(state)

        # 4. Assertions
        meta = result["jules_metadata"]
        assert meta.status == "COMPLETED" # Accepted fallback
        assert meta.is_refactoring is False

        # Verify client calls
        mock_client.fallback_to_green.assert_called_once_with(124, "Green Patch Content")
        mock_client.merge_pr.assert_called_once_with(124)
