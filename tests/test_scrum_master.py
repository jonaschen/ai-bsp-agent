import unittest
from unittest.mock import MagicMock, patch
from studio.agents.scrum_master import ScrumMasterAgent, run_scrum_retrospective, RetrospectiveReport, ProcessOptimization
from studio.memory import Ticket

class TestScrumMasterAgent(unittest.TestCase):
    def setUp(self):
        self.mock_llm = MagicMock()
        self.mock_parser = MagicMock()

        # Patch the dependencies
        self.patcher_llm = patch("studio.agents.scrum_master.ChatVertexAI", return_value=self.mock_llm)
        self.patcher_parser = patch("studio.agents.scrum_master.PydanticOutputParser", return_value=self.mock_parser)

        self.patcher_llm.start()
        self.patcher_parser.start()

        self.agent = ScrumMasterAgent()

    def tearDown(self):
        self.patcher_llm.stop()
        self.patcher_parser.stop()

    def test_summarize_logs(self):
        # Create dummy tickets using MagicMock to support dynamic attributes
        t1 = MagicMock()
        t1.id = "T1"
        t1.title = "Task 1"
        t1.retry_count = 2

        t2 = MagicMock()
        t2.id = "T2"
        t2.title = "Task 2"
        t2.failure_log = "Syntax Error"

        summary = self.agent._summarize_logs(completed=[t1], failed=[t2])

        self.assertIn("[PASS] T1: Task 1 (Retries: 2)", summary)
        self.assertIn("[FAIL] T2: Task 2 -> Reason: Syntax Error", summary)

    def test_conduct_retrospective_success(self):
        sprint_data = {
            "sprint_id": "SPRINT-1",
            "completed_tickets_log": [],
            "failed_tickets_log": []
        }

        expected_report = RetrospectiveReport(
            sprint_id="SPRINT-1",
            success_rate=0.0,
            avg_entropy_score=0.5,
            key_bottlenecks=[],
            optimizations=[]
        )

        # Mock chain invoke
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = expected_report

        # Patch ChatPromptTemplate.from_messages
        with patch("studio.agents.scrum_master.ChatPromptTemplate.from_messages") as mock_prompt_cls:
            mock_prompt = MagicMock()
            mock_prompt_cls.return_value = mock_prompt

            # Chain simulation: prompt | llm | parser
            # We need to make sure the result of these pipes is our mock_chain

            mock_chain_step1 = MagicMock()
            mock_prompt.__or__.return_value = mock_chain_step1
            mock_chain_step1.__or__.return_value = mock_chain

            report = self.agent.conduct_retrospective(sprint_data)

            self.assertEqual(report, expected_report)
            mock_chain.invoke.assert_called_once()

    def test_run_scrum_retrospective_not_enough_data(self):
        state = {
            "orchestration_layer": {
                "completed_tasks_log": [],
                "failed_tasks_log": []
            }
        }
        result = run_scrum_retrospective(state)
        self.assertIsNone(result)

    def test_run_scrum_retrospective_enough_data(self):
        # We need 3+ tasks
        tickets = [Ticket(id=f"T{i}", title=f"Task {i}", description="D", priority="LOW", source_section_id="S") for i in range(3)]

        state = {
            "orchestration_layer": {
                "completed_tasks_log": tickets,
                "failed_tasks_log": [],
                "current_sprint_id": "SPRINT-TEST"
            }
        }

        with patch("studio.agents.scrum_master.ScrumMasterAgent") as MockAgentCls:
            mock_agent_instance = MockAgentCls.return_value
            mock_report = RetrospectiveReport(
                sprint_id="SPRINT-TEST",
                success_rate=1.0,
                avg_entropy_score=0.0,
                key_bottlenecks=[],
                optimizations=[]
            )
            mock_agent_instance.conduct_retrospective.return_value = mock_report

            result = run_scrum_retrospective(state)

            self.assertEqual(result, mock_report)
            mock_agent_instance.conduct_retrospective.assert_called_once()

if __name__ == "__main__":
    unittest.main()
