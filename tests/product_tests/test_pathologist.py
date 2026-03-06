import os
import sys

# AGGRESSIVE CI PATH RESOLUTION
def setup_ci_path():
    # 1. Absolute root identification
    current = os.path.abspath(os.path.dirname(__file__))
    root = current
    while root != os.path.dirname(root):
        if os.path.exists(os.path.join(root, "PRODUCT_BLUEPRINT.md")):
            break
        root = os.path.dirname(root)

    # 2. Strategic sys.path insertion
    if root not in sys.path:
        sys.path.insert(0, root)

    # 3. Handle common sandbox mount points
    for p in ["/workspace", "/app"]:
        if os.path.exists(p) and p not in sys.path:
            sys.path.insert(0, p)

    # 4. Explicit package path injection to avoid ModuleNotFoundError in submodules
    # This helps when 'product.schemas' is found but 'product.schemas.datasheet' fails
    product_path = os.path.join(root, "product")
    if os.path.exists(product_path) and product_path not in sys.path:
        sys.path.insert(0, product_path)

setup_ci_path()

import pytest
import json
from unittest.mock import MagicMock, patch

from product.schemas import ConsultantResponse
from product.bsp_agent.agents.pathologist import KernelPathologistAgent

@patch("product.bsp_agent.agents.pathologist.ChatVertexAI")
def test_verify_file_exists_tool(mock_chat):
    """Test the tool that verifies if a file exists in the filesystem."""
    agent = KernelPathologistAgent()
    assert agent.verify_file_exists(__file__) is True
    assert agent.verify_file_exists("non_existent_file.c") is False

@patch("product.bsp_agent.agents.pathologist.ChatVertexAI")
def test_pathologist_panic_diagnosis(mock_chat):
    """Test Case 1: NULL Pointer Dereference."""
    mock_llm = MagicMock()
    mock_chat.return_value = mock_llm
    mock_llm.invoke.return_value.content = '{"diagnosis_id": "RCA-BSP-001", "confidence_score": 0.95, "status": "CRITICAL", "root_cause_summary": "Null Pointer", "evidence": [], "sop_steps": []}'

    agent = KernelPathologistAgent()

    # Find root for fixtures
    root = [p for p in sys.path if os.path.exists(os.path.join(p, "fixtures"))][0]
    fixture_path = os.path.join(root, "fixtures/panic_log_01.txt")

    with open(fixture_path, "r") as f:
        log_content = f.read()
    response = agent.analyze(log_content)
    assert response.diagnosis_id == "RCA-BSP-001"

@patch("product.bsp_agent.agents.pathologist.ChatVertexAI")
def test_pathologist_file_not_found_handling(mock_chat):
    """Test downgrading CODE_PATCH if file missing."""
    mock_llm = MagicMock()
    mock_chat.return_value = mock_llm
    mock_llm.invoke.return_value.content = '{"diagnosis_id": "RCA-001", "confidence_score": 0.9, "status": "CRITICAL", "root_cause_summary": "Bug", "evidence": [], "sop_steps": [{"step_id": 1, "action_type": "CODE_PATCH", "instruction": "Fix", "expected_value": "OK", "file_path": "missing.c"}]}'

    agent = KernelPathologistAgent()
    with patch.object(agent, 'verify_file_exists', return_value=False):
        response = agent.analyze("log")
        assert response.sop_steps[0].action_type == "MEASUREMENT"
        assert response.sop_steps[0].file_path == "N/A"

@patch("product.bsp_agent.agents.pathologist.ChatVertexAI")
def test_pathologist_hang_diagnosis(mock_chat):
    """Test Case 2: Watchdog."""
    mock_llm = MagicMock()
    mock_chat.return_value = mock_llm
    mock_llm.invoke.return_value.content = '{"diagnosis_id": "RCA-BSP-002", "confidence_score": 0.85, "status": "CRITICAL", "root_cause_summary": "Watchdog", "evidence": [], "sop_steps": []}'

    agent = KernelPathologistAgent()
    root = [p for p in sys.path if os.path.exists(os.path.join(p, "fixtures"))][0]
    fixture_path = os.path.join(root, "fixtures/suspend_hang_02.txt")
    with open(fixture_path, "r") as f:
        log_content = f.read()
    response = agent.analyze(log_content)
    assert "Watchdog" in response.root_cause_summary

@patch("product.bsp_agent.agents.pathologist.ChatVertexAI")
def test_pathologist_healthy_boot(mock_chat):
    """Test Case 3: Healthy."""
    mock_llm = MagicMock()
    mock_chat.return_value = mock_llm
    mock_llm.invoke.return_value.content = '{"diagnosis_id": "RCA-BSP-003", "confidence_score": 0.95, "status": "INFO", "root_cause_summary": "No Anomaly", "evidence": [], "sop_steps": []}'

    agent = KernelPathologistAgent()
    root = [p for p in sys.path if os.path.exists(os.path.join(p, "fixtures"))][0]
    fixture_path = os.path.join(root, "fixtures/healthy_boot_03.txt")
    with open(fixture_path, "r") as f:
        log_content = f.read()
    response = agent.analyze(log_content)
    assert response.status == "INFO"
