import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio
from studio.agents.pr_monitor import PRMonitorAgent
from studio.memory import ReviewVerdict, ReviewSummary

class TestPRMonitorAgent(unittest.IsolatedAsyncioTestCase):
    @patch("studio.agents.pr_monitor.ReviewAgent")
    @patch("studio.agents.pr_monitor.ArchitectAgent")
    def setUp(self, mock_architect, mock_review):
        self.mock_client = MagicMock()
        self.agent = PRMonitorAgent(self.mock_client)
        self.mock_review_agent = self.agent.review_agent
        self.mock_architect_agent = self.agent.architect_agent

    @patch("studio.agents.pr_monitor.apply_virtual_patch")
    @patch("studio.agents.pr_monitor.DockerSandbox")
    async def test_run_once_success(self, mock_sandbox_class, mock_apply_patch):
        # Setup mocks
        mock_pr = MagicMock()
        mock_pr.number = 123
        mock_pr.title = "Test PR"
        mock_pr.base.sha = "basesha"

        self.mock_client.get_open_prs.return_value = [mock_pr]

        # Mock file fetching
        mock_file = MagicMock()
        mock_file.filename = "test.py"
        mock_file.patch = "@@ -1,1 +1,1 @@\n-old\n+new"
        mock_pr.get_files.return_value = [mock_file]
        self.mock_client.get_file_content.return_value = "old"
        mock_apply_patch.return_value = {"test.py": "new"}

        # Mock agents
        self.mock_review_agent.analyze.return_value = ReviewSummary(status="PASSED", root_cause="Good", suggested_fix="N/A")
        self.mock_architect_agent.review_code.return_value = ReviewVerdict(status="APPROVED", quality_score=9.0)

        # Mock sandbox
        mock_sandbox = mock_sandbox_class.return_value
        mock_sandbox.setup_workspace.return_value = True
        mock_sandbox.run_pytest.return_value = MagicMock(passed=True)

        # Run agent
        await self.agent.run_once()

        # Verify actions
        self.mock_client.review_pr.assert_called_with(123, event="APPROVE", body=unittest.mock.ANY)
        self.mock_client.merge_pr.assert_called_with(123)

    @patch("studio.agents.pr_monitor.apply_virtual_patch")
    @patch("studio.agents.pr_monitor.DockerSandbox")
    async def test_run_once_failure(self, mock_sandbox_class, mock_apply_patch):
        # Setup mocks
        mock_pr = MagicMock()
        mock_pr.number = 456
        mock_pr.title = "Fail PR"
        mock_pr.base.sha = "basesha"
        self.mock_client.get_open_prs.return_value = [mock_pr]

        mock_file = MagicMock()
        mock_file.filename = "test.py"
        mock_file.patch = "@@ -1,1 +1,1 @@\n-old\n+new"
        mock_pr.get_files.return_value = [mock_file]
        self.mock_client.get_file_content.return_value = "old"
        mock_apply_patch.return_value = {"test.py": "new"}

        # Mock agents
        self.mock_review_agent.analyze.return_value = ReviewSummary(status="FAILED", root_cause="Bad SOLID", suggested_fix="Fix it")
        self.mock_architect_agent.review_code.return_value = ReviewVerdict(status="APPROVED", quality_score=9.0)

        # Mock sandbox
        mock_sandbox = mock_sandbox_class.return_value
        mock_sandbox.setup_workspace.return_value = True
        mock_sandbox.run_pytest.return_value = MagicMock(passed=True)

        # Run agent
        await self.agent.run_once()

        # Verify actions
        self.mock_client.review_pr.assert_called_with(456, event="REQUEST_CHANGES", body=unittest.mock.ANY)
        self.mock_client.merge_pr.assert_not_called()

if __name__ == "__main__":
    unittest.main()
