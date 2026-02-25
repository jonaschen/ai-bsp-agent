import pytest
import os
import base64
import json
from pathlib import Path
from studio.memory import RetrospectiveReport, ProcessOptimization
from unittest.mock import patch, MagicMock
from studio.utils.acl import verify_write_permission

def test_acl_logic():
    """Test the ACL logic directly."""
    # Should allow
    verify_write_permission("product/prompts/test.json")
    verify_write_permission("product/prompts/sub/test.yaml")

    # Should block
    with pytest.raises(PermissionError):
        verify_write_permission("studio/config.py")
    with pytest.raises(PermissionError):
        verify_write_permission("prompts.json")
    with pytest.raises(PermissionError):
        verify_write_permission("product/prompts/../../../studio/config.py")

@patch("studio.agents.optimizer.ChatVertexAI")
def test_optimizer_agent_acl(mock_chat):
    """Test OptimizerAgent (studio/agents/optimizer.py) enforcement."""
    from studio.agents.optimizer import OptimizerAgent

    report = RetrospectiveReport(
        sprint_id="SPRINT-1",
        success_rate=0.5,
        avg_entropy_score=2.0,
        key_bottlenecks=["Testing"],
        optimizations=[
            ProcessOptimization(
                target_role="../malicious",
                issue_detected="ACL Test",
                suggested_prompt_update="Update",
                expected_impact="High"
            )
        ]
    )

    optimizer = OptimizerAgent()
    with pytest.raises(PermissionError, match="Malicious role name detected"):
        optimizer.apply_optimizations(report)

@patch("studio.optimizer.ChatVertexAI")
def test_legacy_optimizer_redirection_and_acl(mock_chat):
    """
    Test that the legacy OptimizerAgent (studio/optimizer.py)
    now writes to product/prompts/ and uses ACL.
    """
    from studio.optimizer import OptimizerAgent as LegacyOptimizer

    optimizer = LegacyOptimizer()

    # Let's patch where it is used (inside the method) by patching the source module
    with patch("studio.utils.acl.verify_write_permission") as mock_verify:
        # Patch OptimizerSandbox to avoid Docker errors in test
        with patch("studio.optimizer.OptimizerSandbox") as mock_sandbox_class:
            optimizer.apply_prompt_update("studio/agents/engineer.py", "content")

            # Check that it tried to verify the correct path
            expected_path = str(Path("product/prompts/engineer.py"))
            actual_path = mock_verify.call_args[0][0]
            assert Path(actual_path).resolve() == Path(expected_path).resolve()

def test_prompts_utils_acl():
    """Test that update_system_prompt enforces ACL."""
    from studio.utils.prompts import update_system_prompt, PROMPTS_JSON

    assert PROMPTS_JSON == "product/prompts/prompts.json"

    # Mock verify_write_permission to fail
    with patch("studio.utils.prompts.verify_write_permission", side_effect=PermissionError("Blocked")):
        with pytest.raises(PermissionError, match="Blocked"):
            update_system_prompt("engineer", "new prompt")

@patch("studio.agents.optimizer.OptimizerSandbox")
@patch("studio.agents.optimizer.ChatVertexAI")
def test_optimizer_agent_sandboxed_write(mock_chat, mock_sandbox_class):
    """Test that OptimizerAgent uses the sandbox for writes."""
    from studio.agents.optimizer import OptimizerAgent

    mock_sandbox = MagicMock()
    mock_sandbox_class.return_value = mock_sandbox
    mock_sandbox.run_command.return_value = MagicMock(exit_code=0)

    report = RetrospectiveReport(
        sprint_id="SPRINT-1",
        success_rate=0.5,
        avg_entropy_score=2.0,
        key_bottlenecks=[],
        optimizations=[
            ProcessOptimization(
                target_role="Engineer",
                issue_detected="Speed",
                suggested_prompt_update="Fast",
                expected_impact="High"
            )
        ]
    )

    optimizer = OptimizerAgent()
    # Mock _rewrite_prompt to return a fixed string
    optimizer._rewrite_prompt = MagicMock(return_value="REWRITTEN")

    optimizer.apply_optimizations(report)

    # Verify sandbox was used
    mock_sandbox.run_command.assert_called()
    called_command = mock_sandbox.run_command.call_args[0][0]
    assert "base64" in called_command
    assert "product/prompts/prompts.json" in called_command
