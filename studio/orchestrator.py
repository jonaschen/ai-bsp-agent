import os
import shutil
from typing import Any, Dict
from studio.memory import StudioMemory

class Orchestrator:
    """
    The Orchestrator — The Runtime Executive
    Monitors system health via studio_state.json.
    Routes work to PM, Architect, or Optimizer.
    SOLE authority for writing to studio_state.json.
    """

    def __init__(self, root_dir: str = "."):
        self.root_dir = root_dir
        # AGENTS.md Sec 2.1: The Orchestrator manages studio_state.json via StudioMemory.
        # studio_state.json is located in the studio/ directory.
        state_path = os.path.join(self.root_dir, "studio/studio_state.json")
        self.memory = StudioMemory(file_path=state_path)
        self.state = self.memory.load_state()

        # AGENTS.md Sec 9.1: Ensure a valid default state file exists.
        if not os.path.exists(state_path):
            self.memory.save_state(self.state)

    def update_state(self, key: str, value: Any):
        """
        Updates a key in the state and saves it using StudioMemory.
        """
        self.state = self.memory.load_state()  # Ensure fresh state
        self.state[key] = value
        self.memory.save_state(self.state)

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

        self.memory.append_log(f"Atomic swap: {candidate_path} -> {target_path}", "Orchestrator")

    def route_task(self, task_description: str) -> str:
        """
        Routing (Sec 6):
        Implement a basic route_task(task_description) method that returns
        the appropriate agent role and updates the active_agent in state.
        """
        task_lower = task_description.lower()
        if any(keyword in task_lower for keyword in ["fix", "bug", "feature", "implement", "logic", "code"]):
            role = "Architect"
        elif any(keyword in task_lower for keyword in ["prompt", "optimize", "tune", "meta"]):
            role = "Optimizer"
        elif any(keyword in task_lower for keyword in ["test", "verify", "qa", "pytest"]):
            role = "QA"
        elif any(keyword in task_lower for keyword in ["plan", "blueprint", "strategy"]):
            role = "PM"
        else:
            role = "Architect"  # Default

        self.update_state("active_agent", role)
        self.memory.append_log(f"Routed task to {role}: {task_description[:50]}", "Orchestrator")

        return role
