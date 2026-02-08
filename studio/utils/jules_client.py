import uuid
from typing import List, Optional
from pydantic import BaseModel
from studio.memory import CodeChangeArtifact

class RemoteStatus(BaseModel):
    state: str
    artifacts: List[CodeChangeArtifact] = []

class JulesClient:
    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    async def start_session(self, session_id: str, prompt: str, files: dict) -> str:
        return f"task_{uuid.uuid4()}"

    async def get_status(self, task_id: str) -> RemoteStatus:
        # Mock behavior: Always complete with a dummy patch
        return RemoteStatus(
            state="COMPLETED",
            artifacts=[
                CodeChangeArtifact(
                    file_path="mock.py",
                    diff_content="<<<<<<< SEARCH\nfoo\n=======\nbar\n>>>>>>> REPLACE",
                    change_type="MODIFY"
                )
            ]
        )

    async def get_reasoning_traces(self, task_id: str) -> str:
        return "I thought about the problem and decided to fix it."

    async def cancel_task(self, task_id: str):
        pass
