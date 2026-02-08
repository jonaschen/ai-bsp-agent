import json
import os
import fcntl
from typing import List
from pydantic import BaseModel, ValidationError

class StudioStateSchema(BaseModel):
    phase: str
    step: int
    active_agent: str
    artifacts: List[str]

class StudioMemory:
    def __init__(self, file_path: str):
        self.file_path = file_path

    def load(self) -> StudioStateSchema:
        if not os.path.exists(self.file_path):
            # Return a default state if file doesn't exist,
            # though the tests assume it exists from fixture.
            return StudioStateSchema(
                phase="IDLE",
                step=0,
                active_agent="Orchestrator",
                artifacts=[]
            )

        with open(self.file_path, 'r') as f:
            # Apply shared lock for reading
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                data = json.load(f)
                return StudioStateSchema(**data)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def save(self, state: StudioStateSchema):
        self._write_to_file(state.model_dump())

    def save_raw(self, data: dict):
        # This will trigger Pydantic validation if we try to convert it
        # but the test expects it to raise an exception.
        # Let's ensure we validate before saving.
        validated_state = StudioStateSchema(**data)
        self.save(validated_state)

    def _write_to_file(self, data: dict):
        # Atomic write with exclusive lock
        temp_path = self.file_path + ".tmp"
        with open(temp_path, 'w') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                json.dump(data, f, indent=4)
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

        os.replace(temp_path, self.file_path)
