import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from studio.subgraphs.engineer import node_watch_tower
from studio.memory import JulesMetadata
from studio.utils.jules_client import WorkStatus
from studio.config import Settings

@pytest.mark.asyncio
async def test_node_watch_tower_sleeps():
    """
    Verifies that node_watch_tower respects the jules_poll_interval setting.
    """
    # 1. Setup Mock State
    jules_meta = JulesMetadata(
        external_task_id="123",
        status="WORKING"
    )
    state = {
        "jules_metadata": jules_meta,
        "messages": [],
        "system_constitution": "test",
        "next_agent": None
    }

    # 2. Mock Settings
    mock_settings = MagicMock(spec=Settings)
    mock_settings.jules_poll_interval = 0.05
    mock_settings.github_token = MagicMock()
    mock_settings.github_repository = "test/repo"
    mock_settings.jules_username = "jules"

    # 3. Mock dependencies
    with patch("studio.subgraphs.engineer.get_settings", return_value=mock_settings), \
         patch("studio.subgraphs.engineer.JulesGitHubClient") as MockClient, \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:

        # Mock Client behavior
        mock_client_instance = MockClient.return_value
        mock_client_instance.get_status.return_value = WorkStatus(
            tracking_id="123",
            status="WORKING"
        )

        # 4. Run the node
        result = await node_watch_tower(state)

        # 5. Assertions
        mock_sleep.assert_called_once_with(0.05)
        assert result["jules_metadata"].status == "WORKING"
        mock_client_instance.get_status.assert_called_once_with("123")

@pytest.mark.asyncio
async def test_node_watch_tower_completion():
    """
    Verifies that node_watch_tower transitions to VERIFYING on completion.
    """
    jules_meta = JulesMetadata(
        external_task_id="123",
        status="WORKING"
    )
    state = {
        "jules_metadata": jules_meta,
        "messages": []
    }

    mock_settings = MagicMock(spec=Settings)
    mock_settings.jules_poll_interval = 0.01
    mock_settings.github_token = MagicMock()
    mock_settings.github_repository = "test/repo"
    mock_settings.jules_username = "jules"

    with patch("studio.subgraphs.engineer.get_settings", return_value=mock_settings), \
         patch("studio.subgraphs.engineer.JulesGitHubClient") as MockClient, \
         patch("asyncio.sleep", new_callable=AsyncMock):

        mock_client_instance = MockClient.return_value
        mock_client_instance.get_status.return_value = WorkStatus(
            tracking_id="123",
            status="COMPLETED",
            raw_diff="test-diff",
            pr_url="http://test-pr"
        )

        result = await node_watch_tower(state)

        assert result["jules_metadata"].status == "VERIFYING"
        assert len(result["jules_metadata"].generated_artifacts) == 1
        assert result["jules_metadata"].generated_artifacts[0].diff_content == "test-diff"
