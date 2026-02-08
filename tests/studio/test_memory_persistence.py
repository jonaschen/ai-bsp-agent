import pytest
import json
import os
from studio.memory import StudioMemory

# Mock State Data based on studio_state.json schema
MOCK_STATE = {
    "iteration": 1,
    "phase": "development",
    "artifacts": {
        "code": {},
        "prompts": {}
    },
    "logs": []
}

def test_memory_persistence(tmp_path):
    """
    TDD Cycle: Red -> Green
    Verifies that StudioMemory can initialize, save, and load state
    without data loss or corruption.
    """
    # Setup temporary state file
    state_file = tmp_path / "studio_state.json"
    memory = StudioMemory(file_path=str(state_file))

    # 1. Test Initialization (Should create default state if missing)
    initial_state = memory.load()
    assert "iteration" in initial_state

    # 2. Test Write
    memory.save(MOCK_STATE)

    # 3. Test Read
    loaded_state = memory.load()
    assert loaded_state["phase"] == "development"
    assert loaded_state["iteration"] == 1

    # 4. Test Immutability/Safety (Basic check)
    # Ensure the file on disk matches the saved dict
    with open(state_file, 'r') as f:
        disk_data = json.load(f)
    assert disk_data == MOCK_STATE
