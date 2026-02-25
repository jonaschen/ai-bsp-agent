import unittest
from unittest.mock import patch, mock_open, MagicMock
import json
import os
import sys

# Ensure studio can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from studio.utils.prompts import update_system_prompt, PROMPTS_JSON, fetch_system_prompt, DEFAULT_PROMPTS

class TestPrompts(unittest.TestCase):

    @patch("builtins.open", new_callable=mock_open)
    @patch("studio.utils.prompts.os.path.exists")
    @patch("studio.utils.prompts.json.dump")
    @patch("studio.utils.prompts.json.load")
    def test_update_system_prompt_new_file(self, mock_load, mock_dump, mock_exists, mock_file):
        """Test creating a new prompts.json file."""
        mock_exists.return_value = False

        update_system_prompt("engineer", "New Prompt")

        # Verify read was not attempted (because exists returned False)
        # Note: The implementation checks if exists, if so reads. If not, prompts = {}.
        # So load should not be called.
        mock_load.assert_not_called()

        # Verify write
        mock_file.assert_called_with(PROMPTS_JSON, "w")
        mock_dump.assert_called_once()
        args, _ = mock_dump.call_args
        self.assertEqual(args[0], {"engineer": "New Prompt"})

    @patch("builtins.open", new_callable=mock_open)
    @patch("studio.utils.prompts.os.path.exists")
    @patch("studio.utils.prompts.json.dump")
    @patch("studio.utils.prompts.json.load")
    def test_update_system_prompt_existing_file(self, mock_load, mock_dump, mock_exists, mock_file):
        """Test updating an existing prompts.json file."""
        mock_exists.return_value = True
        mock_load.return_value = {"architect": "Old Prompt"}

        update_system_prompt("engineer", "New Prompt")

        # Verify read
        mock_load.assert_called_once()

        # Verify write
        mock_dump.assert_called_once()
        args, _ = mock_dump.call_args
        self.assertEqual(args[0], {"architect": "Old Prompt", "engineer": "New Prompt"})

    @patch("builtins.open", new_callable=mock_open)
    @patch("studio.utils.prompts.os.path.exists")
    @patch("studio.utils.prompts.json.dump")
    @patch("studio.utils.prompts.json.load")
    def test_update_system_prompt_read_failure(self, mock_load, mock_dump, mock_exists, mock_file):
        """Test handling of corrupted prompts.json."""
        mock_exists.return_value = True
        mock_load.side_effect = json.JSONDecodeError("msg", "doc", 0)

        update_system_prompt("engineer", "New Prompt")

        # Verify read attempted
        mock_load.assert_called_once()

        # Verify write with fresh dict (old content lost/ignored due to error)
        mock_dump.assert_called_once()
        args, _ = mock_dump.call_args
        self.assertEqual(args[0], {"engineer": "New Prompt"})

    @patch("builtins.open", new_callable=mock_open)
    @patch("studio.utils.prompts.os.path.exists")
    @patch("studio.utils.prompts.json.dump")
    def test_update_system_prompt_write_failure(self, mock_dump, mock_exists, mock_file):
        """Test handling of write permission errors."""
        mock_exists.return_value = False
        mock_file.side_effect = IOError("Permission denied")

        # Should catch exception and log error, not crash
        update_system_prompt("engineer", "New Prompt")

        mock_dump.assert_not_called()

    @patch("studio.utils.prompts.os.path.exists")
    @patch("studio.utils.prompts.json.load")
    @patch("builtins.open", new_callable=mock_open)
    def test_fetch_system_prompt_custom(self, mock_file, mock_load, mock_exists):
        """Test fetching a custom prompt from file."""
        mock_exists.return_value = True
        mock_load.return_value = {"engineer": "Custom Prompt"}

        prompt = fetch_system_prompt("engineer")
        self.assertEqual(prompt, "Custom Prompt")

    @patch("studio.utils.prompts.os.path.exists")
    def test_fetch_system_prompt_default(self, mock_exists):
        """Test fetching default prompt when file missing."""
        mock_exists.return_value = False

        prompt = fetch_system_prompt("engineer")
        self.assertEqual(prompt, DEFAULT_PROMPTS["engineer"])

    @patch("builtins.open", new_callable=mock_open)
    @patch("studio.utils.prompts.os.path.exists")
    @patch("studio.utils.prompts.json.load")
    def test_fetch_system_prompt_fallback_on_error(self, mock_load, mock_exists, mock_file):
        """Test fallback to default prompt when file corrupted."""
        mock_exists.return_value = True
        mock_load.side_effect = json.JSONDecodeError("msg", "doc", 0)

        prompt = fetch_system_prompt("engineer")
        self.assertEqual(prompt, DEFAULT_PROMPTS["engineer"])

if __name__ == "__main__":
    unittest.main()
