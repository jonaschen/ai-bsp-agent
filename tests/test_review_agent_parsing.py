import unittest
import sys
import os
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
        # Mock env vars
        with unittest.mock.patch.dict(os.environ, {"PROJECT_ID": "test-project"}):
            self.agent = ReviewAgent()
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

    def test_nested_json(self):
        """Test parsing when input contains nested JSON objects."""
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

    def test_braces_in_conversational_text_with_markdown(self):
        """Test parsing when conversational text contains braces, followed by markdown JSON."""
        # This case exposes the greedy regex issue if not handled correctly.
        # The greedy regex '({.*})' will capture from first { to last }.
        raw_text = """
The code contains a function `def foo(x): return {x}` which is fine.
Here is the review result:
```json
{
  "status": "PASSED",
  "root_cause": "No issues found",
  "suggested_fix": "N/A"
}
```
"""
        # Expected behavior: The JSON inside ```json ... ``` should be extracted.
        # If greedy regex captures `return {x} ... { ... }`, json.loads will fail.
        result = self.agent._clean_and_parse_json(raw_text)
        self.assertEqual(result["status"], "PASSED")

    def test_braces_in_conversational_text_no_markdown(self):
        """Test parsing when conversational text contains braces, followed by raw JSON (no markdown)."""
        # This is a harder case.
        raw_text = """
The code contains a function `def foo(x): return {x}` which is fine.
Here is the review result:
{
  "status": "PASSED",
  "root_cause": "No issues found",
  "suggested_fix": "N/A"
}
"""
        # If greedy regex captures `return {x} ... { ... }`, json.loads will fail.
        # We expect this to be robustly handled.
        result = self.agent._clean_and_parse_json(raw_text)
        self.assertEqual(result["status"], "PASSED")

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

if __name__ == '__main__':
    unittest.main()
