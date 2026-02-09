import unittest
from unittest.mock import MagicMock, patch, mock_open
import sys
import os

# Add repo root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from studio.agents.product_owner import ProductOwnerAgent, BlueprintAnalysis, run_po_cycle, Ticket

class TestProductOwnerAgent(unittest.TestCase):

    def setUp(self):
        # Patch ChatVertexAI to avoid instantiation issues if credentials missing
        with patch("studio.agents.product_owner.ChatVertexAI") as MockLLM:
             self.po = ProductOwnerAgent()
             self.po.llm = MagicMock()
             self.po.parser = MagicMock()

    def test_sort_dag(self):
        # Create tickets with dependencies
        # t1 -> t2 -> t3
        t3 = Ticket(id="t3", title="Task 3", description="Desc 3", priority="LOW", dependencies=["t2"], source_section_id="1")
        t2 = Ticket(id="t2", title="Task 2", description="Desc 2", priority="MEDIUM", dependencies=["t1"], source_section_id="1")
        t1 = Ticket(id="t1", title="Task 1", description="Desc 1", priority="HIGH", dependencies=[], source_section_id="1")

        unsorted_tickets = [t3, t1, t2]
        sorted_tickets = self.po._sort_dag(unsorted_tickets)

        self.assertEqual(len(sorted_tickets), 3)
        self.assertEqual(sorted_tickets[0].id, "t1")
        self.assertEqual(sorted_tickets[1].id, "t2")
        self.assertEqual(sorted_tickets[2].id, "t3")

    def test_sort_dag_cycle(self):
        # Create cycle: t1 -> t2 -> t1
        t1 = Ticket(id="t1", title="Task 1", description="Desc 1", priority="HIGH", dependencies=["t2"], source_section_id="1")
        t2 = Ticket(id="t2", title="Task 2", description="Desc 2", priority="MEDIUM", dependencies=["t1"], source_section_id="1")

        cycle_tickets = [t1, t2]
        # Should return original list (unsorted) or handle gracefully
        # Implementation logs error and returns original list
        result = self.po._sort_dag(cycle_tickets)
        self.assertEqual(len(result), 2)
        # Order might be arbitrary but list should be preserved
        ids = {t.id for t in result}
        self.assertTrue("t1" in ids and "t2" in ids)

    def test_analyze_specs(self):
        # Mock chain invoke
        mock_result = BlueprintAnalysis(
            blueprint_version_hash="hash",
            summary_of_changes="summary",
            new_tickets=[
                Ticket(id="t2", title="Task 2", description="Desc 2", priority="MEDIUM", dependencies=["t1"], source_section_id="1"),
                Ticket(id="t1", title="Task 1", description="Desc 1", priority="HIGH", dependencies=[], source_section_id="1")
            ]
        )

        # We check if sorted
        # t1 -> t2 logic is inside _sort_dag, which analyze_specs calls.
        # But note that in analyze_specs, sorting happens AFTER invoke.
        # So we return unsorted from invoke, and expect sorted from analyze_specs.

        with patch("studio.agents.product_owner.ChatPromptTemplate.from_messages") as mock_prompt_cls:
             mock_prompt = MagicMock()
             mock_prompt_cls.return_value = mock_prompt

             mock_intermediate = MagicMock()
             mock_chain_final = MagicMock()
             mock_chain_final.invoke.return_value = mock_result

             mock_prompt.__or__.return_value = mock_intermediate
             mock_intermediate.__or__.return_value = mock_chain_final

             analysis = self.po.analyze_specs("blueprint", [])

             self.assertEqual(len(analysis.new_tickets), 2)
             self.assertEqual(analysis.new_tickets[0].id, "t1") # Sorted

    def test_run_po_cycle(self):
        with patch("builtins.open", mock_open(read_data="blueprint content")):
            with patch("studio.agents.product_owner.ProductOwnerAgent") as MockPO:
                mock_po_instance = MockPO.return_value
                mock_po_instance.analyze_specs.return_value = BlueprintAnalysis(
                    blueprint_version_hash="hash",
                    summary_of_changes="summary",
                    new_tickets=[Ticket(id="t1", title="Task 1", description="Desc 1", priority="HIGH", dependencies=[], source_section_id="1")]
                )

                # Test with dict state and task_queue as list
                state = {"orchestration": {"task_queue": []}}
                tickets = run_po_cycle(state)

                self.assertEqual(len(tickets), 1)
                self.assertEqual(tickets[0].id, "t1")

if __name__ == '__main__':
    unittest.main()
