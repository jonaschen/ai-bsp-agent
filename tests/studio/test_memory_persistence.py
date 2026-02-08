import pytest
import json
import os
from studio.memory import StudioMemory, StudioStateSchema

# Fixture: A temporary state file to prevent overwriting the real studio_state.json
@pytest.fixture
def temp_state_file(tmp_path):
    f = tmp_path / "test_studio_state.json"
    initial_state = {
        "phase": "IDLE",
        "step": 0,
        "active_agent": "Orchestrator",
        "artifacts": []
    }
    f.write_text(json.dumps(initial_state))
    return str(f)

def test_memory_load_and_validate(temp_state_file):
    """
    Scenario: The Orchestrator initializes memory.
    Expectation: Data is loaded and validates against the Pydantic Schema.
    """
    memory = StudioMemory(file_path=temp_state_file)
    state = memory.load()

    assert state.phase == "IDLE"
    assert isinstance(state, StudioStateSchema)

def test_memory_update_state(temp_state_file):
    """
    Scenario: The Orchestrator updates the phase to 'RED'.
    Expectation: The file on disk is updated with the new value.
    """
    memory = StudioMemory(file_path=temp_state_file)

    # Mutate
    new_state = memory.load()
    new_state.phase = "RED"
    new_state.step = 1

    memory.save(new_state)

    # Verify persistence
    with open(temp_state_file, 'r') as f:
        data = json.load(f)
        assert data["phase"] == "RED"
        assert data["step"] == 1

def test_schema_violation_raises_error(temp_state_file):
    """
    Scenario: Attempting to save an invalid state (violating strict typing).
    Expectation: Pydantic ValidationError prevents corruption of the JSON file.
    """
    memory = StudioMemory(file_path=temp_state_file)
    state = memory.load()

    # Invalid assignment (e.g., step should be int, not string)
    # Note: Pydantic v2 might coerce, so we test a missing required field or totally wrong type
    with pytest.raises(Exception): # Catch Pydantic ValidationError
        bad_data = {"phase": "RED"} # Missing other fields
        memory.save_raw(bad_data)
