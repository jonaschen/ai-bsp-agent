import unittest
import sys
import os
from unittest.mock import MagicMock

# Mock dotenv before importing studio.review_agent
sys.modules["dotenv"] = MagicMock()
sys.modules["langchain_google_vertexai"] = MagicMock()
sys.modules["langchain_core"] = MagicMock()
sys.modules["langchain_core.messages"] = MagicMock()

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

class TestReviewAgentImport(unittest.TestCase):
    def test_import_review_agent(self):
        """Test that studio.review_agent can be imported."""
        try:
            from studio import review_agent
            self.assertTrue(True)
        except ImportError as e:
             self.fail(f"Failed to import studio.review_agent: {e}")
        except Exception as e:
            self.fail(f"An error occurred during import: {e}")

    def test_review_agent_instantiation(self):
        """Test that ReviewAgent can be instantiated and methods called."""
        from studio.review_agent import ReviewAgent

        # Mock environment variables
        with unittest.mock.patch.dict(os.environ, {"PROJECT_ID": "test-project"}):
             agent = ReviewAgent()
             # Manually mock LLM since it's disabled in tests by default logic
             agent.llm = MagicMock()

             # Setup mock LLM response
             mock_response = MagicMock()
             mock_response.content = '{"status": "PASSED", "root_cause": "Looks good", "suggested_fix": "None"}'
             agent.llm.invoke.return_value = mock_response

             summary = agent.analyze("diff content")
             self.assertEqual(summary.status, "PASSED")
             self.assertEqual(summary.root_cause, "Looks good")

if __name__ == '__main__':
    unittest.main()
