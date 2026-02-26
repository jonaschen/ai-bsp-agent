import pytest
from unittest.mock import MagicMock, patch
from product.schemas import ConsultantResponse
from product.bsp_agent.agents.supervisor import SupervisorAgent
from product.bsp_agent.core.state import AgentState

def test_consultant_response_schema():
    """Test A (Schema Compliance): The output MUST validate against the JSON Schema."""
    valid_data = {
        "diagnosis_id": "RCA-BSP-001",
        "confidence": 0.9,
        "status": "CRITICAL",
        "root_cause_summary": "Null Pointer Dereference",
        "evidence": ["Timestamp 1456.78: null pointer dereference"],
        "sop_steps": [
            {
                "step_id": 1,
                "action_type": "CODE_PATCH",
                "instruction": "Add check for clk_ptr before access.",
                "expected_value": "N/A",
                "file_path": "drivers/gpu/drm/msm/mdss.c"
            }
        ]
    }
    response = ConsultantResponse(**valid_data)
    assert response.diagnosis_id == "RCA-BSP-001"
    assert len(response.sop_steps) == 1

@patch("product.bsp_agent.agents.supervisor.ChatVertexAI")
def test_supervisor_validation(mock_chat):
    """Test B (Input Validation - Fix #2): Non-log text should fail validation."""
    agent = SupervisorAgent()
    assert agent.validate_input("Hello, how are you?") is False

@patch("product.bsp_agent.agents.supervisor.ChatVertexAI")
def test_supervisor_chunking(mock_chat):
    """Test C (Chunking Protocol - Fix #3): Large logs should be chunked."""
    # Use a small threshold for testing to avoid memory issues
    agent = SupervisorAgent(chunk_threshold_mb=0)
    # Generate dummy log
    large_log = "log line\n" * 6000
    chunked = agent.chunk_log(large_log)

    # Assertion: Verify the agent extracts only the last 5000 lines
    # (Simplified for mock: check that the result is smaller than original)
    assert len(chunked.splitlines()) <= 5000

@patch("product.bsp_agent.agents.supervisor.ChatVertexAI")
def test_supervisor_chunking_window(mock_chat):
    """Test C (Chunking Protocol - Fix #3): ±10s window around failure."""
    agent = SupervisorAgent(chunk_threshold_mb=0)
    log_content = [
        "[   10.000000] normal log",
        "[  100.000000] more normal log",
        "[  200.000000] Kernel panic - not syncing: Fatal exception",
        "[  201.000000] after panic",
        "[  215.000000] far after panic"
    ]
    text = "\n".join(log_content)
    chunked = agent.chunk_log(text)

    # ±10s around 200 should include 190 to 210.
    # So 100 is excluded, 215 is excluded.
    assert "[  200.000000] Kernel panic" in chunked
    assert "[  201.000000] after panic" in chunked
    assert "[   10.000000] normal log" not in chunked
    assert "[  215.000000] far after panic" not in chunked

@patch("product.bsp_agent.agents.supervisor.ChatVertexAI")
def test_supervisor_routing(mock_chat):
    """Test D (Golden Set Routing): Supervisor identifies Software Panic and routes to Kernel Pathologist."""
    # Mock LLM response for routing
    mock_llm = MagicMock()
    mock_chat.return_value = mock_llm

    # Mock response to route to Kernel Pathologist
    mock_llm.invoke.return_value.content = "KERNEL_PATHOLOGIST"

    agent = SupervisorAgent()
    with open("tests/fixtures/panic_log_01.txt", "r") as f:
        log_content = f.read()

    state: AgentState = {
        "messages": [("user", log_content)],
        "current_log_chunk": log_content,
        "diagnosis_report": None
    }

    next_node = agent.route(state)
    assert next_node == "kernel_pathologist"
