import pytest
import os
import unittest.mock
from unittest.mock import MagicMock
from studio.subgraphs.engineer import node_qa_verifier
from studio.memory import JulesMetadata, ContextSlice, CodeChangeArtifact, TestResult
from langchain_core.messages import HumanMessage
from studio.utils.sandbox import TestRunResult

@pytest.mark.asyncio
async def test_qa_verifier_missing_tests_dir_guard():
    # Test that node_qa_verifier handles empty test_files gracefully with a FAIL status
    # and a helpful message instead of crashing with a "file not found" error.

    jules_metadata = JulesMetadata(
        status="VERIFYING",
        active_context_slice=ContextSlice(files=["dummy.txt"]),
        generated_artifacts=[
            CodeChangeArtifact(
                diff_content="--- a/dummy.txt\n+++ b/dummy.txt\n@@ -1 +1 @@\n-old\n+new\n",
                change_type="MODIFY"
            )
        ],
        retry_count=0
    )
    state = {
        "messages": [HumanMessage(content="update dummy")],
        "jules_metadata": jules_metadata,
        "system_constitution": ""
    }

    with unittest.mock.patch("studio.subgraphs.engineer.DockerSandbox") as mock_sandbox_class, \
         unittest.mock.patch("os.path.exists", side_effect=lambda x: x == "dummy.txt" or x == "pytest.ini"), \
         unittest.mock.patch("os.path.isfile", return_value=True), \
         unittest.mock.patch("builtins.open", unittest.mock.mock_open(read_data="old\n")), \
         unittest.mock.patch("studio.subgraphs.engineer.apply_virtual_patch") as mock_patch:

        mock_sandbox = MagicMock()
        mock_sandbox_class.return_value = mock_sandbox
        mock_sandbox.setup_workspace.return_value = True

        # Mock patch success but it doesn't return anything in tests/
        mock_patch.return_value = {"dummy.txt": "new\n"}

        result = await node_qa_verifier(state)

        # Verify it DID NOT try to run pytest on "tests/"
        mock_sandbox.run_pytest.assert_not_called()

        # Verify metadata was updated correctly
        final_metadata = result["jules_metadata"]
        assert final_metadata.status == "FAILED"
        assert len(final_metadata.test_results_history) == 1
        last_result = final_metadata.test_results_history[-1]
        assert last_result.status == "FAIL"
        assert "No tests found to run" in last_result.logs

@pytest.mark.asyncio
async def test_qa_verifier_includes_pytest_ini():
    # Test that node_qa_verifier includes pytest.ini if it exists

    jules_metadata = JulesMetadata(
        status="VERIFYING",
        active_context_slice=ContextSlice(files=["README.md"]),
        generated_artifacts=[],
        retry_count=0
    )
    state = {
        "messages": [HumanMessage(content="task")],
        "jules_metadata": jules_metadata,
        "system_constitution": ""
    }

    with unittest.mock.patch("studio.subgraphs.engineer.DockerSandbox") as mock_sandbox_class, \
         unittest.mock.patch("os.path.exists", side_effect=lambda x: x == "pytest.ini" or x == "README.md"), \
         unittest.mock.patch("os.path.isfile", return_value=True), \
         unittest.mock.patch("builtins.open", unittest.mock.mock_open(read_data="[pytest]\n")), \
         unittest.mock.patch("studio.subgraphs.engineer.apply_virtual_patch") as mock_patch:

        mock_sandbox = MagicMock()
        mock_sandbox_class.return_value = mock_sandbox
        mock_sandbox.setup_workspace.return_value = True
        mock_sandbox.run_pytest.return_value = TestRunResult(
            test_id="tests/",
            passed=True,
            total_tests=1,
            failed_tests=0,
            duration_ms=10
        )

        # We need to make it think there ARE tests in sandbox so it doesn't trip the guard
        mock_patch.return_value = {"tests/test_dummy.py": "pass", "pytest.ini": "[pytest]\n"}

        await node_qa_verifier(state)

        # Verify setup_workspace was called with pytest.ini
        workspace_files = mock_sandbox.setup_workspace.call_args[0][0]
        assert "pytest.ini" in workspace_files
        assert workspace_files["pytest.ini"] == "[pytest]\n"

@pytest.mark.asyncio
async def test_qa_verifier_filters_non_py_tests():
    # Test that node_qa_verifier filters out non-.py files from test_files

    with unittest.mock.patch("os.path.exists", return_value=True), \
         unittest.mock.patch("os.path.isfile", return_value=True), \
         unittest.mock.patch("builtins.open", unittest.mock.mock_open(read_data="content")), \
         unittest.mock.patch("studio.subgraphs.engineer.apply_virtual_patch") as mock_patch:

        jules_metadata = JulesMetadata(
            status="VERIFYING",
            active_context_slice=ContextSlice(files=["tests/test_valid.py", "pytest.ini", "tests/not_a_test.txt"]),
            generated_artifacts=[],
            retry_count=0
        )
        state = {
            "messages": [HumanMessage(content="task")],
            "jules_metadata": jules_metadata,
            "system_constitution": ""
        }

        mock_sandbox = MagicMock()
        mock_sandbox.setup_workspace.return_value = True
        mock_sandbox.run_pytest.return_value = TestRunResult(
            test_id="tests/test_valid.py",
            passed=True,
            total_tests=1,
            failed_tests=0,
            duration_ms=10
        )

        with unittest.mock.patch("studio.subgraphs.engineer.DockerSandbox", return_value=mock_sandbox):
            mock_patch.return_value = {"tests/test_valid.py": "content"}

            await node_qa_verifier(state)

            # Verify run_pytest was called ONLY with the valid .py test file
            mock_sandbox.run_pytest.assert_called_with("tests/test_valid.py")
