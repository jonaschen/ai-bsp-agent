import os
import json
import tempfile
import copy
from typing import Any, Dict

class StudioMemory:
    """
    Centralized Memory Management System for the Studio.
    Encapsulates studio_state.json operations, ensuring data consistency
    and enforcing Data Sovereignty rules.
    """

    DEFAULT_STATE = {
        "metadata": {
            "version": "5.1",
            "phase": "IDLE",
            "iteration": 0
        },
        "agents": {
            "orchestrator": {},
            "product_owner": { "backlog": [] },
            "scrum_master": { "blockers": [] },
            "architect": { "review_queue": [] },
            "engineer": { "workspace_path": "_workspace/" },
            "qa_agent": { "test_results": [] },
            "optimizer": { "prompt_versions": [] }
        }
    }

    def __init__(self, file_path: str = "studio/studio_state.json"):
        self.file_path = file_path
        self._state = None

    def initialize(self):
        """Creates the default JSON structure if missing or invalid."""
        if not os.path.exists(self.file_path):
            self._state = copy.deepcopy(self.DEFAULT_STATE)
            self.save()
        else:
            self.load()

    def load(self):
        """Loads the state from disk."""
        try:
            with open(self.file_path, "r") as f:
                self._state = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._state = copy.deepcopy(self.DEFAULT_STATE)
            self.save()

    def save(self):
        """Handles file I/O with atomic write to prevent race conditions."""
        if self._state is None:
            return

        dir_name = os.path.dirname(self.file_path)
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name, exist_ok=True)

        fd, temp_path = tempfile.mkstemp(dir=dir_name if dir_name else ".", text=True)
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(self._state, f, indent=4)
            os.replace(temp_path, self.file_path)
        except Exception:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise

    def get_state(self) -> Dict[str, Any]:
        """Returns the current state."""
        if self._state is None:
            self.load()
        return self._state

    def update_global_phase(self, phase: str):
        """Updates the Studio's lifecycle state."""
        state = self.get_state()
        state["metadata"]["phase"] = phase
        self.save()

    def update_agent_state(self, agent_name: str, data: Dict[str, Any]):
        """Updates specific agent slots."""
        state = self.get_state()
        if "agents" not in state:
            state["agents"] = {}
        if agent_name not in state["agents"]:
            state["agents"][agent_name] = {}

        state["agents"][agent_name].update(data)
        self.save()
