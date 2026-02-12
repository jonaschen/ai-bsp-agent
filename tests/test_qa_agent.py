import pytest
from unittest.mock import MagicMock, patch
import json
import os
import sys

from studio.qa_agent import QAAgent

class TestQAAgent:
    @pytest.fixture
    def agent(self):
        return QAAgent()

    @patch("studio.qa_agent.subprocess.run")
    @patch("studio.qa_agent.os.path.isfile")
    def test_run_suite_success_file(self, mock_isfile, mock_subprocess, agent):
        # Arrange
        mock_isfile.return_value = True
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Test Passed"
        mock_result.stderr = ""
        mock_subprocess.return_value = mock_result

        test_path = "/path/to/test_file.py"

        # Act
        result_json = agent.run_suite(test_path)
        result = json.loads(result_json)

        # Assert
        mock_isfile.assert_called_with(test_path)
        mock_subprocess.assert_called_once()
        args, kwargs = mock_subprocess.call_args
        assert args[0] == [sys.executable, "-m", "pytest", "test_file.py"]
        assert kwargs["cwd"] == "/path/to"
        # Check environment variable copy
        assert kwargs["env"]["PYTHONPATH"] == "/path/to"

        assert result["status"] == "PASS"
        assert "Test Passed" in result["logs"]

    @patch("studio.qa_agent.subprocess.run")
    @patch("studio.qa_agent.os.path.isfile")
    def test_run_suite_success_directory(self, mock_isfile, mock_subprocess, agent):
        # Arrange
        mock_isfile.return_value = False
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Test Passed"
        mock_result.stderr = ""
        mock_subprocess.return_value = mock_result

        test_path = "/path/to/tests"

        # Act
        result_json = agent.run_suite(test_path)
        result = json.loads(result_json)

        # Assert
        mock_isfile.assert_called_with(test_path)
        mock_subprocess.assert_called_once()
        args, kwargs = mock_subprocess.call_args
        assert args[0] == [sys.executable, "-m", "pytest", "."]
        assert kwargs["cwd"] == "/path/to/tests"
        assert kwargs["env"]["PYTHONPATH"] == "/path/to/tests"

        assert result["status"] == "PASS"

    @patch("studio.qa_agent.subprocess.run")
    @patch("studio.qa_agent.os.path.isfile")
    def test_run_suite_failure(self, mock_isfile, mock_subprocess, agent):
        # Arrange
        mock_isfile.return_value = True
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = "Test Failed"
        mock_result.stderr = "Error details"
        mock_subprocess.return_value = mock_result

        test_path = "/path/to/test_file.py"

        # Act
        result_json = agent.run_suite(test_path)
        result = json.loads(result_json)

        # Assert
        assert result["status"] == "FAIL"
        assert "Test Failed" in result["logs"]
        assert "Error details" in result["logs"]

    @patch("studio.qa_agent.subprocess.run")
    @patch("studio.qa_agent.os.path.isfile")
    def test_run_suite_exception(self, mock_isfile, mock_subprocess, agent):
        # Arrange
        mock_isfile.return_value = True
        mock_subprocess.side_effect = Exception("Subprocess Error")

        test_path = "/path/to/test_file.py"

        # Act
        result_json = agent.run_suite(test_path)
        result = json.loads(result_json)

        # Assert
        assert result["status"] == "FAIL"
        assert "Internal Error in QAAgent: Subprocess Error" in result["logs"]
