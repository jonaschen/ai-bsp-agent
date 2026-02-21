import unittest
from unittest.mock import MagicMock, patch
from studio.utils.jules_client import JulesGitHubClient

class TestJulesDiff(unittest.TestCase):
    def test_diff_generation_with_prefixes_and_newlines(self):
        # Mock SecretStr
        mock_token = MagicMock()
        mock_token.get_secret_value.return_value = "token"

        # Instantiate client with mocks
        with patch('studio.utils.jules_client.Github'):
            client = JulesGitHubClient(mock_token, "repo")

        # Create mock files
        file1 = MagicMock()
        file1.filename = "file1.py"
        file1.patch = "@@ -1 +1 @@\n-old1\n+new1" # NO trailing newline

        file2 = MagicMock()
        file2.filename = "file2.py"
        file2.patch = "@@ -1 +1 @@\n-old2\n+new2\n" # WITH trailing newline

        diff_files = [file1, file2]

        # We need to mock pr.get_files() to return our mock files
        mock_pr = MagicMock()
        mock_pr.get_files.return_value = diff_files
        mock_pr.state = "open"
        mock_pr.number = 1
        mock_pr.html_url = "url"
        mock_pr.head.sha = "sha"
        mock_pr.additions = 2
        mock_pr.deletions = 2

        # Mock repo and issue to get to _find_linked_pr
        mock_issue = MagicMock()
        mock_issue.state = "open"

        with patch.object(JulesGitHubClient, 'repo', new_callable=unittest.mock.PropertyMock) as mock_repo_prop:
            mock_repo = mock_repo_prop.return_value
            mock_repo.get_issue.return_value = mock_issue

            with patch.object(client, '_find_linked_pr', return_value=mock_pr):
                status = client.get_status("123")
                diff_text = status.raw_diff

        # Expected format:
        # --- a/file1.py
        # +++ b/file1.py
        # @@ -1 +1 @@
        # -old1
        # +new1
        # --- a/file2.py
        # +++ b/file2.py
        # @@ -1 +1 @@
        # -old2
        # +new2
        #

        expected = (
            "--- a/file1.py\n"
            "+++ b/file1.py\n"
            "@@ -1 +1 @@\n"
            "-old1\n"
            "+new1\n"
            "--- a/file2.py\n"
            "+++ b/file2.py\n"
            "@@ -1 +1 @@\n"
            "-old2\n"
            "+new2\n"
        )

        self.assertEqual(diff_text, expected)

if __name__ == '__main__':
    unittest.main()
