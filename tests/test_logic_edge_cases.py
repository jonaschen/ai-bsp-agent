import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add repo root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from studio.agents.product_owner import ProductOwnerAgent, Ticket
from studio.agents.scrum_master import run_scrum_retrospective

class TestLogicEdgeCases(unittest.TestCase):
    """
    Logic Edge Cases (邏輯邊界測試)
    These tests do not call LLMs, but test the internal Python logic of the Agents.
    """

    def setUp(self):
        # Patch ChatVertexAI to avoid instantiation issues
        self.patcher_po_llm = patch("studio.agents.product_owner.ChatVertexAI")
        self.patcher_sm_llm = patch("studio.agents.scrum_master.ChatVertexAI")
        self.patcher_po_llm.start()
        self.patcher_sm_llm.start()

    def tearDown(self):
        self.patcher_po_llm.stop()
        self.patcher_sm_llm.stop()

    def test_po_circular_dependency(self):
        """
        PO 的「死結」測試 (The Circular Dependency Test)
        Target: Verify ProductOwnerAgent._sort_dag's anti-loop mechanism.
        Scenario: Ticket A depends on Ticket B, and Ticket B depends on Ticket A.
        Expected: networkx might throw an error (or be detected),
                  the code should catch it and return the original list.
        """
        po = ProductOwnerAgent()

        # Create cycle: A -> B -> A
        ticket_a = Ticket(id="A", title="Ticket A", description="Desc A", priority="HIGH", dependencies=["B"], source_section_id="1")
        ticket_b = Ticket(id="B", title="Ticket B", description="Desc B", priority="MEDIUM", dependencies=["A"], source_section_id="1")

        tickets = [ticket_a, ticket_b]

        # We expect it not to crash and return the original list (or some handled list)
        result = po._sort_dag(tickets)

        self.assertEqual(len(result), 2)
        ids = {t.id for t in result}
        self.assertIn("A", ids)
        self.assertIn("B", ids)

    def test_scrum_master_data_starvation(self):
        """
        Scrum Master 的「資料飢餓」測試 (The Data Starvation Test)
        Target: Verify run_scrum_retrospective's threshold check.
        Scenario: Pass a state with only 1 completed task (len(completed) + len(failed) < 3).
        Expected: Function should return None and log it, ensuring no LLM call is wasted.
        """
        # Scenario: Only 1 completed task
        state = {
            "orchestration_layer": {
                "completed_tasks_log": [
                    Ticket(id="T1", title="Task 1", description="D1", priority="LOW", source_section_id="S1")
                ],
                "failed_tasks_log": [],
                "current_sprint_id": "SPRINT-EMPTY"
            }
        }

        # We also mock ScrumMasterAgent to ensure it's NOT even instantiated/called if threshold not met
        with patch("studio.agents.scrum_master.ScrumMasterAgent") as MockSM:
            result = run_scrum_retrospective(state)

            self.assertIsNone(result)
            MockSM.assert_not_called()

if __name__ == "__main__":
    unittest.main()
