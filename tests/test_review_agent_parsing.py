import unittest
import sys
import os
import re
from unittest.mock import MagicMock

# Mock dependencies before importing studio.review_agent
sys.modules["dotenv"] = MagicMock()
sys.modules["langchain_google_vertexai"] = MagicMock()
sys.modules["langchain_core"] = MagicMock()
sys.modules["langchain_core.messages"] = MagicMock()

# Mock pydantic with a real class for BaseModel to avoid typing issues
class MockBaseModel:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    @classmethod
    def model_validate(cls, data):
        return cls(**data)

mock_pydantic = MagicMock()
mock_pydantic.BaseModel = MockBaseModel
sys.modules["pydantic"] = mock_pydantic

# Ensure studio can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from studio.review_agent import ReviewAgent, ReviewAgentOutputError

class TestReviewAgentParsing(unittest.TestCase):
    def setUp(self):
        # We need to mock os.environ temporarily for init
        with unittest.mock.patch.dict(os.environ, {"PROJECT_ID": "test-project"}):
            self.agent = ReviewAgent()
            # Disable actual LLM just in case, though imports are mocked
            self.agent.llm = MagicMock()

    def test_valid_json(self):
        """Test parsing of clean, valid JSON."""
        raw_text = '{"status": "PASSED", "root_cause": "Clean code", "suggested_fix": "None"}'
        result = self.agent._clean_and_parse_json(raw_text)
        self.assertEqual(result["status"], "PASSED")
        self.assertEqual(result["root_cause"], "Clean code")

    def test_markdown_wrapped_json(self):
        """Test parsing of JSON wrapped in markdown code blocks."""
        raw_text = """
```json
{
  "status": "FAILED",
  "root_cause": "Violation of SRP",
  "suggested_fix": "Refactor class"
}
```
"""
        result = self.agent._clean_and_parse_json(raw_text)
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["root_cause"], "Violation of SRP")

    def test_conversational_filler(self):
        """Test parsing of JSON surrounded by conversational text."""
        raw_text = """
Here is the analysis of your code:

{
  "status": "PASSED",
  "root_cause": "Good job",
  "suggested_fix": "N/A"
}

Hope this helps!
"""
        result = self.agent._clean_and_parse_json(raw_text)
        self.assertEqual(result["status"], "PASSED")
        self.assertEqual(result["root_cause"], "Good job")

    def test_multiple_braces(self):
        """Test parsing when input contains multiple braces (nested JSON)."""
        raw_text = """
{
  "status": "FAILED",
  "root_cause": "Issue found",
  "details": {
      "line": 10,
      "error": "Syntax error"
  },
  "suggested_fix": "Fix syntax"
}
"""
        result = self.agent._clean_and_parse_json(raw_text)
        self.assertEqual(result["status"], "FAILED")
        self.assertIsInstance(result["details"], dict)
        self.assertEqual(result["details"]["line"], 10)

    def test_malformed_json(self):
        """Test that malformed JSON raises ReviewAgentOutputError."""
        raw_text = '{"status": "PASSED", "root_cause": "Missing brace"'
        with self.assertRaises(ReviewAgentOutputError):
            self.agent._clean_and_parse_json(raw_text)

    def test_empty_input(self):
        """Test that empty input raises ReviewAgentOutputError."""
        with self.assertRaises(ReviewAgentOutputError):
            self.agent._clean_and_parse_json("")
        with self.assertRaises(ReviewAgentOutputError):
            self.agent._clean_and_parse_json("   ")

    def test_normalization(self):
        """Test normalization of legacy fields."""
        raw_text = '{"verdict": "PASS", "comments": "LGTM", "approved": true}'
        result = self.agent._clean_and_parse_json(raw_text)
        self.assertEqual(result["status"], "PASSED")
        self.assertEqual(result["root_cause"], "LGTM")
        self.assertTrue(result["approved"])

    def test_greedy_regex_issue(self):
        """Test potential issue with greedy regex matching across multiple JSON blocks."""
        # This test is designed to fail if the regex is too greedy and captures multiple objects as one
        raw_text = """
Block 1:
{ "id": 1 }
Block 2:
{ "id": 2 }
"""
        # The current implementation uses re.DOTALL which makes . match newlines.
        # It matches from first { to last }.
        # So it will extract:
        # { "id": 1 }
        # Block 2:
        # { "id": 2 }
        # This is invalid JSON.

        with self.assertRaises(ReviewAgentOutputError):
             self.agent._clean_and_parse_json(raw_text)

if __name__ == '__main__':
    unittest.main()
