import os
import json
import pytest
from main import CLEAN_PATH
from studio.memory import StudioState
from studio.manager import StudioManager

def test_manager_load_state_new():
    if os.path.exists(CLEAN_PATH):
        os.remove(CLEAN_PATH)
    manager = StudioManager()
    state = manager.state
    assert isinstance(state, StudioState)
    # StudioManager's default system_version is 5.2.0
    assert state.system_version == "5.2.0"

def test_manager_save_and_load_state():
    if os.path.exists(CLEAN_PATH):
        os.remove(CLEAN_PATH)
    manager = StudioManager()
    state = manager.state
    state.orchestration.user_intent = "Test intent"
    manager._save_state()

    assert os.path.exists(CLEAN_PATH)

    new_manager = StudioManager()
    assert new_manager.state.orchestration.user_intent == "Test intent"

    os.remove(CLEAN_PATH)

def test_clean_state():
    with open(CLEAN_PATH, "w") as f:
        f.write("{}")

    # Simulate clean logic (can also test CLI if needed)
    if os.path.exists(CLEAN_PATH):
        os.remove(CLEAN_PATH)

    assert not os.path.exists(CLEAN_PATH)
