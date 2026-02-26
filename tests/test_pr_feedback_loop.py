import pytest
import asyncio
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from studio.subgraphs.engineer import node_watch_tower, node_feedback_loop, route_feedback_loop, node_architect_gate
from studio.memory import JulesMetadata, AgentState, ContextSlice
from studio.utils.jules_client import WorkStatus, JulesGitHubClient, TaskPriority
from studio.config import Settings

@pytest.mark.asyncio
async def test_watch_tower_hash_check():
    """
    Test that node_watch_tower only transitions to VERIFYING if the commit hash has changed.
    """
    jules_meta = JulesMetadata(
        external_task_id="123",
        status="WORKING",
        last_verified_commit="hash1" # Already verified hash1
    )
    state = {"jules_metadata": jules_meta, "messages": []}

    mock_settings = MagicMock(spec=Settings)
    mock_settings.jules_poll_interval = 0
    mock_settings.github_token = MagicMock()
    mock_settings.github_repository = "test/repo"
    mock_settings.jules_username = "jules"

    with patch("studio.subgraphs.engineer.get_settings", return_value=mock_settings), \
         patch("studio.subgraphs.engineer.JulesGitHubClient") as MockClient:

        mock_client = MockClient.return_value

        # Scenario 1: Hash hasn't changed
        mock_client.get_status.return_value = WorkStatus(
            tracking_id="123",
            status="REVIEW_READY",
            last_commit_hash="hash1"
        )

        result = await node_watch_tower(state)
        assert result["jules_metadata"].status == "WORKING" # Remains WORKING because hash is same

        # Scenario 2: Hash has changed
        mock_client.get_status.return_value = WorkStatus(
            tracking_id="123",
            status="REVIEW_READY",
            last_commit_hash="hash2",
            raw_diff="diff2",
            linked_pr_number=42
        )

        result = await node_watch_tower(state)
        assert result["jules_metadata"].status == "VERIFYING"
        assert result["jules_metadata"].last_verified_commit == "hash2"
        assert result["jules_metadata"].last_verified_pr_number == 42

@pytest.mark.asyncio
async def test_feedback_loop_reuse_task():
    """
    Test that node_feedback_loop sets status to WORKING (to reuse task) instead of QUEUED.
    """
    jules_meta = JulesMetadata(
        external_task_id="123",
        status="FAILED",
        retry_count=0
    )
    state = {"jules_metadata": jules_meta, "messages": []}

    mock_settings = MagicMock(spec=Settings)
    mock_settings.github_token = MagicMock()
    mock_settings.github_repository = "test/repo"
    mock_settings.jules_username = "jules"

    with patch("studio.subgraphs.engineer.get_settings", return_value=mock_settings), \
         patch("studio.subgraphs.engineer.JulesGitHubClient") as MockClient:

        mock_client = MockClient.return_value

        result = await node_feedback_loop(state)

        assert result["jules_metadata"].status == "WORKING"
        assert result["jules_metadata"].retry_count == 1
        mock_client.post_feedback.assert_called_once()

def test_route_feedback_loop_working():
    """
    Test that route_feedback_loop routes WORKING status to watch_tower.
    """
    state = {
        "jules_metadata": JulesMetadata(status="WORKING")
    }
    assert route_feedback_loop(state) == "watch_tower"

@pytest.mark.asyncio
async def test_architect_gate_merge_pr():
    """
    Test that node_architect_gate calls review_pr (APPROVE) then merge_pr on success.
    """
    jules_meta = JulesMetadata(
        external_task_id="123",
        status="COMPLETED",
        last_verified_pr_number=42
    )
    state = {"jules_metadata": jules_meta, "messages": []}

    with patch("studio.subgraphs.engineer.JulesGitHubClient") as MockClient, \
         patch("studio.subgraphs.engineer.ArchitectAgent") as MockArchitect, \
         patch("studio.subgraphs.engineer.checkout_pr_branch") as mock_checkout, \
         patch("studio.subgraphs.engineer.os.path.exists", return_value=False):

        mock_client = MockClient.return_value
        mock_architect = MockArchitect.return_value
        mock_architect.review_code.return_value = MagicMock(status="APPROVED", violations=[])

        await node_architect_gate(state)

        mock_client.review_pr.assert_called_once_with(42, event="APPROVE", body="All checks passed. Merging.")
        mock_client.merge_pr.assert_called_once_with(42)

