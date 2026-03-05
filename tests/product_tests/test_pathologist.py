import pytest
import os
import json
import sys
from unittest.mock import MagicMock, patch

# Ensure the project root is in the path for CI environments
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from product.schemas import ConsultantResponse
from product.bsp_agent.agents.pathologist import KernelPathologistAgent

@patch("product.bsp_agent.agents.pathologist.ChatVertexAI")
def test_verify_file_exists_tool(mock_chat):
    """Test the tool that verifies if a file exists in the filesystem."""
    agent = KernelPathologistAgent()
    # Test with an existing file (this test file itself)
    assert agent.verify_file_exists(__file__) is True
    # Test with a non-existent file
    assert agent.verify_file_exists("non_existent_file.c") is False

@patch("product.bsp_agent.agents.pathologist.ChatVertexAI")
def test_pathologist_panic_diagnosis(mock_chat):
    """Test Case 1: NULL Pointer Dereference (Software Panic)."""
    mock_llm = MagicMock()
    mock_chat.return_value = mock_llm

    mock_llm.invoke.return_value.content = """
    {
      "diagnosis_id": "RCA-BSP-001",
      "confidence_score": 0.95,
      "status": "CRITICAL",
      "root_cause_summary": "Null Pointer Dereference in mdss_dsi driver.",
      "evidence": [
        "[ 102.553882] BUG: kernel NULL pointer dereference, address: 0000000000000008",
        "pc : mdss_dsi_probe+0x34/0x110"
      ],
      "sop_steps": [
        {
          "step_id": 1,
          "action_type": "CODE_PATCH",
          "instruction": "Add NULL check for clock pointer in mdss_dsi_probe before access.",
          "expected_value": "Kernel boots without panic.",
          "file_path": "drivers/gpu/drm/msm/mdss_dsi.c"
        }
      ]
    }
    """

    agent = KernelPathologistAgent()

    with patch.object(agent, 'verify_file_exists', return_value=True):
        # Use absolute path for fixtures to be safe in CI
        fixture_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../fixtures/panic_log_01.txt"))
        with open(fixture_path, "r") as f:
            log_content = f.read()

        response = agent.analyze(log_content)

        assert isinstance(response, ConsultantResponse)
        assert "Null Pointer" in response.root_cause_summary
        assert response.status == "CRITICAL"
        assert response.confidence_score >= 0.85

@patch("product.bsp_agent.agents.pathologist.ChatVertexAI")
def test_pathologist_file_not_found_handling(mock_chat):
    """Test that the agent handles missing files by downgrading CODE_PATCH to MEASUREMENT."""
    mock_llm = MagicMock()
    mock_chat.return_value = mock_llm

    mock_llm.invoke.return_value.content = """
    {
      "diagnosis_id": "RCA-BSP-001",
      "confidence_score": 0.95,
      "status": "CRITICAL",
      "root_cause_summary": "Null Pointer Dereference in imaginary driver.",
      "evidence": ["pc : imaginary_probe+0x34/0x110"],
      "sop_steps": [
        {
          "step_id": 1,
          "action_type": "CODE_PATCH",
          "instruction": "Add NULL check.",
          "expected_value": "N/A",
          "file_path": "drivers/imaginary/missing_file.c"
        }
      ]
    }
    """

    agent = KernelPathologistAgent()

    with patch.object(agent, 'verify_file_exists', return_value=False):
        response = agent.analyze("dummy log")

        assert response.sop_steps[0].action_type == "MEASUREMENT"
        assert "FILE NOT FOUND" in response.sop_steps[0].instruction
        assert response.sop_steps[0].file_path == "N/A"

@patch("product.bsp_agent.agents.pathologist.ChatVertexAI")
def test_pathologist_hang_diagnosis(mock_chat):
    """Test Case 2: Watchdog Timeout (Hardware Hang)."""
    mock_llm = MagicMock()
    mock_chat.return_value = mock_llm

    mock_llm.invoke.return_value.content = """
    {
      "diagnosis_id": "RCA-BSP-002",
      "confidence_score": 0.85,
      "status": "CRITICAL",
      "root_cause_summary": "Watchdog Timeout / Hard Lockup during suspend.",
      "evidence": [
        "watchdog: Watchdog detected hard lockup on CPU 0",
        "Kernel panic - not syncing: watchdog: Watchdog detected hard lockup on CPU 0"
      ],
      "sop_steps": [
        {
          "step_id": 1,
          "action_type": "MEASUREMENT",
          "instruction": "Connect JTAG and check Program Counter (PC) to identify the hang location.",
          "expected_value": "PC points to a specific loop or blocked function.",
          "file_path": "N/A"
        }
      ]
    }
    """

    agent = KernelPathologistAgent()

    fixture_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../fixtures/suspend_hang_02.txt"))
    with open(fixture_path, "r") as f:
        log_content = f.read()

    response = agent.analyze(log_content)

    assert isinstance(response, ConsultantResponse)
    assert "Watchdog" in response.root_cause_summary
    assert response.status == "CRITICAL"

@patch("product.bsp_agent.agents.pathologist.ChatVertexAI")
def test_pathologist_healthy_boot(mock_chat):
    """Test Case 3: Healthy Boot (False Alarm)."""
    mock_llm = MagicMock()
    mock_chat.return_value = mock_llm

    mock_llm.invoke.return_value.content = """
    {
      "diagnosis_id": "RCA-BSP-003",
      "confidence_score": 0.95,
      "status": "INFO",
      "root_cause_summary": "No Anomaly Detected.",
      "evidence": [],
      "sop_steps": []
    }
    """

    agent = KernelPathologistAgent()

    fixture_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../fixtures/healthy_boot_03.txt"))
    with open(fixture_path, "r") as f:
        log_content = f.read()

    response = agent.analyze(log_content)

    assert isinstance(response, ConsultantResponse)
    assert "No Anomaly" in response.root_cause_summary
    assert response.status == "INFO"
    assert response.confidence_score >= 0.90
