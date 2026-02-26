import pytest
from studio.utils.patching import extract_affected_files

def test_extract_affected_files_standard():
    diff = """--- requirements.txt
+++ requirements.txt
@@ -1 +1,2 @@
 pytest
+mock
"""
    files = extract_affected_files(diff)
    assert files == ["requirements.txt"]

def test_extract_affected_files_git_style():
    diff = """--- a/studio/subgraphs/engineer.py
+++ b/studio/subgraphs/engineer.py
@@ -1,3 +1,3 @@
 import os
+import re
"""
    files = extract_affected_files(diff)
    assert files == ["studio/subgraphs/engineer.py"]

def test_extract_affected_files_multiple():
    diff = """--- a/file1.py
+++ b/file1.py
@@ -1 +1 @@
-1
+2
--- a/file2.py
+++ b/file2.py
@@ -1 +1 @@
-A
+B
"""
    files = extract_affected_files(diff)
    assert sorted(files) == ["file1.py", "file2.py"]

def test_extract_affected_files_new_and_deleted():
    diff = """--- /dev/null
+++ b/new_file.py
@@ -0,0 +1 @@
+pass
--- a/deleted_file.py
+++ /dev/null
@@ -1 +0,0 @@
-pass
"""
    files = extract_affected_files(diff)
    assert sorted(files) == ["deleted_file.py", "new_file.py"]

import os
import unittest.mock
from unittest.mock import MagicMock
from studio.subgraphs.engineer import node_task_dispatcher, node_qa_verifier
from studio.memory import JulesMetadata, ContextSlice, CodeChangeArtifact
from langchain_core.messages import HumanMessage

@pytest.mark.asyncio
async def test_task_dispatcher_dynamic_logic():
    # Test case for root-level file (os.makedirs("") bug check)
    root_file = "root_test_file.txt"
    if os.path.exists(root_file): os.remove(root_file)

    try:
        jules_metadata = JulesMetadata(status="QUEUED")
        state = {
            "messages": [HumanMessage(content=f"Update {root_file}")],
            "jules_metadata": jules_metadata,
            "system_constitution": ""
        }

        with unittest.mock.patch("studio.subgraphs.engineer.JulesGitHubClient") as mock_client:
            mock_client.return_value.dispatch_task.return_value = "1"

            result = await node_task_dispatcher(state)

            assert os.path.exists(root_file)
            assert root_file in result["jules_metadata"].active_context_slice.files

    finally:
        if os.path.exists(root_file): os.remove(root_file)

@pytest.mark.asyncio
async def test_qa_verifier_dynamic_sandbox_sync():
    # Test that node_qa_verifier loads files touched by diff even if not in slice
    test_file = "sync_test.py"
    with open(test_file, "w") as f: f.write("original\n")

    try:
        jules_metadata = JulesMetadata(
            status="VERIFYING",
            active_context_slice=ContextSlice(files=[]), # Empty slice
            generated_artifacts=[
                CodeChangeArtifact(
                    diff_content=f"--- a/{test_file}\n+++ b/{test_file}\n@@ -1 +1 @@\n-original\n+patched\n",
                    change_type="MODIFY"
                )
            ]
        )
        state = {
            "messages": [HumanMessage(content="task")],
            "jules_metadata": jules_metadata,
            "system_constitution": ""
        }

        with unittest.mock.patch("studio.subgraphs.engineer.DockerSandbox") as mock_sandbox_class, \
             unittest.mock.patch("studio.subgraphs.engineer.checkout_pr_branch") as mock_checkout:
            mock_sandbox = MagicMock()
            mock_sandbox_class.return_value = mock_sandbox
            mock_sandbox.setup_workspace.return_value = True
            mock_sandbox.run_pytest.return_value = MagicMock(passed=True, error_log=None)

            # Simulate checkout happened and file updated
            with open(test_file, "w") as f: f.write("patched\n")
            await node_qa_verifier(state)

            # Verify setup_workspace was called with the patched content of test_file
            workspace_files = mock_sandbox.setup_workspace.call_args[0][0]
            assert test_file in workspace_files
            assert workspace_files[test_file] == "patched\n"

    finally:
        if os.path.exists(test_file): os.remove(test_file)