@pytest.mark.asyncio
async def test_architect_gate_request_changes_on_violation():
    """
    Test that node_architect_gate calls review_pr (REQUEST_CHANGES) when violations are found.
    """
    from studio.agents.architect import ReviewVerdict, Violation
    jules_meta = JulesMetadata(
        external_task_id="123",
        status="COMPLETED",
        last_verified_pr_number=99,
        active_context_slice=ContextSlice(files=["foo.py"])
    )
    state = {"jules_metadata": jules_meta, "messages": []}

    mock_violation = MagicMock()
    mock_violation.severity = "HIGH"
    mock_violation.rule_id = "SRP"
    mock_violation.file_path = "foo.py"
    mock_violation.description = "Class does too much"
    mock_violation.suggested_fix = "Split into smaller classes"

    mock_verdict = MagicMock()
    mock_verdict.status = "REJECTED"
    mock_verdict.violations = [mock_violation]

    with patch("studio.subgraphs.engineer.JulesGitHubClient") as MockClient, \
         patch("studio.subgraphs.engineer.ArchitectAgent") as MockArchitect, \
         patch("studio.subgraphs.engineer.checkout_pr_branch") as mock_checkout, \
         patch("studio.subgraphs.engineer.os.path.exists", return_value=True), \
         patch("builtins.open", unittest.mock.mock_open(read_data="code")):

        mock_client = MockClient.return_value
        mock_architect = MockArchitect.return_value
        mock_architect.review_code.return_value = mock_verdict

        result = await node_architect_gate(state)

        mock_client.review_pr.assert_called_once()
        args, kwargs = mock_client.review_pr.call_args
        # Arguments: (pr_number, event, body)
        assert args[0] == 99
        assert kwargs.get("event") == "REQUEST_CHANGES"
        mock_client.merge_pr.assert_not_called()
        assert result["jules_metadata"].status == "FAILED"

def test_jules_client_review_pr():
    """
    Test that JulesGitHubClient.review_pr submits a formal GitHub PR review.
    """
    with patch("studio.utils.jules_client.Github"):
        client = JulesGitHubClient(github_token=MagicMock(), repo_name="test/repo")
        assert hasattr(client, "review_pr")

        mock_pr = MagicMock()
        client.repo.get_pull = MagicMock(return_value=mock_pr)

        assert client.review_pr(42, event="APPROVE", body="LGTM")
        mock_pr.create_review.assert_called_once_with(body="LGTM", event="APPROVE")

        mock_pr.create_review.reset_mock()
        assert client.review_pr(42, event="REQUEST_CHANGES", body="Fix violations")
        mock_pr.create_review.assert_called_once_with(body="Fix violations", event="REQUEST_CHANGES")

def test_jules_client_merge_pr():
    """
    Test that JulesGitHubClient has a merge_pr method.
    """
    with patch("studio.utils.jules_client.Github"):
        client = JulesGitHubClient(github_token=MagicMock(), repo_name="test/repo")
        assert hasattr(client, "merge_pr")

        # Test implementation (mocking repo.get_pull)
        mock_pr = MagicMock()
        mock_pr.merged = False
        mock_status = MagicMock()
        mock_status.merged = True
        mock_pr.merge.return_value = mock_status
        client.repo.get_pull = MagicMock(return_value=mock_pr)

        assert client.merge_pr(42) is True
        mock_pr.merge.assert_called_once_with(merge_method="merge")
