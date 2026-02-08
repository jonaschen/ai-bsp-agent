import os
import shutil
from typing import Any, Dict
from studio.memory import StudioMemory

class StudioManager:
    """
    The Manager — The Autopilot
    Monitors system health via studio_state.json.
    Routes work to PM, Architect, or Optimizer.
    Implements Circuit Breakers.
    SOLE authority for writing to studio_state.json.
    """

    def __init__(self, root_dir: str = "."):
        self.root_dir = root_dir
        self.memory = StudioMemory(file_path=os.path.join(self.root_dir, "studio_state.json"))
        self.memory.initialize()

    @property
    def state(self) -> Dict[str, Any]:
        """Returns the current state from memory."""
        return self.memory.get_state()

    def update_state(self, key: str, value: Any):
        """
        Updates a key in the state and saves it.
        Maintained for backward compatibility.
        """
        state = self.memory.get_state()
        state[key] = value
        self.memory.save()

    def update_global_phase(self, phase: str):
        """Updates the Studio's lifecycle state."""
        self.memory.update_global_phase(phase)

    def update_agent_state(self, agent_name: str, data: Dict[str, Any]):
        """Updates specific agent slots."""
        self.memory.update_agent_state(agent_name, data)

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
