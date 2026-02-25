import pytest
from studio.memory import OrchestrationState, Ticket

def test_orchestration_state_sprint_fields():
    """TDD: Test that OrchestrationState supports sprint_goal and sprint_backlog."""
    state = OrchestrationState(
        session_id="session-123",
        user_intent="Update schema",
        sprint_goal="Implement sprint execution support",
        sprint_backlog=[
            Ticket(
                id="TKT-001",
                title="Add fields",
                description="Add sprint_goal and sprint_backlog",
                priority="HIGH",
                source_section_id="1.1"
            )
        ]
    )
    assert state.sprint_goal == "Implement sprint execution support"
    assert len(state.sprint_backlog) == 1
    assert state.sprint_backlog[0].id == "TKT-001"

def test_orchestration_state_sprint_defaults():
    """TDD: Test default values for sprint_goal and sprint_backlog."""
    state = OrchestrationState(
        session_id="session-123",
        user_intent="Update schema"
    )
    assert state.sprint_goal is None
    assert state.sprint_backlog == []
