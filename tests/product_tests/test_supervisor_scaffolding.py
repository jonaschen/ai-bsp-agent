import pytest
from unittest.mock import MagicMock, patch
from product.bsp_agent.agents.supervisor import SupervisorAgent
from product.bsp_agent.core.state import AgentState

@pytest.fixture(autouse=True)
def mock_vertex_ai():
    with patch("product.bsp_agent.agents.supervisor.ChatVertexAI") as mock:
        mock_instance = MagicMock()
        mock.return_value = mock_instance
        yield mock_instance

@pytest.fixture(autouse=True)
def mock_secure_sandbox():
    with patch("studio.utils.sandbox.SecureSandbox") as mock:
        mock_instance = MagicMock()
        mock.return_value = mock_instance
        # Default behavior: simulate finding a panic
        mock_instance.run_command.return_value.exit_code = 0
        yield mock_instance

@pytest.mark.asyncio
async def test_supervisor_run_exists():
    """Test that SupervisorAgent has a run method."""
    agent = SupervisorAgent()
    assert hasattr(agent, "run")

@pytest.mark.asyncio
async def test_supervisor_main_loop_chat(mock_vertex_ai):
    """Test the main loop handling user chat."""
    agent = SupervisorAgent()
    state: AgentState = {
        "messages": [("user", "Help me debug a kernel panic")],
        "current_log_chunk": None,
        "diagnosis_report": None
    }

    mock_vertex_ai.invoke.return_value.content = "I can help with that. Please provide the log."

    # We expect run to return the updated state
    result = await agent.run(state)

    assert len(result["messages"]) == 2
    assert result["messages"][-1][0] == "assistant"
    assert "Please provide the log" in result["messages"][-1][1]

@pytest.mark.asyncio
async def test_supervisor_main_loop_triage(mock_vertex_ai, mock_secure_sandbox):
    """Test the main loop handling log triage."""
    agent = SupervisorAgent()
    log_content = "[    1.234567] Kernel panic - not syncing: Fatal exception"
    state: AgentState = {
        "messages": [("user", "Analyze this:"), ("user", log_content)],
        "current_log_chunk": None,
        "diagnosis_report": None
    }

    # Secure triage will return kernel_pathologist (due to exit_code 0)
    result = await agent.run(state)

    assert result["current_log_chunk"] == log_content
    assert "routed this case to the Kernel Pathologist specialist" in result["messages"][-1][1]

@pytest.mark.asyncio
async def test_supervisor_secure_triage_routing(mock_secure_sandbox):
    """Test the secure_triage method directly."""
    agent = SupervisorAgent()

    # Mock finding a watchdog
    def side_effect(cmd):
        if "panic" in cmd:
            return MagicMock(exit_code=1)
        if "watchdog" in cmd:
            return MagicMock(exit_code=0)
        return MagicMock(exit_code=1)

    mock_secure_sandbox.run_command.side_effect = side_effect

    specialist = agent.secure_triage("watchdog timeout")
    assert specialist == "hardware_advisor"
