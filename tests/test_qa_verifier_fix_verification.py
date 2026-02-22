import pytest
from unittest.mock import MagicMock, patch
from studio.subgraphs.engineer import node_qa_verifier
from studio.memory import AgentState, JulesMetadata, ContextSlice, CodeChangeArtifact
import os

@pytest.mark.asyncio
async def test_node_qa_verifier_normalizes_paths_and_filters_tests():
    # 1. Setup State: Jules produced a patch with absolute paths and context has absolute paths
    jules_data = JulesMetadata(
        status="VERIFYING",
        active_context_slice=ContextSlice(files=["/workspace/product/logic.py"]),
        generated_artifacts=[
            CodeChangeArtifact(
                diff_content="--- /workspace/pytest.ini\t2024-01-01\n+++ /workspace/pytest.ini\t2024-01-01\n@@ -1,1 +1,1 @@\n-[pytest]\n+[pytest]\n+addopts = -v",
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
         patch("builtins.open") as mock_open:

        # Mock extract_affected_files to return the absolute path from the diff
        mock_extract.return_value = ["/workspace/pytest.ini"]

        # mock_apply side effect
        def mock_apply_side_effect(files, diff):
            return files.copy()
        mock_apply.side_effect = mock_apply_side_effect

        # Simulate existence of files on disk (as relative paths, which we expect after normalization)
        def side_effect_exists(path):
            if path in ["pytest.ini", "product/logic.py", "requirements.txt"]: return True
            return False
        mock_exists.side_effect = side_effect_exists

        # Mock open
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

        # EXPECTATION 1: Paths should be normalized (no /workspace/ prefix)
        assert "pytest.ini" in setup_call_args
        assert "product/logic.py" in setup_call_args
        assert "/workspace/pytest.ini" not in setup_call_args
        assert "/workspace/product/logic.py" not in setup_call_args

        # EXPECTATION 2: pytest.ini should NOT be in the pytest target
        # run_pytest is called with 'target'
        run_pytest_args = mock_sandbox_inst.run_pytest.call_args[0][0]
        assert "pytest.ini" not in run_pytest_args
        # Since no other tests were provided, it should fallback to 'tests/'
        assert run_pytest_args == "tests/"
