import pytest
from unittest.mock import patch
from studio.config import get_settings
from product.bsp_agent.agents.supervisor import SupervisorAgent

def test_infra_1m_context_window_provisioned():
    """
    Verify that the 1M token context window is provisioned in settings.
    1M tokens is approximately 4MB of text.
    """
    settings = get_settings()
    # The requirement is 1M tokens.
    assert hasattr(settings, "context_window")
    assert settings.context_window >= 1000000

@patch("product.bsp_agent.agents.supervisor.ChatVertexAI")
def test_supervisor_uses_provisioned_context_window(mock_chat):
    """
    Verify that the SupervisorAgent uses the provisioned context window
    for its chunking threshold instead of a hardcoded 50MB.
    """
    settings = get_settings()
    # Mocking settings if necessary, but here we just check if it's aligned
    agent = SupervisorAgent()

    # 1M tokens should translate to roughly 4MB threshold
    # If settings.context_window is 1,000,000, threshold should be ~4MB
    # Current hardcoded is 50MB which is too large for a 1M token window
    expected_threshold = settings.context_window * 4
    assert agent.chunk_threshold <= expected_threshold
