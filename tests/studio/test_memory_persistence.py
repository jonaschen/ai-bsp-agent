import pytest
import json
import os
from studio.memory import StudioMemory

# Fixture for a clean test state
@pytest.fixture
def test_db_path():
    path = "tests/fixtures/studio_state_test.json"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        os.remove(path)
    yield path
    if os.path.exists(path):
        os.remove(path)

def test_memory_initialization_creates_roster_schema(test_db_path):
    """
    TDD: Red.
    Ensure initializing memory creates a valid studio_state.json
    with keys for all Roster agents defined in AGENTS.md.
    """
    memory = StudioMemory(file_path=test_db_path)
    memory.initialize()

    with open(test_db_path, 'r') as f:
        state = json.load(f)

    # Verify Roster slots exist per AGENTS.md Section 2
    required_agents = [
        "orchestrator",
        "product_owner",
        "scrum_master",
        "architect",
        "engineer",
        "qa_agent",
        "optimizer"
    ]

    for agent in required_agents:
        assert agent in state["agents"], f"Missing schema for {agent}"

    # Verify Global State
    assert "metadata" in state
    assert state["metadata"]["phase"] == "IDLE"

def test_orchestrator_state_transition(test_db_path):
    """
    TDD: Red.
    Simulate the Orchestrator updating the global phase and assigning a task.
    """
    memory = StudioMemory(file_path=test_db_path)
    memory.initialize()

    # Orchestrator moves state to CODING
    memory.update_global_phase("CODING")

    # Orchestrator assigns task to Engineer
    task_payload = {"ticket_id": "BSP-101", "description": "Fix S2D Hang"}
    memory.update_agent_state("engineer", {"current_task": task_payload})

    # Reload from disk to verify persistence
    memory_reload = StudioMemory(file_path=test_db_path)
    state = memory_reload.get_state()

    assert state["metadata"]["phase"] == "CODING"
    assert state["agents"]["engineer"]["current_task"]["ticket_id"] == "BSP-101"
