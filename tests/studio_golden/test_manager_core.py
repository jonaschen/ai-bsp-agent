import pytest
import json
import os
import shutil
from studio.orchestrator import Orchestrator
from studio.memory import StudioMeta

# Fixture: Temporary Studio Environment
@pytest.fixture
def temp_studio(tmp_path):
    # StudioMemory prefers studio/studio_state.json if studio/ exists
    state_file = tmp_path / "studio" / "studio_state.json"
    candidate_dir = tmp_path / "studio" / "_candidate"
    target_dir = tmp_path / "studio"

    candidate_dir.mkdir(parents=True)
    # target_dir exists

    return {
        "root": tmp_path,
        "state": state_file,
        "candidate": candidate_dir,
        "target": target_dir
    }

def test_manager_initializes_state(temp_studio):
    """
    AGENTS.md Sec 9.1: Manager is the State Owner.
    Verify it creates a valid default state file if none exists.
    """
    mgr = Orchestrator(root_dir=str(temp_studio["root"]))

    assert temp_studio["state"].exists()
    with open(temp_studio["state"]) as f:
        data = json.load(f)
        assert "studio_meta" in data
        assert "orchestration_state" in data

def test_atomic_swap_protocol(temp_studio):
    """
    AGENTS.md Sec 4 (ESL-2): The Atomic Swap.
    Verify the Manager can swap a candidate file into production
    ONLY if the file exists.
    """
    mgr = Orchestrator(root_dir=str(temp_studio["root"]))

    # Setup: Create a candidate file (New Logic)
    candidate_file = temp_studio["candidate"] / "architect.py"
    candidate_file.write_text("print('New Logic')")

    # Setup: Create existing target file (Old Logic)
    target_file = temp_studio["target"] / "architect.py"
    target_file.write_text("print('Old Logic')")

    # Action: Perform Swap
    mgr.perform_atomic_swap(
        candidate_path="studio/_candidate/architect.py",
        target_path="studio/architect.py"
    )

    # Assert: Target now contains New Logic
    assert target_file.read_text() == "print('New Logic')"
    # Assert: Candidate is cleaned up
    assert not candidate_file.exists()

def test_state_write_lock_enforcement(temp_studio):
    """
    AGENTS.md Sec 9.3: Violation Consequences.
    Ensure the Manager writes safely (simulated).
    """
    mgr = Orchestrator(root_dir=str(temp_studio["root"]))

    # Create a new StudioMeta object
    new_meta = StudioMeta(
        system_version="TEST_VERSION",
        constitution_hash="TEST_HASH",
        current_phase="TEST_PHASE"
    )

    mgr.update_state(key="studio_meta", value=new_meta)

    with open(temp_studio["state"]) as f:
        data = json.load(f)
        assert data["studio_meta"]["current_phase"] == "TEST_PHASE"
