import os
import shutil
from typing import Any, Dict
from studio.memory import StudioMemory

class Orchestrator:
    """
    The Orchestrator — The Runtime Executive.
    Monitors system health via studio_state.json.
    Routes work between Product Owner, Architect, and Engineer.
    SOLE authority for writing to studio_state.json via StudioMemory.
    """

    def __init__(self, root_dir: str = "."):
        self.root_dir = root_dir
        self.state_path = os.path.join(self.root_dir, "studio_state.json")
        self.memory = StudioMemory(file_path=self.state_path)

        # AGENTS.md Sec 9.1: Ensure default state file exists
        if not os.path.exists(self.state_path):
            self.state = self.memory.load()
            self.memory.save(self.state)
        else:
            self.state = self.memory.load()

    def update_state(self, key: str, value: Any):
        """
        Updates a key in the state and saves it via StudioMemory.
        """
        self.state[key] = value
        self.memory.save(self.state)

    def perform_atomic_swap(self, candidate_path: str, target_path: str):
        """
        AGENTS.md Sec 4 (ESL-2): The Atomic Swap.
        Verify the Orchestrator can swap a candidate file into production
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
