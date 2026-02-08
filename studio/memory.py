import os
import json
import tempfile
import copy
from typing import Any, Dict

class StudioMemory:
    """
    Centralized Memory Module for Studio Agents.
    Abstracts the persistence layer and ensures atomic writes.
    """

    DEFAULT_STATE = {
        "iteration": 0,
        "metadata": {
            "version": "1.0",
            "last_updated": ""
        },
        "workflow": {
            "current_step": "idle",
            "retry_count": 0
        },
        "buffer": {
            "user_request": "",
            "plan": []
        }
    }

    def __init__(self, file_path: str = "studio_state.json"):
        self.file_path = file_path

    def load(self) -> Dict[str, Any]:
        """
        Loads the state from the file.
        Returns DEFAULT_STATE if the file does not exist or is invalid.
        """
        if not os.path.exists(self.file_path):
            return copy.deepcopy(self.DEFAULT_STATE)

        with open(self.file_path, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return copy.deepcopy(self.DEFAULT_STATE)

    def save(self, state: Dict[str, Any]):
        """
        Saves the state to the file using an atomic write operation.
        """
        dir_name = os.path.dirname(self.file_path) or "."
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name, exist_ok=True)

        fd, temp_path = tempfile.mkstemp(dir=dir_name, text=True)
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(state, f, indent=4)
            os.replace(temp_path, self.file_path)
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise e
