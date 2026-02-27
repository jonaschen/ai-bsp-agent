import os
import json
import pytest
import tempfile
from studio.manager import StudioManager
from studio.memory import StudioState

class TestStudioManagerSeedFallback:
    def test_load_seed_if_state_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            seed_path = os.path.join(temp_dir, "studio_state.seed.json")
            state_path = os.path.join(temp_dir, "studio_state.json")

            # 1. Ensure studio_state.json does not exist
            if os.path.exists(state_path):
                os.remove(state_path)
            assert not os.path.exists(state_path)

            # 2. Create a mock studio_state.seed.json
            # We need to provide a valid StudioState structure
            seed_data = {
                "system_version": "5.9.9-SEED",
                "orchestration": {
                    "session_id": "SEED-SESSION",
                    "user_intent": "SEED-TEST"
                },
                "engineering": {
                    "verification_gate": {"status": "PENDING"}
                }
            }
            with open(seed_path, "w") as f:
                json.dump(seed_data, f)

            # 3. Initialize StudioManager
            manager = StudioManager(root_dir=temp_dir)

            # 4. Assert that StudioManager loaded data from the seed file
            assert manager.state.system_version == "5.9.9-SEED"
            assert manager.state.orchestration.session_id == "SEED-SESSION"

            # 5. Assert that StudioManager created a new studio_state.json
            assert os.path.exists(state_path)
            with open(state_path, "r") as f:
                saved_data = json.load(f)
                assert saved_data["system_version"] == "5.9.9-SEED"

    def test_load_state_if_exists(self):
        # Ensure it still prioritizes studio_state.json if it exists
        with tempfile.TemporaryDirectory() as temp_dir:
            seed_path = os.path.join(temp_dir, "studio_state.seed.json")
            state_path = os.path.join(temp_dir, "studio_state.json")

            seed_data = {
                "system_version": "SEED-VER",
                "orchestration": {"session_id": "SEED-S", "user_intent": "SEED-I"},
                "engineering": {"verification_gate": {"status": "PENDING"}}
            }
            state_data = {
                "system_version": "STATE-VER",
                "orchestration": {"session_id": "STATE-S", "user_intent": "STATE-I"},
                "engineering": {"verification_gate": {"status": "PENDING"}}
            }

            with open(seed_path, "w") as f:
                json.dump(seed_data, f)
            with open(state_path, "w") as f:
                json.dump(state_data, f)

            manager = StudioManager(root_dir=temp_dir)
            assert manager.state.system_version == "STATE-VER"
            assert manager.state.orchestration.session_id == "STATE-S"

    def test_default_fallback_if_both_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = StudioManager(root_dir=temp_dir)
            # Should fallback to _get_default_state()
            assert manager.state.system_version == "5.2.0"
            assert os.path.exists(os.path.join(temp_dir, "studio_state.json"))
