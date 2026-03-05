import pytest
from unittest.mock import MagicMock, patch
from product.schemas import ConsultantResponse
from product.bsp_agent.agents.supervisor import SupervisorAgent
from product.bsp_agent.core.state import AgentState

def test_consultant_response_schema():
    """Test A (Schema Compliance): The output MUST validate against the JSON Schema."""
    valid_data = {
        "diagnosis_id": "RCA-BSP-001",
        "confidence_score": 0.9,
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
def test_supervisor_chunking_size(mock_chat):
    """Test C (Chunking Protocol): Concentrated segment MUST be < 500 lines."""
    agent = SupervisorAgent(chunk_threshold_mb=0)
    # Generate dummy log without timestamps but with many lines
    large_log = "log line\n" * 1000
    chunked = agent.chunk_log(large_log)
    assert len(chunked.splitlines()) < 500

@patch("product.bsp_agent.agents.supervisor.ChatVertexAI")
def test_supervisor_chunking_keywords(mock_chat):
    """Test C (Chunking Protocol): Identify keywords like 'Call trace:'."""
    agent = SupervisorAgent(chunk_threshold_mb=0)
    # Large log with a keyword in the middle
    log_content = ["noise"] * 600 + ["Call trace:"] + ["more noise"] * 100
    text = "\n".join(log_content)
    chunked = agent.chunk_log(text)

    assert "Call trace:" in chunked
    assert len(chunked.splitlines()) < 500

@pytest.mark.parametrize("log_file, expected_node", [
    ("panic_log_01.txt", "kernel_pathologist"),
    ("suspend_hang_02.txt", "hardware_advisor"),
    ("healthy_boot_03.txt", "clarify_needed"),
])
@patch("product.bsp_agent.agents.supervisor.ChatVertexAI")
def test_supervisor_golden_set_routing(mock_chat, log_file, expected_node):
    """Test D (Golden Set Routing): Supervisor correctly routes TKT-003 fixtures."""
    mock_llm = MagicMock()
    mock_chat.return_value = mock_llm

    # Mock LLM response based on expected_node
    mock_llm.invoke.return_value.content = expected_node.upper()

    agent = SupervisorAgent()
    # Using root fixtures/ directory
    with open(f"fixtures/{log_file}", "r") as f:
        log_content = f.read()

    # Pre-process log as the orchestrator would
    chunked_log = agent.chunk_log(log_content)

    state: AgentState = {
        "messages": [("user", log_content)],
        "current_log_chunk": chunked_log,
        "diagnosis_report": None
    }

    next_node = agent.route(state)
    assert next_node == expected_node
