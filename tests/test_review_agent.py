import unittest
import sys
import os
from unittest.mock import MagicMock, patch

# Ensure studio can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class MockBaseModel:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    @classmethod
    def model_validate(cls, data):
        return cls(**data)

class TestReviewAgentImport(unittest.TestCase):
    def setUp(self):
        # Local mock to avoid global pollution
        self.modules_patcher = patch.dict(sys.modules, {
            "dotenv": MagicMock(),
            "langchain_google_vertexai": MagicMock(),
            "langchain_core": MagicMock(),
            "langchain_core.messages": MagicMock(),
            "pydantic": MagicMock(BaseModel=MockBaseModel)
        })
        self.modules_patcher.start()

    def tearDown(self):
        self.modules_patcher.stop()

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
        with patch.dict(os.environ, {"PROJECT_ID": "test-project"}):
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
