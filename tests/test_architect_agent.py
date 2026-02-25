import unittest
from unittest.mock import MagicMock, patch, mock_open
import sys
import os

# Ensure studio can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from studio.agents.architect import ArchitectAgent, run_architect_gate, ReviewVerdict, Violation
from studio.memory import ArchitecturalDecisionRecord

class TestArchitectAgent(unittest.TestCase):

    @patch("studio.agents.architect.ChatVertexAI")
    @patch("builtins.open", new_callable=mock_open, read_data="CONSTITUTION_CONTENT")
    def test_initialization(self, mock_file, mock_llm):
        agent = ArchitectAgent()
        self.assertEqual(agent.constitution_content, "CONSTITUTION_CONTENT")
        self.assertIsNotNone(agent.constitution_hash)

    @patch("studio.agents.architect.ChatVertexAI")
    @patch("builtins.open")
    def test_load_constitution_file_not_found(self, mock_file, mock_llm):
        mock_file.side_effect = FileNotFoundError
        agent = ArchitectAgent()
        self.assertEqual(agent.constitution_content, "CRITICAL: ENFORCE SOLID. NO AGENTS.MD FOUND.")
        self.assertEqual(agent.constitution_hash, "EMERGENCY_MODE")

    @patch("studio.agents.architect.ArchitectAgent")
    def test_run_architect_gate(self, MockArchitectAgent):
        # Setup mock agent instance
        mock_agent_instance = MockArchitectAgent.return_value
        mock_verdict = ReviewVerdict(
            status="APPROVED",
            quality_score=9.0,
            violations=[]
        )
        mock_agent_instance.review_code.return_value = mock_verdict

        engineering_state = {
            "code_artifacts": {
                "proposed_patch": "some diff"
            },
            "workspace_snapshot": {
                "current_file": "test.py",
                "current_file_content": "print('hello')"
            },
            "current_task": "TKT-1"
        }

        result = run_architect_gate(engineering_state)

        self.assertEqual(result["verification_gate"]["status"], "GREEN")
        self.assertEqual(result["code_artifacts"]["static_analysis_report"]["status"], "APPROVED")

        # Check if review_code was called with correct args
        mock_agent_instance.review_code.assert_called_once()
        args, _ = mock_agent_instance.review_code.call_args
        self.assertEqual(args[0], "test.py")
        self.assertEqual(args[1], "print('hello')")
        self.assertEqual(args[2], "TKT-1")

    @patch("studio.agents.architect.ArchitectAgent")
    def test_run_architect_gate_rejected(self, MockArchitectAgent):
        # Setup mock agent instance
        mock_agent_instance = MockArchitectAgent.return_value
        mock_verdict = ReviewVerdict(
            status="REJECTED",
            quality_score=4.0,
            violations=[Violation(
                rule_id="SRP",
                severity="MAJOR",
                description="Too complex",
                file_path="test.py",
                suggested_fix="Split it"
            )]
        )
        mock_agent_instance.review_code.return_value = mock_verdict

        engineering_state = {
            "code_artifacts": {
                "proposed_patch": "some diff"
            },
            "workspace_snapshot": {
                "current_file": "test.py",
                "current_file_content": "complex code"
            },
            "current_task": "TKT-1"
        }

        result = run_architect_gate(engineering_state)

        self.assertEqual(result["verification_gate"]["status"], "RED")
        self.assertIn("ARCHITECT REJECT: Too complex", result["verification_gate"]["blocking_reason"])

if __name__ == '__main__':
    unittest.main()
