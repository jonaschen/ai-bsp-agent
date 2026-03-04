import unittest
from unittest.mock import patch, MagicMock
import subprocess
from studio.utils.git_utils import checkout_pr_branch, sync_main_branch

class TestGitUtils(unittest.TestCase):
    @patch("subprocess.run")
    def test_checkout_pr_branch_success(self, mock_run):
        # Configure mock_run to return a successful result
        mock_run.return_value = MagicMock(returncode=0)

        branch_name = "feat/new-api"
        checkout_pr_branch(branch_name)

        # Verify the sequence of git commands
        self.assertEqual(mock_run.call_count, 4)

        # 1. git stash
        mock_run.assert_any_call(["git", "stash"], check=False)

        # 2. git fetch origin
        mock_run.assert_any_call(["git", "fetch", "origin"], check=True)

        # 3. git checkout branch_name
        mock_run.assert_any_call(["git", "checkout", branch_name], check=True)

        # 4. git reset --hard origin/branch_name
        mock_run.assert_any_call(["git", "reset", "--hard", f"origin/{branch_name}"], check=True)

    @patch("subprocess.run")
    def test_sync_main_branch_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)

        sync_main_branch()

        self.assertEqual(mock_run.call_count, 2)
        mock_run.assert_any_call(["git", "checkout", "main"], check=True)
        mock_run.assert_any_call(["git", "pull", "--rebase", "origin", "main"], check=True)

    @patch("subprocess.run")
    def test_sync_main_branch_checkout_failure(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(returncode=1, cmd=["git", "checkout", "main"])

        with self.assertRaises(subprocess.CalledProcessError):
            sync_main_branch()

        self.assertEqual(mock_run.call_count, 1)
        mock_run.assert_called_once_with(["git", "checkout", "main"], check=True)

    @patch("subprocess.run")
    def test_sync_main_branch_pull_failure(self, mock_run):
        def side_effect(*args, **kwargs):
            cmd = args[0]
            if "pull" in cmd:
                raise subprocess.CalledProcessError(returncode=1, cmd=cmd)
            return MagicMock(returncode=0)

        mock_run.side_effect = side_effect

        with self.assertRaises(subprocess.CalledProcessError):
            sync_main_branch()

        self.assertEqual(mock_run.call_count, 2)
        mock_run.assert_any_call(["git", "checkout", "main"], check=True)
        mock_run.assert_any_call(["git", "pull", "--rebase", "origin", "main"], check=True)

if __name__ == "__main__":
    unittest.main()
