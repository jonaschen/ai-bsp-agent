
import pytest
from unittest.mock import MagicMock, patch
from studio.utils.jules_client import JulesGitHubClient, TaskPayload, TaskPriority
from pydantic import SecretStr

@pytest.fixture
def mock_github():
    with patch("studio.utils.jules_client.Github") as mock_gh:
        yield mock_gh

def test_get_status_constructs_correct_diff(mock_github):
    # Setup mocks
    client = JulesGitHubClient(github_token=SecretStr("fake_token"), repo_name="owner/repo")

    mock_repo = MagicMock()
    client._repo_cache = mock_repo

    mock_issue = MagicMock()
    mock_issue.number = 123
    mock_issue.state = "open"
    mock_repo.get_issue.return_value = mock_issue

    # Mock timeline to find linked PR
    mock_event = MagicMock()
    mock_event.event = "cross-referenced"
    mock_event.source.issue.pull_request = True
    mock_pr = MagicMock()
    mock_pr.number = 456
    mock_pr.state = "open"
    mock_pr.html_url = "http://github.com/owner/repo/pull/456"
    mock_pr.head.sha = "abcdef12345"
    mock_pr.head.ref = "feat/new-api"
    mock_pr.additions = 10
    mock_pr.deletions = 5
    mock_event.source.issue.as_pull_request.return_value = mock_pr
    mock_issue.get_timeline.return_value = [mock_event]

    # Mock PR files with a malformed patch
    mock_file = MagicMock()
    mock_file.filename = "test.py"
    # line1: context, has space
    # (empty line): context, missing space
    # line3: context, missing space
    mock_file.patch = "@@ -1,3 +1,3 @@\n line1\n\nline3"
    mock_pr.get_files.return_value = [mock_file]

    # Execute
    status = client.get_status("123")

    # Verify
    assert status.status == "REVIEW_READY"
    assert "--- a/test.py" in status.raw_diff
    assert "+++ b/test.py" in status.raw_diff

    # Check for normalized context lines
    assert "\n line1\n" in status.raw_diff
    assert "\n \n" in status.raw_diff  # The empty line became a space
    assert "\n line3\n" in status.raw_diff # line3 got its space
