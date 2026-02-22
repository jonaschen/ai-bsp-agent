
import os
import pytest
import shutil
from unittest.mock import MagicMock, patch
from studio.subgraphs.engineer import node_task_dispatcher
from studio.memory import AgentState, JulesMetadata
from langchain_core.messages import HumanMessage

@pytest.mark.asyncio
async def test_node_task_dispatcher_garbage_paths():
    # Setup state with garbage paths in feedback log
    garbage_log = """
    Error in /workspace/tests/product_tests/test_vector_store.py:10
    See documentation at org/en/stable/how-to/mark.h
    Also failed at //docs.py
    Standard library: 10/unittest/mock.py
    Valid file: product/bsp_agent/core/vector_store.py
    New file to create: tests/new_valid_test.py
    """

    jules_metadata = JulesMetadata(
        session_id="SESSION-TEST",
        retry_count=1,
        feedback_log=[garbage_log],
        status="QUEUED"
    )

    state = {
        "messages": [HumanMessage(content="Fix the issues")],
        "jules_metadata": jules_metadata
    }

    # Mock settings to avoid real API calls
    with patch("studio.subgraphs.engineer.get_settings") as mock_settings, \
         patch("studio.subgraphs.engineer.JulesGitHubClient") as mock_client:

        mock_settings.return_value.github_token = "fake"
        mock_settings.return_value.github_repository = "fake/repo"
        mock_settings.return_value.jules_username = "jules"

        # We want to verify that it does NOT try to create garbage paths.
        # We'll check the filesystem after running.

        result = await node_task_dispatcher(state)

        target_files = result["jules_metadata"].active_context_slice.files

        # Garbage paths should NOT be in target_files
        garbage_paths = [
            "/workspace/tests/product_tests/test_vector_store.py",
            "//docs.py",
            "org/en/stable/how-to/mark.h",
            "10/unittest/mock.py"
        ]

        for path in garbage_paths:
            assert path not in target_files, f"Garbage path {path} should not be in target_files"
            # Verify they were not created on disk
            # For absolute paths, they shouldn't be created because of PermissionError anyway,
            # but we want to avoid the attempt.
            assert not os.path.exists(path.lstrip('/')), f"Garbage path {path} should not exist on disk"

        # Verify valid files ARE included
        assert "product/bsp_agent/core/vector_store.py" in target_files
        assert "tests/new_valid_test.py" in target_files

        # Verify new valid file WAS created as placeholder (it's safe to create placeholders for valid local paths)
        assert os.path.exists("tests/new_valid_test.py")

        # Cleanup
        if os.path.exists("tests/new_valid_test.py"):
            os.remove("tests/new_valid_test.py")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_node_task_dispatcher_garbage_paths())
