import os
import shutil
from typing import Any
from studio.memory import StudioMemory, StudioStateSchema

class Orchestrator:
    """
    The Orchestrator — The Autopilot
    Monitors system health via StudioMemory.
    Routes work to PM, Architect, or Optimizer.
    Implements Circuit Breakers.
    SOLE authority for writing to studio_state.json via StudioMemory.
    """

    def __init__(self, root_dir: str = "."):
        self.root_dir = root_dir
        self.state_path = os.path.join(self.root_dir, "studio_state.json")
        self.memory = StudioMemory(self.state_path)
        self.state = self.memory.load()

    def update_state(self, **kwargs):
        """
        Updates fields in the state and saves it.
        """
        current_state_dict = self.state.model_dump()
        current_state_dict.update(kwargs)
        self.state = StudioStateSchema(**current_state_dict)
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
