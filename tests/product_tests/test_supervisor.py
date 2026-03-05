import sys
import os
from unittest.mock import MagicMock

# Mock dependencies before importing SupervisorAgent
mock_pydantic = MagicMock()
sys.modules["pydantic"] = mock_pydantic
sys.modules["pydantic_settings"] = MagicMock()
sys.modules["langchain_google_vertexai"] = MagicMock()
sys.modules["product.schemas"] = MagicMock()
sys.modules["product.bsp_agent.core.state"] = MagicMock()

import pytest
from unittest.mock import patch
from product.bsp_agent.agents.supervisor import SupervisorAgent

@pytest.fixture
def supervisor():
    return SupervisorAgent(model_name="gemini-1.5-pro")

@pytest.fixture
def fixtures_dir():
    """Fixture providing the path to the fixtures directory."""
    test_dir = os.path.dirname(os.path.abspath(__file__))

    # Strategy: Search in multiple likely locations to ensure compatibility with different CI environments
    candidates = [
        os.path.abspath(os.path.join(test_dir, "../../fixtures")),    # Root fixtures/
        os.path.abspath(os.path.join(test_dir, "../fixtures")),       # tests/fixtures/
        os.path.abspath(os.path.join(os.getcwd(), "fixtures")),        # CWD/fixtures/
        os.path.abspath(os.path.join(os.getcwd(), "tests/fixtures")), # CWD/tests/fixtures/
    ]

    for candidate in candidates:
        if os.path.isdir(candidate) and os.path.exists(os.path.join(candidate, "panic_log_01.txt")):
            return candidate

    # Fallback to the standard repo structure
    return os.path.abspath(os.path.join(test_dir, "../../fixtures"))

def test_chunk_log_large_file(supervisor):
    # Create a dummy log with 1000 lines
    large_log = "\n".join([f"[{i}.000000] some log message" for i in range(1000)])
    # Add a failure pattern near the end
    large_log += "\n[999.000000] BUG: kernel NULL pointer dereference, address: 0000000000000008"

    chunked = supervisor.chunk_log(large_log)
    lines = chunked.splitlines()

    assert len(lines) < 500
    assert "BUG: kernel NULL pointer dereference" in chunked

def test_chunk_log_small_file(supervisor):
    small_log = "[1.000000] small log\n[2.000000] another line"
    chunked = supervisor.chunk_log(small_log)
    assert chunked == small_log

def test_validate_input(supervisor):
    assert supervisor.validate_input("[ 123.456] valid log") is True
    assert supervisor.validate_input("invalid log message") is False

@patch("product.bsp_agent.agents.supervisor.ChatVertexAI")
def test_route_kernel_pathologist(mock_llm_class, supervisor):
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = "kernel_pathologist"
    mock_llm_class.return_value = mock_llm

    # Re-initialize supervisor to use the mocked class
    supervisor = SupervisorAgent(model_name="gemini-1.5-pro")

    state = {
        "messages": [],
        "current_log_chunk": "[ 102.553882] BUG: kernel NULL pointer dereference",
        "diagnosis_report": None
    }

    route = supervisor.route(state)
    assert route == "kernel_pathologist"

@patch("product.bsp_agent.agents.supervisor.ChatVertexAI")
def test_route_hardware_advisor(mock_llm_class, supervisor):
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = "hardware_advisor"
    mock_llm_class.return_value = mock_llm

    supervisor = SupervisorAgent(model_name="gemini-1.5-pro")

    state = {
        "messages": [],
        "current_log_chunk": "[  302.300123] watchdog: Watchdog detected hard lockup on CPU 0",
        "diagnosis_report": None
    }

    route = supervisor.route(state)
    assert route == "hardware_advisor"

@patch("product.bsp_agent.agents.supervisor.ChatVertexAI")
def test_route_clarify_needed(mock_llm_class, supervisor):
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = "clarify_needed"
    mock_llm_class.return_value = mock_llm

    supervisor = SupervisorAgent(model_name="gemini-1.5-pro")

    state = {
        "messages": [],
        "current_log_chunk": "[ 1.000000] just some normal boot logs",
        "diagnosis_report": None
    }

    route = supervisor.route(state)
    assert route == "clarify_needed"

def test_chunk_log_with_tkt003_panic(supervisor, fixtures_dir):
    with open(os.path.join(fixtures_dir, "panic_log_01.txt"), "r") as f:
        log = f.read()

    chunked = supervisor.chunk_log(log)
    lines = chunked.splitlines()

    assert len(lines) < 500
    assert "BUG: kernel NULL pointer dereference" in chunked

def test_chunk_log_with_tkt003_suspend(supervisor, fixtures_dir):
    with open(os.path.join(fixtures_dir, "suspend_hang_02.txt"), "r") as f:
        log = f.read()

    chunked = supervisor.chunk_log(log)
    lines = chunked.splitlines()

    # Original file is only 31 lines, so it should be returned as is or similar (less than limit)
    assert len(lines) <= 500
    assert "watchdog: Watchdog detected hard lockup" in chunked

def test_route_invalid_input(supervisor):
    state = {
        "messages": [],
        "current_log_chunk": "This is not a kernel log",
        "diagnosis_report": None
    }

    route = supervisor.route(state)
    assert route == "clarify_needed"
