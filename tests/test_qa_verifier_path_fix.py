import pytest
from unittest.mock import MagicMock, patch
from studio.subgraphs.engineer import node_qa_verifier, is_valid_local_path
from studio.memory import AgentState, JulesMetadata, ContextSlice, CodeChangeArtifact
import os

@pytest.mark.asyncio
async def test_node_qa_verifier_normalizes_absolute_paths():
    # 1. Setup State: Jules produced a patch with absolute paths (/workspace/...)
    jules_data = JulesMetadata(
        status="VERIFYING",
        active_context_slice=ContextSlice(files=[]),
        generated_artifacts=[
            CodeChangeArtifact(
                diff_content="""diff --git a/workspace/product/logic.py b/workspace/product/logic.py
--- a/workspace/product/logic.py
+++ b/workspace/product/logic.py
@@ -1,1 +1,1 @@
-old
+new
diff --git a/workspace/pytest.ini b/workspace/pytest.ini
--- a/workspace/pytest.ini
+++ b/workspace/pytest.ini
@@ -1,1 +1,1 @@
-old
+new
""",
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
         patch("os.path.exists") as mock_exists, \
         patch("builtins.open") as mock_open:

        # mock_apply should return the files that were passed to it
        def mock_apply_side_effect(files, diff):
            return files.copy()
        mock_apply.side_effect = mock_apply_side_effect

        # Simulate existence of files on disk (all relative)
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

        # Check normalization: /workspace/product/logic.py -> product/logic.py
        assert "product/logic.py" in setup_call_args
        assert "/workspace/product/logic.py" not in setup_call_args

        # Check normalization: /workspace/pytest.ini -> pytest.ini
        assert "pytest.ini" in setup_call_args
        assert "/workspace/pytest.ini" not in setup_call_args

        # 5. Verify test identification
        # pytest.ini contains "test" but it should NOT be in test_files passed to run_pytest
        # product/logic.py does NOT contain "test" or "spec", so it shouldn't be either.
        # Since no tests are found, it should fall back to "tests/" (if it existed) or the target determined.

        # In this mock, "tests" doesn't exist.
        # But wait, node_qa_verifier has:
        # has_tests = any(f.endswith(".py") and ("test" in f or "spec" in f) for f in all_target_files)
        # In our case, none of the files match this.

        # Check what was passed to run_pytest
        run_pytest_args = mock_sandbox_inst.run_pytest.call_args[0][0]
        assert "pytest.ini" not in run_pytest_args
        assert "tests/" in run_pytest_args # Default fallback when no tests identified

def test_is_valid_local_path_extensions():
    assert is_valid_local_path("pytest.ini") is True
    assert is_valid_local_path("pyproject.toml") is True
    assert is_valid_local_path("product/logic.py") is True
    assert is_valid_local_path("/workspace/pytest.ini") is False
    assert is_valid_local_path("../outside.py") is False
