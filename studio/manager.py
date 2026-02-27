import os
import json
import shutil
import tempfile
import threading
from typing import Any, Dict
from studio.memory import (
    StudioState, OrchestrationState, EngineeringState, VerificationGate
)

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
        self.state_path = os.path.join(self.root_dir, "studio_state.json")
        self.seed_path = os.path.join(self.root_dir, "studio_state.seed.json")
        self.lock = threading.RLock()
        self.state = self._load_state()

    def _get_default_state(self) -> StudioState:
        return StudioState(
            system_version="5.2.0",
            orchestration=OrchestrationState(
                session_id="SESSION-00",
                user_intent="BOOTSTRAP"
            ),
            engineering=EngineeringState(
                verification_gate=VerificationGate(status="PENDING")
            )
        )

    def _load_state(self) -> StudioState:
        """
        AGENTS.md Sec 9.1: Manager is the State Owner.
        Verify it creates a valid default state file if none exists.
        Attempts to load from studio_state.seed.json if studio_state.json is missing.
        """
        if not os.path.exists(self.state_path):
            # TDD Requirement: Fallback to seed if it exists
            # We check both the local root_dir and the central studio/ directory
            potential_seeds = [
                self.seed_path,
                os.path.join(self.root_dir, "studio", "studio_state.seed.json")
            ]

            for seed in potential_seeds:
                if os.path.exists(seed):
                    with open(seed, "r") as f:
                        try:
                            data = json.load(f)
                            state = StudioState.model_validate(data)
                            self.state = state
                            self._save_state()
                            return state
                        except Exception:
                            # If seed is corrupt, try next one
                            continue

            state = self._get_default_state()
            self.state = state
            self._save_state()
            return state

        with open(self.state_path, "r") as f:
            try:
                data = json.load(f)
                return StudioState.model_validate(data)
            except (json.JSONDecodeError, Exception):
                # If corrupt or invalid, backup and reset (or just reset for MVP)
                # For safety, we should probably backup.
                if os.path.getsize(self.state_path) > 0:
                    shutil.copy2(self.state_path, self.state_path + ".corrupt")

                state = self._get_default_state()
                self.state = state
                self._save_state()
                return state

    def _save_state(self):
        """
        AGENTS.md Sec 9: Data Sovereignty.
        Ensure _save_state() writes to a temporary file first, then renames it (atomic write).
        """
        with self.lock:
            fd, temp_path = tempfile.mkstemp(dir=self.root_dir, text=True)
            # Use model_dump_json to serialize Pydantic model
            json_str = self.state.model_dump_json(indent=4)

            with os.fdopen(fd, 'w') as f:
                f.write(json_str)

            os.replace(temp_path, self.state_path)

    def update_state(self, key: str, value: Any):
        """
        Updates a key in the state and saves it.
        Supports dot notation for nested keys (e.g., 'orchestration.session_id').
        """
        keys = key.split('.')
        target = self.state

        # Traverse to the parent of the target key
        for k in keys[:-1]:
            if hasattr(target, k):
                target = getattr(target, k)
            elif isinstance(target, dict) and k in target:
                target = target[k]
            else:
                # If we can't traverse, we might need to handle it or raise error.
                # For robustness, we might want to fail explicitly.
                raise KeyError(f"Key path '{key}' not found in state.")

        final_key = keys[-1]

        # Update the value
        if hasattr(target, final_key):
             setattr(target, final_key, value)
        elif isinstance(target, dict):
            target[final_key] = value
        else:
             raise KeyError(f"Cannot update key '{final_key}' on object {type(target)}")

        self._save_state()

    def get_view_for_agent(self, role: str) -> Dict[str, Any]:
        """
        Delegates to StudioState.get_view_for_agent.
        """
        return self.state.get_agent_slice(role)

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
