import pytest
from unittest.mock import MagicMock, patch
from src.auth.login import process_login_logs

def test_process_login_logs():
    # We mock SecureSandbox to avoid dependency on a running Docker daemon during unit tests
    with patch("src.auth.login.SecureSandbox") as MockSandbox:
        mock_instance = MockSandbox.return_value
        mock_instance.run_command.return_value = MagicMock(
            exit_code=0,
            stdout="Analysis Complete: 2 failures detected."
        )

        logs = "FAILED LOGIN\nSUCCESS\nFAILED LOGIN"
        result = process_login_logs(logs)

        assert "2 failures detected" in result
        mock_instance.setup_workspace.assert_called_once()
        mock_instance.run_command.assert_called_with("python3 analyzer.py")
        mock_instance.teardown.assert_called_once()
