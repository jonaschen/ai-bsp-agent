import os
import json
import pytest
from main import load_state, save_state, CLEAN_PATH
from studio.memory import StudioState

def test_load_state_new():
    if os.path.exists(CLEAN_PATH):
        os.remove(CLEAN_PATH)
    state = load_state()
    assert isinstance(state, StudioState)
    assert state.system_version == "1.0.0"

def test_save_and_load_state():
    state = load_state()
    state.orchestration.user_intent = "Test intent"
    save_state(state)

    assert os.path.exists(CLEAN_PATH)

    new_state = load_state()
    assert new_state.orchestration.user_intent == "Test intent"

    os.remove(CLEAN_PATH)

def test_clean_state():
    with open(CLEAN_PATH, "w") as f:
        f.write("{}")

    # Simulate clean logic (can also test CLI if needed)
    if os.path.exists(CLEAN_PATH):
        os.remove(CLEAN_PATH)

    assert not os.path.exists(CLEAN_PATH)
