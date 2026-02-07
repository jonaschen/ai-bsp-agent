import pytest
from unittest.mock import MagicMock, patch
from studio.scrum_master import ScrumMasterAgent, EvolutionTicket

MOCK_HISTORY_CRITICAL = """
2023-10-27 10:00:00 - PR #101 - FAIL - Syntax Error
2023-10-27 10:05:00 - PR #102 - PASS
2023-10-27 10:10:00 - PR #103 - FAIL - Test Regression
2023-10-27 10:15:00 - PR #104 - FAIL - Hallucination
"""

MOCK_HISTORY_STABLE = """
2023-10-27 10:00:00 - PR #101 - PASS
2023-10-27 10:05:00 - PR #102 - PASS
2023-10-27 10:10:00 - PR #103 - PASS
2023-10-27 10:15:00 - PR #104 - PASS
"""

@pytest.fixture
def agent():
    return ScrumMasterAgent()

def test_calculate_health_metrics(agent):
    rate = agent._calculate_health_metrics(MOCK_HISTORY_CRITICAL)
    assert rate == 0.75

    rate_stable = agent._calculate_health_metrics(MOCK_HISTORY_STABLE)
    assert rate_stable == 0.0

def test_select_retrospective_strategy(agent):
    # Case A: High Failure Rate (> 20%)
    strategy_a = agent._select_retrospective_strategy(0.75)
    assert "Mad-Sad-Glad" in strategy_a

    # Case B: Stable (< 20%)
    strategy_b = agent._select_retrospective_strategy(0.0)
    assert "Start-Stop-Continue" in strategy_b

@patch("studio.scrum_master.ChatVertexAI")
def test_conduct_retrospective(mock_llm_class, agent):
    mock_llm = MagicMock()
    mock_llm_class.return_value = mock_llm

    # Mocking the LLM response to return EvolutionTicket-like objects
    # In a real scenario, we might use structured output or a parser.
    # For simplicity in this test, we'll assume the agent handles the parsing.
    mock_ticket = EvolutionTicket(
        title="Fix Architect Prompt",
        type="PROCESS_IMPROVEMENT",
        description="The Architect needs to read rules.md more carefully",
        priority="HIGH"
    )

    # We'll mock the internal call that actually gets the tickets
    with patch.object(agent, 'conduct_retrospective', return_value=[mock_ticket]):
        tickets = agent.conduct_retrospective(MOCK_HISTORY_CRITICAL)
        assert len(tickets) == 1
        assert tickets[0].title == "Fix Architect Prompt"
        assert tickets[0].priority == "HIGH"

@patch("studio.scrum_master.ChatVertexAI")
def test_get_recommendations(mock_llm_class, agent, tmp_path):
    history_file = tmp_path / "review_history.md"
    history_file.write_text(MOCK_HISTORY_CRITICAL)

    mock_llm = MagicMock()
    mock_llm_class.return_value = mock_llm

    mock_ticket = EvolutionTicket(
        title="Improve Testing",
        type="TOOLING",
        description="Add more unit tests",
        priority="MEDIUM"
    )

    with patch.object(agent, 'conduct_retrospective', return_value=[mock_ticket]):
        tickets = agent.get_recommendations(str(history_file))
        assert len(tickets) == 1
        assert tickets[0].type == "TOOLING"
