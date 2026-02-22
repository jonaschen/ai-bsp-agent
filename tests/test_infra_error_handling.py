import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from studio.memory import (
    AgentState, JulesMetadata, ContextSlice, TestResult
)
from studio.subgraphs.engineer import node_qa_verifier, node_feedback_loop
from langchain_core.messages import AIMessage

@pytest.mark.asyncio
async def test_permission_error_no_retry():
    # 1. Setup Initial State
    jules_meta = JulesMetadata(
        session_id="test-session",
        max_retries=5,
        status="VERIFYING",
        retry_count=0
    )

    state = {
        "messages": [],
        "jules_metadata": jules_meta
    }

    # 2. Mock DockerSandbox to raise PermissionError
    with patch("studio.subgraphs.engineer.DockerSandbox") as mock_sandbox:
        # PermissionError(errno, strerror)
        mock_sandbox.side_effect = PermissionError(13, "Permission denied")

        # We also need to mock other things in node_qa_verifier
        with patch("studio.subgraphs.engineer.os.path.exists", return_value=True), \
             patch("studio.subgraphs.engineer.open", MagicMock()), \
             patch("studio.subgraphs.engineer.extract_affected_files", return_value=[]), \
             patch("studio.subgraphs.engineer.apply_virtual_patch", return_value={}), \
             patch("studio.subgraphs.engineer.get_settings") as mock_settings:

            mock_settings.return_value.jules_poll_interval = 0.1

            # Run node_qa_verifier
            result_qa = await node_qa_verifier(state)
            state["jules_metadata"] = result_qa["jules_metadata"]

            # Verify status is FAILED
            assert state["jules_metadata"].status == "FAILED"
            assert state["jules_metadata"].test_results_history[-1].status == "ERROR"
            assert "Permission denied" in state["jules_metadata"].test_results_history[-1].logs

            # Now run node_feedback_loop
            # Mock JulesGitHubClient to avoid network calls
            with patch("studio.subgraphs.engineer.JulesGitHubClient") as mock_client_class:
                mock_client = mock_client_class.return_value

                result_feedback = await node_feedback_loop(state)

                # Assertions: retry_count should NOT increment, status should NOT be QUEUED
                # This is the expected behavior after the fix.
                # Currently (Before fix), it will probably be retry_count=1 and status=QUEUED
                assert result_feedback["jules_metadata"].retry_count == 0
                assert result_feedback["jules_metadata"].status == "FAILED"
