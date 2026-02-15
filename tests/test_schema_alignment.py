import unittest
from unittest.mock import MagicMock, patch, mock_open
import sys
import os

# Add repo root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from studio.agents.product_owner import run_po_cycle, Ticket, BlueprintAnalysis

class TestSchemaAlignment(unittest.TestCase):

    @patch("studio.agents.product_owner.ProductOwnerAgent")
    @patch("builtins.open", new_callable=mock_open, read_data="Mock Blueprint Content")
    def test_run_po_cycle_new_schema(self, mock_file, MockPO):
        """Verifies that 'orchestration_layer' (new schema) is correctly handled."""
        mock_po_instance = MockPO.return_value
        mock_po_instance.analyze_specs.return_value = BlueprintAnalysis(
            blueprint_version_hash="hash",
            summary_of_changes="summary",
            new_tickets=[]
        )

        state = {
            "orchestration_layer": {
                "task_queue": [
                    Ticket(id="T1", title="Existing 1", description="D1", priority="HIGH", source_section_id="S1")
                ]
            }
        }

        run_po_cycle(state)

        # Verify that analyze_specs was called with the correct existing titles
        mock_po_instance.analyze_specs.assert_called_with("Mock Blueprint Content", ["Existing 1"])

    @patch("studio.agents.product_owner.ProductOwnerAgent")
    @patch("builtins.open", new_callable=mock_open, read_data="Mock Blueprint Content")
    def test_run_po_cycle_old_schema(self, mock_file, MockPO):
        """Verifies that 'orchestration' (old schema) is correctly handled as a fallback."""
        mock_po_instance = MockPO.return_value
        mock_po_instance.analyze_specs.return_value = BlueprintAnalysis(
            blueprint_version_hash="hash",
            summary_of_changes="summary",
            new_tickets=[]
        )

        state = {
            "orchestration": {
                "task_queue": [
                    Ticket(id="T2", title="Existing 2", description="D2", priority="HIGH", source_section_id="S2")
                ]
            }
        }

        run_po_cycle(state)

        # Verify that fallback to 'orchestration' worked
        mock_po_instance.analyze_specs.assert_called_with("Mock Blueprint Content", ["Existing 2"])

    @patch("studio.agents.product_owner.ProductOwnerAgent")
    @patch("builtins.open", new_callable=mock_open, read_data="Mock Blueprint Content")
    def test_run_po_cycle_precedence(self, mock_file, MockPO):
        """Verifies that 'orchestration_layer' takes precedence over 'orchestration'."""
        mock_po_instance = MockPO.return_value
        mock_po_instance.analyze_specs.return_value = BlueprintAnalysis(
            blueprint_version_hash="hash",
            summary_of_changes="summary",
            new_tickets=[]
        )

        state = {
            "orchestration_layer": {
                "task_queue": [Ticket(id="T_NEW", title="New Title", description="D", priority="H", source_section_id="S")]
            },
            "orchestration": {
                "task_queue": [Ticket(id="T_OLD", title="Old Title", description="D", priority="H", source_section_id="S")]
            }
        }

        run_po_cycle(state)

        # Should use New Title from orchestration_layer
        mock_po_instance.analyze_specs.assert_called_with("Mock Blueprint Content", ["New Title"])

    @patch("studio.agents.product_owner.ProductOwnerAgent")
    @patch("builtins.open", new_callable=mock_open, read_data="Mock Blueprint Content")
    def test_run_po_cycle_task_queue_dict(self, mock_file, MockPO):
        """Verifies that 'task_queue' as a dictionary is correctly handled."""
        mock_po_instance = MockPO.return_value
        mock_po_instance.analyze_specs.return_value = BlueprintAnalysis(
            blueprint_version_hash="hash",
            summary_of_changes="summary",
            new_tickets=[]
        )

        state = {
            "orchestration_layer": {
                "task_queue": {
                    "T1": Ticket(id="T1", title="Dict Title", description="D1", priority="HIGH", source_section_id="S1")
                }
            }
        }

        run_po_cycle(state)

        mock_po_instance.analyze_specs.assert_called_with("Mock Blueprint Content", ["Dict Title"])

    @patch("studio.agents.product_owner.ProductOwnerAgent")
    @patch("builtins.open", new_callable=mock_open, read_data="Mock Blueprint Content")
    def test_run_po_cycle_task_queue_list_dicts(self, mock_file, MockPO):
        """Verifies that 'task_queue' as a list of dictionaries is correctly handled."""
        mock_po_instance = MockPO.return_value
        mock_po_instance.analyze_specs.return_value = BlueprintAnalysis(
            blueprint_version_hash="hash",
            summary_of_changes="summary",
            new_tickets=[]
        )

        state = {
            "orchestration_layer": {
                "task_queue": [
                    {"title": "List Dict Title"}
                ]
            }
        }

        run_po_cycle(state)

        mock_po_instance.analyze_specs.assert_called_with("Mock Blueprint Content", ["List Dict Title"])

if __name__ == "__main__":
    unittest.main()
