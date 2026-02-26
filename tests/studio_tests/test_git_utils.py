import unittest
from unittest.mock import patch, MagicMock
from studio.utils.git_utils import checkout_pr_branch

class TestGitUtils(unittest.TestCase):
    @patch("subprocess.run")
    def test_checkout_pr_branch_success(self, mock_run):
        # Configure mock_run to return a successful result
        mock_run.return_value = MagicMock(returncode=0)

        branch_name = "feat/new-api"
        checkout_pr_branch(branch_name)

        # Verify the sequence of git commands
        self.assertEqual(mock_run.call_count, 3)

        # 1. git stash
        mock_run.assert_any_call(["git", "stash"], check=False)

        # 2. git fetch origin
        mock_run.assert_any_call(["git", "fetch", "origin"], check=True)

        # 3. git checkout branch_name
        mock_run.assert_any_call(["git", "checkout", branch_name], check=True)

if __name__ == "__main__":
    unittest.main()
