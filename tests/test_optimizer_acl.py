"""
tests/test_optimizer_acl.py
---------------------------
Tests for Optimizer ACL Enforcement (AGENTS.md §4).

TDD Compliance:
- Follow Red-Green-Refactor cycle.
- Verify PermissionError is raised for writes outside product/prompts/.
- Verify writes to product/prompts/ are allowed.
"""

import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock


class TestOptimizerACL:
    """
    Tests for studio/optimizer.py ACL enforcement (AGENTS.md §4).
    The Optimizer must only write to product/prompts/.
    Any attempt to write outside product/prompts/ must raise PermissionError.
    """

    def setup_method(self):
        """Ensure product/prompts/ exists for valid-path tests."""
        os.makedirs("product/prompts", exist_ok=True)

    def teardown_method(self):
        """Clean up any test files written to product/prompts/."""
        for name in ["test_agent.py", "valid_prompt.py"]:
            f = Path("product/prompts") / name
            if f.exists():
                f.unlink()

    def _make_optimizer(self):
        """Helper: create an OptimizerAgent without LLM initialization."""
        from studio.optimizer import OptimizerAgent
        agent = OptimizerAgent.__new__(OptimizerAgent)
        agent.logger = MagicMock()
        return agent

    def test_apply_prompt_update_raises_for_studio_path(self):
        """
        AGENTS.md §4: Any attempt by the Optimizer to write to studio/
        must raise PermissionError.
        """
        agent = self._make_optimizer()

        with pytest.raises(PermissionError, match="Optimizer ACL Violation"):
            agent.apply_prompt_update("studio/agents/engineer.py", "malicious content")

    def test_apply_prompt_update_raises_for_arbitrary_relative_path(self):
        """
        Optimizer must not write to paths outside product/prompts/.
        """
        agent = self._make_optimizer()

        with pytest.raises(PermissionError, match="Optimizer ACL Violation"):
            agent.apply_prompt_update("some/other/path.py", "content")

    def test_apply_prompt_update_raises_for_absolute_path_outside_product(self):
        """
        Absolute paths outside product/prompts/ must be rejected.
        """
        agent = self._make_optimizer()

        with pytest.raises(PermissionError, match="Optimizer ACL Violation"):
            agent.apply_prompt_update("/tmp/some_file.py", "content")

    def test_apply_prompt_update_allowed_for_product_prompts(self):
        """
        Optimizer is allowed to write to product/prompts/.
        Verify write succeeds without raising PermissionError.
        """
        agent = self._make_optimizer()

        target = "product/prompts/valid_prompt.py"
        # Should not raise
        agent.apply_prompt_update(target, "optimized content")

        written = Path(target)
        assert written.exists()
        assert written.read_text() == "optimized content"

    def test_allowed_write_path_constant(self):
        """
        ALLOWED_WRITE_PATH must be set to product/prompts/ (AGENTS.md §4).
        """
        from studio.optimizer import ALLOWED_WRITE_PATH
        assert str(ALLOWED_WRITE_PATH).endswith("product/prompts")


class TestOptimizerAgentACL:
    """
    Tests for studio/agents/optimizer.py ACL enforcement (AGENTS.md §4).
    The OptimizerAgent.write_prompt_file() must enforce write restrictions.
    """

    def setup_method(self):
        os.makedirs("product/prompts", exist_ok=True)

    def teardown_method(self):
        test_file = Path("product/prompts/test_role_prompt.yaml")
        if test_file.exists():
            test_file.unlink()

    @pytest.fixture
    def optimizer(self, mocker=None):
        """Create OptimizerAgent with mocked LLM."""
        with pytest.MonkeyPatch().context() as mp:
            from unittest.mock import patch as upatch
            with upatch("studio.agents.optimizer.ChatVertexAI"):
                from studio.agents.optimizer import OptimizerAgent
                return OptimizerAgent()

    def test_allowed_write_paths_attribute(self):
        """
        OptimizerAgent must expose allowed_write_paths attribute (AGENTS.md §4).
        """
        with __import__("unittest.mock", fromlist=["patch"]).patch("studio.agents.optimizer.ChatVertexAI"):
            from studio.agents.optimizer import OptimizerAgent, ALLOWED_WRITE_PATH
            agent = OptimizerAgent()
            assert hasattr(agent, "allowed_write_paths")
            assert ALLOWED_WRITE_PATH in agent.allowed_write_paths

    def test_write_prompt_file_raises_for_studio_path(self):
        """
        write_prompt_file() must raise PermissionError for studio/ paths.
        """
        with __import__("unittest.mock", fromlist=["patch"]).patch("studio.agents.optimizer.ChatVertexAI"):
            from studio.agents.optimizer import OptimizerAgent
            agent = OptimizerAgent()

            with pytest.raises(PermissionError, match="Optimizer ACL Violation"):
                agent.write_prompt_file("studio/some_config.py", "content")

    def test_write_prompt_file_allowed_for_product_prompts(self):
        """
        write_prompt_file() must allow writes to product/prompts/.
        """
        with __import__("unittest.mock", fromlist=["patch"]).patch("studio.agents.optimizer.ChatVertexAI"):
            from studio.agents.optimizer import OptimizerAgent
            agent = OptimizerAgent()

            target = "product/prompts/test_role_prompt.yaml"
            agent.write_prompt_file(target, "role: engineer\nprompt: test")

            written = Path(target)
            assert written.exists()
            assert "role: engineer" in written.read_text()
