import pytest
from unittest.mock import MagicMock, patch
from studio.utils.jules_client import JulesGitHubClient
from pydantic import SecretStr

@pytest.fixture
def mock_github():
    with patch("studio.utils.jules_client.Github") as mock_gh:
        yield mock_gh

def test_post_feedback_on_pr_when_available(mock_github):
    client = JulesGitHubClient(github_token=SecretStr("fake_token"), repo_name="owner/repo", jules_username="google-jules")

    mock_repo = MagicMock()
    client._repo_cache = mock_repo

    mock_issue = MagicMock()
    mock_repo.get_issue.return_value = mock_issue

    # Mock finding a linked PR
    mock_pr = MagicMock()
    with patch.object(JulesGitHubClient, "_find_linked_pr", return_value=mock_pr):
        success = client.post_feedback("123", "Some feedback")

        assert success is True
        # Should NOT call create_comment on the issue if PR is found
        mock_issue.create_comment.assert_not_called()
        # Should call create_issue_comment on the PR
        mock_pr.create_issue_comment.assert_called_once()
        comment_body = mock_pr.create_issue_comment.call_args[0][0]
        assert "@google-jules" in comment_body
        assert "Some feedback" in comment_body

def test_post_feedback_on_issue_fallback(mock_github):
    client = JulesGitHubClient(github_token=SecretStr("fake_token"), repo_name="owner/repo", jules_username="google-jules")

    mock_repo = MagicMock()
    client._repo_cache = mock_repo

    mock_issue = MagicMock()
    mock_repo.get_issue.return_value = mock_issue

    # Mock NO linked PR
    with patch.object(JulesGitHubClient, "_find_linked_pr", return_value=None):
        success = client.post_feedback("123", "General guidance")

        assert success is True
        # Should call create_comment on the issue
        mock_issue.create_comment.assert_called_once()
        comment_body = mock_issue.create_comment.call_args[0][0]
        assert "@google-jules" in comment_body
        assert "General guidance" in comment_body
