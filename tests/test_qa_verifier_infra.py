import pytest
from unittest.mock import MagicMock, patch
from studio.subgraphs.engineer import node_qa_verifier
from studio.memory import AgentState, JulesMetadata, ContextSlice, CodeChangeArtifact
import os

@pytest.mark.asyncio
async def test_node_qa_verifier_ensures_infra_files():
    # 1. Setup State: Jules produced a patch but it doesn't touch tests, and context is empty.
    jules_data = JulesMetadata(
        status="VERIFYING",
        active_context_slice=ContextSlice(files=[]),
        generated_artifacts=[
            CodeChangeArtifact(
                diff_content="diff --git a/product/logic.py b/product/logic.py\n--- a/product/logic.py\n+++ b/product/logic.py\n@@ -1,1 +1,1 @@\n-old\n+new",
                change_type="MODIFY"
            )
        ]
    )
    state: AgentState = {
        "messages": [],
        "jules_metadata": jules_data,
        "system_constitution": "",
        "next_agent": None
    }

    # 2. Mock Dependencies
    with patch("studio.subgraphs.engineer.DockerSandbox") as MockSandbox, \
         patch("studio.subgraphs.engineer.apply_virtual_patch") as mock_apply, \
         patch("studio.subgraphs.engineer.extract_affected_files") as mock_extract, \
         patch("os.path.exists") as mock_exists, \
         patch("os.walk") as mock_walk, \
         patch("builtins.open") as mock_open:

        # Mock extract_affected_files to only return the source file
        mock_extract.return_value = ["product/logic.py"]

        # mock_apply should return the files that were passed to it, plus modifications
        def mock_apply_side_effect(files, diff):
            return {**files, "product/logic.py": "new content"}
        mock_apply.side_effect = mock_apply_side_effect

        # Simulate existence of files on disk
        def side_effect_exists(path):
            if path in ["pytest.ini", "product/logic.py", "tests"]: return True
            if path == "tests/test_logic.py": return True
            return False
        mock_exists.side_effect = side_effect_exists

        # Mock os.walk for test discovery
        mock_walk.return_value = [
            ("tests", [], ["test_logic.py"])
        ]

        # Mock open to return dummy content for any file being read
        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.return_value = "dummy content"
        mock_open.return_value = mock_file

        mock_sandbox_inst = MagicMock()
        MockSandbox.return_value = mock_sandbox_inst
        mock_sandbox_inst.setup_workspace.return_value = True
        mock_sandbox_inst.run_pytest.return_value = MagicMock(passed=True, error_log=None)

        # 3. Execute the node
        await node_qa_verifier(state)

        # 4. Verify sandbox setup
        assert mock_sandbox_inst.setup_workspace.called
        setup_call_args = mock_sandbox_inst.setup_workspace.call_args[0][0]

        # EXPECTATION: These should be included even if not explicitly in context or patch
        assert "pytest.ini" in setup_call_args, "pytest.ini was NOT included in sandbox"
        assert "tests/test_logic.py" in setup_call_args, "tests/test_logic.py was NOT included in sandbox"
