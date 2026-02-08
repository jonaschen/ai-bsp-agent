import pytest
import json
import os
import shutil
from studio.orchestrator import Orchestrator

# Fixture: Temporary Studio Environment
@pytest.fixture
def temp_studio(tmp_path):
    # The Orchestrator expects studio/studio_state.json relative to root_dir
    studio_dir = tmp_path / "studio"
    studio_dir.mkdir()
    state_file = studio_dir / "studio_state.json"
    candidate_dir = studio_dir / "_candidate"
    target_dir = studio_dir

    candidate_dir.mkdir(parents=True)

    return {
        "root": tmp_path,
        "state": state_file,
        "candidate": candidate_dir,
        "target": target_dir
    }

def test_orchestrator_initializes_state(temp_studio):
    """
    AGENTS.md Sec 2.1: The Orchestrator manages studio_state.json via StudioMemory.
    Verify it creates a valid default state file if none exists.
    """
    orch = Orchestrator(root_dir=str(temp_studio["root"]))

    assert temp_studio["state"].exists()
    with open(temp_studio["state"]) as f:
        data = json.load(f)
        assert "version" in data
        assert "phase" in data

def test_atomic_swap_protocol(temp_studio):
    """
    AGENTS.md Sec 4 (ESL-2): The Atomic Swap.
    Verify the Orchestrator can swap a candidate file into production
    ONLY if the file exists.
    """
    orch = Orchestrator(root_dir=str(temp_studio["root"]))

    # Setup: Create a candidate file (New Logic)
    candidate_file = temp_studio["candidate"] / "architect.py"
    candidate_file.write_text("print('New Logic')")

    # Setup: Create existing target file (Old Logic)
    target_file = temp_studio["target"] / "architect.py"
    target_file.write_text("print('Old Logic')")

    # Action: Perform Swap
    orch.perform_atomic_swap(
        candidate_path="studio/_candidate/architect.py",
        target_path="studio/architect.py"
    )

    # Assert: Target now contains New Logic
    assert target_file.read_text() == "print('New Logic')"
    # Assert: Candidate is cleaned up
    assert not candidate_file.exists()

def test_state_persistence(temp_studio):
    """
    Ensure the Orchestrator writes safely and persists using StudioMemory.
    """
    orch = Orchestrator(root_dir=str(temp_studio["root"]))
    orch.update_state(key="phase", value="TESTING")

    with open(temp_studio["state"]) as f:
        data = json.load(f)
        assert data["phase"] == "TESTING"
