import os
import json
import shutil
import tempfile
from typing import Any, Dict

class StudioManager:
    """
    The Manager — The Autopilot
    Monitors system health via studio_state.json.
    Routes work to PM, Architect, or Optimizer.
    Implements Circuit Breakers.
    SOLE authority for writing to studio_state.json.
    """

    DEFAULT_STATE = {
        "version": "1.0",
        "evolution_queue": [],
        "meta": {
            "schema_version": "1.0",
            "system_status": "BOOTSTRAP"
        }
    }

    def __init__(self, root_dir: str = "."):
        self.root_dir = root_dir
        self.state_path = os.path.join(self.root_dir, "studio_state.json")
        self.state = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        """
        AGENTS.md Sec 9.1: Manager is the State Owner.
        Verify it creates a valid default state file if none exists.
        """
        if not os.path.exists(self.state_path):
            state = self.DEFAULT_STATE.copy()
            self.state = state
            self._save_state()
            return state

        with open(self.state_path, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return self.DEFAULT_STATE.copy()

    def _save_state(self):
        """
        AGENTS.md Sec 9: Data Sovereignty.
        Ensure _save_state() writes to a temporary file first, then renames it (atomic write).
        """
        fd, temp_path = tempfile.mkstemp(dir=self.root_dir, text=True)
        with os.fdopen(fd, 'w') as f:
            json.dump(self.state, f, indent=4)

        os.replace(temp_path, self.state_path)

    def update_state(self, key: str, value: Any):
        """
        Updates a key in the state and saves it.
        """
        self.state[key] = value
        self._save_state()

    def perform_atomic_swap(self, candidate_path: str, target_path: str):
        """
        AGENTS.md Sec 4 (ESL-2): The Atomic Swap.
        Verify the Manager can swap a candidate file into production
        ONLY if the file exists.
        """
        full_candidate_path = os.path.join(self.root_dir, candidate_path)
        full_target_path = os.path.join(self.root_dir, target_path)

        if not os.path.exists(full_candidate_path):
            raise FileNotFoundError(f"Candidate file not found: {full_candidate_path}")

        # Backup target if it exists
        if os.path.exists(full_target_path):
            backup_path = full_target_path + ".bak"
            shutil.copy2(full_target_path, backup_path)

        # Ensure target directory exists
        os.makedirs(os.path.dirname(full_target_path), exist_ok=True)

        # Move candidate to target
        shutil.move(full_candidate_path, full_target_path)

    def route_task(self, task_description: str) -> str:
        """
        Routing (Sec 6):
        Implement a basic route_task(task_description) method that returns
        the appropriate agent role.
        """
        task_lower = task_description.lower()
        if any(keyword in task_lower for keyword in ["fix", "bug", "feature", "implement", "logic", "code"]):
            return "Architect"
        if any(keyword in task_lower for keyword in ["prompt", "optimize", "tune", "meta"]):
            return "Optimizer"
        if any(keyword in task_lower for keyword in ["test", "verify", "qa", "pytest"]):
            return "QA"
        if any(keyword in task_lower for keyword in ["plan", "blueprint", "strategy"]):
            return "PM"

        return "Architect"  # Default
