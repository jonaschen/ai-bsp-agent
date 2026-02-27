import pytest
from unittest.mock import MagicMock, patch, mock_open
from studio.agents.product_owner import run_po_cycle, BlueprintAnalysis
from studio.memory import Ticket

def test_run_po_cycle_deduplication():
    """
    TDD: Prove that run_po_cycle filters out tickets that already exist in the orchestration state.
    Existing: TKT-001 (task_queue), TKT-002 (completed_tasks_log), TKT-004 (sprint_backlog), TKT-005 (failed_tasks_log)
    Generated: TKT-001, TKT-002, TKT-003, TKT-004, TKT-005
    Expected: Only TKT-003
    """
    tkt1 = Ticket(id="TKT-001", title="Task 1", description="Desc 1", priority="HIGH", source_section_id="1.1")
    tkt2 = Ticket(id="TKT-002", title="Task 2", description="Desc 2", priority="MEDIUM", source_section_id="1.2")
    tkt3 = Ticket(id="TKT-003", title="Task 3", description="Desc 3", priority="LOW", source_section_id="1.3")
    tkt_sprint = Ticket(id="TKT-004", title="Task 4", description="Desc 4", priority="LOW", source_section_id="1.4")
    tkt_failed = Ticket(id="TKT-005", title="Task 5", description="Desc 5", priority="LOW", source_section_id="1.5")

    # The OrchestratorState might contain these in different lists
    state_dict = {
        "orchestration": {
            "task_queue": [tkt1],
            "completed_tasks_log": [tkt2],
            "sprint_backlog": [tkt_sprint],
            "failed_tasks_log": [tkt_failed]
        }
    }

    # Mocking PO's analyze_specs to return all tickets (including duplicates)
    mock_analysis = BlueprintAnalysis(
        blueprint_version_hash="test-hash",
        summary_of_changes="test-summary",
        new_tickets=[tkt1, tkt2, tkt3, tkt_sprint, tkt_failed]
    )

    with patch("studio.agents.product_owner.ChatVertexAI"): # Avoid auth issues
        with patch("studio.agents.product_owner.ProductOwnerAgent.analyze_specs", return_value=mock_analysis):
            with patch("builtins.open", mock_open(read_data="blueprint content")):
                # Action
                result = run_po_cycle(state_dict)

                # Assertions
                result_ids = [t.id for t in result]

                # Currently it's expected to FAIL here because deduplication isn't implemented.
                # It will return all 5 tickets.
                assert "TKT-001" not in result_ids, "TKT-001 should be filtered out (already in task_queue)"
                assert "TKT-002" not in result_ids, "TKT-002 should be filtered out (already in completed_tasks_log)"
                assert "TKT-004" not in result_ids, "TKT-004 should be filtered out (already in sprint_backlog)"
                assert "TKT-005" not in result_ids, "TKT-005 should be filtered out (already in failed_tasks_log)"
                assert "TKT-003" in result_ids, "TKT-003 should be present (it is net new)"
                assert len(result) == 1, f"Expected 1 ticket, got {len(result)}: {result_ids}"
