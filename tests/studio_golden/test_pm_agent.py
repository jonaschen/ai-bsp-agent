import pytest
from unittest.mock import MagicMock, patch
from studio.pm import ProductManager

# Fixture: A vague user request regarding the BSP domain
USER_REQUEST_FIXTURE = """
The current system misses race conditions during the suspend/resume cycle.
We need the Pathologist to look deeper into the kernel trace for 'stall' events.
"""

@pytest.mark.integration
@patch("studio.pm.ChatVertexAI")
def test_analyze_request_generates_spec_not_code(mock_chat_class):
    """
    Verifies that the PM converts a request into a structured spec
    and strictly adheres to the 'No Technical Implementation' constraint.
    """
    # Arrange
    mock_chat_instance = mock_chat_class.return_value
    mock_chat_instance.invoke.return_value.content = """
    {
        "feature_title": "Suspend/Resume Stall Detection",
        "user_story": "As a BSP Engineer, I want the Pathologist to analyze kernel traces for 'stall' events during suspend/resume, so that race conditions are identified.",
        "acceptance_criteria": [
            "Pathologist identifies 'stall' events in kernel traces.",
            "Report identifies potential race conditions."
        ]
    }
    """

    pm = ProductManager()

    # Act
    # We mock the blueprint read to ensure isolation
    with patch("builtins.open", new_callable=MagicMock) as mock_open:
        mock_open.return_value.__enter__.return_value.read.return_value = "# Product Blueprint..."
        result = pm.analyze_request(USER_REQUEST_FIXTURE)

    # Assert
    # 1. Check Structure (Must be a dictionary/JSON-like structure)
    assert isinstance(result, dict)
    assert "feature_title" in result
    assert "user_story" in result
    assert "acceptance_criteria" in result

    # 2. Check Content (Must capture the intent)
    assert "suspend/resume" in result["user_story"].lower()

    # 3. Check Constraints (The PM must NOT write code)
    raw_text = str(result).lower()
    forbidden_terms = ["def ", "class ", "import ", "try:", "except:"]
    for term in forbidden_terms:
        assert term not in raw_text, f"PM violated Separation of Concerns by suggesting code: {term}"
