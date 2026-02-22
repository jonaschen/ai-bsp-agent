
import os
import pytest
from unittest.mock import MagicMock, patch
from studio.subgraphs.engineer import node_task_dispatcher, is_valid_local_path
from studio.memory import AgentState, JulesMetadata
from langchain_core.messages import HumanMessage

# ============================================================================
# UNIT TESTS: is_valid_local_path() Function (Deterministic)
# ============================================================================

class TestIsValidLocalPath:
    """TDD: Red -> Green -> Refactor cycle for path validation."""

    def test_rejects_absolute_paths(self):
        """Absolute paths (security risk) should be rejected."""
        assert is_valid_local_path("/workspace/tests/test.py") is False
        assert is_valid_local_path("/home/user/file.py") is False
        assert is_valid_local_path("/etc/passwd.txt") is False

    def test_rejects_double_slash_paths(self):
        """Malformed or protocol-based paths should be rejected."""
        assert is_valid_local_path("//docs.py") is False
        assert is_valid_local_path("foo//bar.py") is False
        assert is_valid_local_path("http://example.com/file.py") is False
        assert is_valid_local_path("https://example.com/file.py") is False

    def test_rejects_parent_directory_escape(self):
        """Paths with '..' (directory traversal) should be rejected."""
        assert is_valid_local_path("../tests/file.py") is False
        assert is_valid_local_path("tests/../../outside.py") is False

    def test_rejects_noise_patterns(self):
        """Common noise patterns (stdlib, docs) should be rejected."""
        assert is_valid_local_path("org/en/stable/api.h") is False
        assert is_valid_local_path("unittest/mock.py") is False
        assert is_valid_local_path("10/unittest/mock.py") is False
        assert is_valid_local_path("workspace/test.py") is False

    def test_rejects_unsupported_extensions(self):
        """Only whitelisted extensions should be accepted."""
        assert is_valid_local_path("config.xml") is False
        assert is_valid_local_path("image.png") is False
        assert is_valid_local_path("script.sh") is False
        assert is_valid_local_path("README") is False  # No extension

    def test_accepts_valid_local_paths(self):
        """Valid local paths with supported extensions should be accepted."""
        assert is_valid_local_path("tests/test_utils.py") is True
        assert is_valid_local_path("product/bsp_agent/core/vector_store.py") is True
        assert is_valid_local_path("studio/subgraphs/engineer.py") is True
        assert is_valid_local_path("config.yaml") is True
        assert is_valid_local_path("data.json") is True
        assert is_valid_local_path("src/main.c") is True
        assert is_valid_local_path("include/header.h") is True

    def test_accepts_nested_valid_paths(self):
        """Deep nesting should be allowed if not escaping."""
        assert is_valid_local_path("a/b/c/d/e/file.py") is True
        assert is_valid_local_path("deeply/nested/dir/structure/config.yaml") is True

    def test_edge_case_single_file(self):
        """Single file names (no directory) should be valid."""
        assert is_valid_local_path("test.py") is True
        assert is_valid_local_path("config.yaml") is True

    def test_edge_case_hyphenated_names(self):
        """Paths with hyphens should be valid."""
        assert is_valid_local_path("test-utils.py") is True
        assert is_valid_local_path("my-module/sub-dir/file.py") is True


# ============================================================================
# INTEGRATION TEST: node_task_dispatcher() with Garbage Paths
# ============================================================================

@pytest.mark.asyncio
async def test_node_task_dispatcher_garbage_paths():
    """Integration test: Verify dispatcher does NOT process garbage paths."""
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

    with patch("studio.subgraphs.engineer.get_settings") as mock_settings, \
         patch("studio.subgraphs.engineer.JulesGitHubClient") as mock_client:

        mock_settings.return_value.github_token = "fake"
        mock_settings.return_value.github_repository = "fake/repo"
        mock_settings.return_value.jules_username = "jules"

        result = await node_task_dispatcher(state)
        target_files = result["jules_metadata"].active_context_slice.files

        # Assert garbage paths are NOT included
        garbage_paths = [
            "/workspace/tests/product_tests/test_vector_store.py",
            "//docs.py",
            "org/en/stable/how-to/mark.h",
            "10/unittest/mock.py"
        ]

        for path in garbage_paths:
            assert path not in target_files, f"Garbage path {path} should not be in target_files"

        # Assert valid paths ARE included
        assert "product/bsp_agent/core/vector_store.py" in target_files
        assert "tests/new_valid_test.py" in target_files

        # Cleanup
        if os.path.exists("tests/new_valid_test.py"):
            os.remove("tests/new_valid_test.py")


# ============================================================================
# REGRESSION TESTS: Known Issue Patterns
# ============================================================================

@pytest.mark.asyncio
async def test_no_garbage_folders_created_on_disk():
    """Regression: Verify NO garbage folders are created on filesystem."""

    # Create a scenario that previously created garbage
    malicious_task = "Fix error at /workspace/bad.py and org/en/stable/docs.h"

    state = {
        "messages": [HumanMessage(content=malicious_task)],
        "jules_metadata": JulesMetadata(
            session_id="TEST",
            retry_count=0,
            feedback_log=[],
            status="QUEUED"
        )
    }

    with patch("studio.subgraphs.engineer.get_settings") as mock_settings, \
         patch("studio.subgraphs.engineer.JulesGitHubClient"):

        mock_settings.return_value.github_token = "fake"
        mock_settings.return_value.github_repository = "fake/repo"
        mock_settings.return_value.jules_username = "jules"

        # Run dispatcher
        result = await node_task_dispatcher(state)

        # Assert NO garbage directories were created
        garbage_dirs = ["workspace", "org", "en", "stable"]
        for dir_name in garbage_dirs:
            assert not os.path.exists(dir_name), \
                f"Garbage directory '{dir_name}' should NOT be created"


# ============================================================================
# FUZZING TEST: Pathological Edge Cases
# ============================================================================

class TestPathValidationEdgeCases:
    """Stress test the validation with unusual inputs."""

    def test_unicode_paths(self):
        """Unicode characters in paths (potential security risk)."""
        # Currently: no unicode filtering. Consider adding if needed.
        # assert is_valid_local_path("日本語/test.py") is False  # (Optional)
        pass

    def test_very_long_paths(self):
        """Filesystem limits: paths over 255 characters."""
        long_path = "/".join(["folder"] * 100) + "/file.py"
        # Long valid path should still be accepted by is_valid_local_path
        # (filesystem rejection is OS-level)
        result = is_valid_local_path(long_path)
        # Path validation should work; actual creation might fail on filesystem
        assert isinstance(result, bool)

    def test_special_characters_in_filename(self):
        """Filenames with spaces, special chars (when valid)."""
        assert is_valid_local_path("test file.py") is False  # Spaces generally invalid
        assert is_valid_local_path("test-file.py") is True   # Hyphens OK
        assert is_valid_local_path("test_file.py") is True   # Underscores OK

    def test_case_sensitivity(self):
        """File extensions should be case-insensitive (if needed)."""
        # Current implementation is case-sensitive
        assert is_valid_local_path("test.PY") is False  # .PY not in whitelist
        assert is_valid_local_path("test.py") is True   # .py OK
        # TODO: Consider adding lowercase handling if cross-platform support needed
