import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio
import os
import json
import sys

# Mock dependencies before importing the agent
sys.modules["langchain_google_vertexai"] = MagicMock()
sys.modules["langchain_core"] = MagicMock()
sys.modules["langchain_core.messages"] = MagicMock()

from studio.agents.codebase_analyzer import CodebaseAnalyzerAgent

class TestCodebaseAnalyzerAgent(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_client = MagicMock()

        # Patch ChatVertexAI where it is imported in codebase_analyzer
        self.llm_patcher = patch("studio.agents.codebase_analyzer.ChatVertexAI")
        self.mock_llm_class = self.llm_patcher.start()
        self.mock_llm = self.mock_llm_class.return_value

        with patch.dict(os.environ, {"PROJECT_ID": "test-project"}):
            self.agent = CodebaseAnalyzerAgent(self.mock_client)

    def tearDown(self):
        if hasattr(self, "llm_patcher"):
            self.llm_patcher.stop()

    @patch("os.walk")
    @patch("builtins.open", new_callable=unittest.mock.mock_open, read_data="TODO: fix this bug\nimport openai")
    @patch("os.path.exists")
    async def test_run_scan_finds_issues(self, mock_exists, mock_open, mock_walk):
        mock_exists.return_value = True # For rules.md

        # Mock os.walk to return a mock file
        mock_walk.return_value = [
            (".", [], ["file.py"]),
        ]

        # Mock LLM response
        self.mock_llm.ainvoke = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps([
            {
                "type": "TECH_DEBT",
                "file": "file.py",
                "description": "Found a TODO: fix this bug",
                "severity": "LOW"
            },
            {
                "type": "VIOLATION",
                "file": "file.py",
                "description": "Prohibited import: openai",
                "severity": "CRITICAL"
            }
        ])
        self.mock_llm.ainvoke.return_value = mock_response

        # Run scan
        await self.agent.run_scan()

        # Verify issues were "published" (created on GitHub)
        # We expect 2 calls to create_issue
        self.assertEqual(self.mock_client.create_issue.call_count, 2)

        calls = self.mock_client.create_issue.call_args_list
        # Check that descriptions are in the calls
        bodies = [call[1]["body"] for call in calls]
        self.assertTrue(any("Found a TODO: fix this bug" in b for b in bodies))
        self.assertTrue(any("Prohibited import: openai" in b for b in bodies))

if __name__ == "__main__":
    unittest.main()
