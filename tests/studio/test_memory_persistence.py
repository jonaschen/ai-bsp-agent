import pytest
import json
import os
from studio.memory import StudioMemory

# Mock state data
MOCK_STATE = {
    "phase": "development",
    "active_agent": "Engineer",
    "task_queue": ["implement_rag"],
    "logs": ["init_sequence_complete"]
}

def test_memory_cycle(tmp_path):
    """
    TDD Cycle:
    1. Red: Try to load state from a non-existent file (should handle gracefully or init default).
    2. Green: Save state and verify file existence.
    3. Refactor: Load state and verify content equality.
    """
    # Setup temporary state file
    state_file = tmp_path / "studio_state.json"
    memory = StudioMemory(file_path=str(state_file))

    # Test 1: Initialization (Should create default or handle empty)
    initial_state = memory.load_state()
    assert isinstance(initial_state, dict)

    # Test 2: Write Persistence
    memory.save_state(MOCK_STATE)
    assert state_file.exists()

    # Test 3: Read Integrity
    loaded_state = memory.load_state()
    assert loaded_state["active_agent"] == "Engineer"
    assert loaded_state["task_queue"][0] == "implement_rag"

def test_schema_validation():
    """
    Ensure state adheres to the required schema keys defined in AGENTS.md.
    """
    memory = StudioMemory() # Uses default path
    state = memory.get_template()
    required_keys = ["phase", "active_agent", "task_queue", "logs", "artifacts"]
    for key in required_keys:
        assert key in state
