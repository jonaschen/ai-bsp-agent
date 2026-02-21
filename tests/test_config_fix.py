
import os
import unittest
import tempfile
import shutil
from pydantic import SecretStr
from studio.config import Settings, get_settings

class TestConfigFix(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for the .env file
        self.test_dir = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.test_dir)

        # Backup environment variables
        self.orig_token = os.environ.get("GITHUB_TOKEN")
        self.orig_repo = os.environ.get("GITHUB_REPOSITORY")

        if "GITHUB_TOKEN" in os.environ:
            del os.environ["GITHUB_TOKEN"]
        if "GITHUB_REPOSITORY" in os.environ:
            del os.environ["GITHUB_REPOSITORY"]

        # Create a temporary .env file in the temporary directory
        with open(".env", "w") as f:
            f.write("GITHUB_TOKEN=test-token-from-env\n")
            f.write("GITHUB_REPOSITORY=test/repo-from-env\n")
            f.write("JULES_USERNAME=test-jules\n")

    def tearDown(self):
        # Restore CWD
        os.chdir(self.old_cwd)
        # Remove temporary directory
        shutil.rmtree(self.test_dir)

        # Restore environment variables
        if self.orig_token:
            os.environ["GITHUB_TOKEN"] = self.orig_token
        if self.orig_repo:
            os.environ["GITHUB_REPOSITORY"] = self.orig_repo

    def test_settings_loads_from_env_file(self):
        """Verify that Settings class loads from .env file when os.environ is empty."""
        # We need to test the Settings class directly
        # It will look for .env in the current working directory (which is now our test_dir)
        settings = Settings()

        self.assertEqual(settings.github_token.get_secret_value(), "test-token-from-env")
        self.assertEqual(settings.github_repository, "test/repo-from-env")
        self.assertEqual(settings.jules_username, "test-jules")

        # Verify os.environ is still empty for these keys
        self.assertNotIn("GITHUB_TOKEN", os.environ)
        self.assertNotIn("GITHUB_REPOSITORY", os.environ)

    def test_get_settings_reflects_env_file(self):
        """
        Verify that get_settings() (after potentially being re-initialized)
        picks up the .env file.
        """
        import studio.config
        studio.config._settings = None # Force re-initialization

        settings = get_settings()
        self.assertEqual(settings.github_token.get_secret_value(), "test-token-from-env")
        self.assertEqual(settings.github_repository, "test/repo-from-env")

if __name__ == "__main__":
    unittest.main()
