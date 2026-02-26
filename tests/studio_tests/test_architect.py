import unittest
from unittest.mock import MagicMock, patch, mock_open
import sys
import os

# Ensure studio can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from studio.agents.architect import ArchitectAgent, ReviewVerdict, Violation

class TestArchitectGoodEnough(unittest.TestCase):

    def setUp(self):
        # We need to mock open during __init__
        with patch("studio.agents.architect.ChatVertexAI"):
            with patch("builtins.open", mock_open(read_data="CONSTITUTION")):
                self.agent = ArchitectAgent()

    @patch("langchain_core.runnables.RunnableSequence.invoke")
    def test_good_enough_threshold_approved_with_tech_debt(self, mock_invoke):
        """
        TDD: Code with score 8.5 and only MINOR violations should be APPROVED_WITH_TECH_DEBT.
        """
        # Mocking the LLM chain invoke to return a "NEEDS_REFACTOR" verdict with 8.5 score
        mock_verdict = ReviewVerdict(
            status="NEEDS_REFACTOR",
            quality_score=8.5,
            violations=[
                Violation(
                    rule_id="SRP",
                    severity="MINOR",
                    description="Slightly long method",
                    file_path="test.py",
                    suggested_fix="Break it down"
                )
            ]
        )
        mock_invoke.return_value = mock_verdict

        verdict = self.agent.review_code("test.py", "print('hello')", "TKT-1")

        self.assertEqual(verdict.status, "APPROVED_WITH_TECH_DEBT")
        self.assertEqual(verdict.tech_debt_tag, "#TODO: Tech Debt")

    @patch("langchain_core.runnables.RunnableSequence.invoke")
    def test_below_threshold_remains_needs_refactor(self, mock_invoke):
        """
        Code with score 7.5 should remain NEEDS_REFACTOR.
        """
        mock_verdict = ReviewVerdict(
            status="NEEDS_REFACTOR",
            quality_score=7.5,
            violations=[
                Violation(
                    rule_id="SRP",
                    severity="MAJOR",
                    description="Too complex",
                    file_path="test.py",
                    suggested_fix="Split it"
                )
            ]
        )
        mock_invoke.return_value = mock_verdict

        verdict = self.agent.review_code("test.py", "complex code", "TKT-1")

        self.assertEqual(verdict.status, "NEEDS_REFACTOR")

    @patch("langchain_core.runnables.RunnableSequence.invoke")
    def test_critical_violation_remains_rejected(self, mock_invoke):
        """
        Code with score 9.0 but a CRITICAL violation should remain REJECTED.
        """
        mock_verdict = ReviewVerdict(
            status="REJECTED",
            quality_score=9.0,
            violations=[
                Violation(
                    rule_id="SEC",
                    severity="CRITICAL",
                    description="Hardcoded secret",
                    file_path="test.py",
                    suggested_fix="Use env var"
                )
            ]
        )
        mock_invoke.return_value = mock_verdict

        verdict = self.agent.review_code("test.py", "secret='123'", "TKT-1")

        self.assertEqual(verdict.status, "REJECTED")

if __name__ == '__main__':
    unittest.main()
