import os
import json
import re
from typing import Optional, List
from langchain_google_vertexai import ChatVertexAI
from product.schemas import ConsultantResponse, SOPStep

class KernelPathologistAgent:
    def __init__(self, model_name: str = "gemini-1.5-pro", cached_content: Optional[str] = None):
        """
        Initialize the Kernel Pathologist Agent.

        Args:
            model_name: The Gemini model to use (default gemini-1.5-pro).
            cached_content: Optional Vertex AI Context Cache ID for the kernel source tree.
        """
        self.llm = ChatVertexAI(
            model_name=model_name,
            cached_content=cached_content
        )

    def verify_file_exists(self, path: str) -> bool:
        """
        Verify if a file exists in the filesystem.
        Must be called before recommending any file modification.
        """
        if not path or path == "N/A":
            return False
        return os.path.exists(path)

    def _validate_sop_steps(self, steps: List[SOPStep]) -> List[SOPStep]:
        """Validate SOP steps and ensure file existence for patches."""
        validated_steps = []
        for step in steps:
            if step.action_type == "CODE_PATCH":
                if not self.verify_file_exists(step.file_path):
                    step.action_type = "MEASUREMENT"
                    step.instruction = f"[FILE NOT FOUND: {step.file_path}] " + step.instruction
                    step.file_path = "N/A"
            validated_steps.append(step)
        return validated_steps

    def analyze(self, log_content: str) -> ConsultantResponse:
        """
        Analyze kernel logs (dmesg, logcat, kernel_trace) to diagnose issues.
        Uses Vertex AI for deep analysis and returns a standardized response.
        """
        system_prompt = """
        You are a Kernel Pathologist Agent, a specialized software analysis expert for Android BSP.
        Analyze kernel logs (dmesg, logcat, kernel_trace) and identify root causes.

        Guidelines:
        - Look for panics, null pointers, watchdogs, etc.
        - Output MUST be valid JSON matching ConsultantResponse schema.
        """

        prompt = f"{system_prompt}\n\nLog Content:\n{log_content}\n\nReturn JSON only."
        response = self.llm.invoke(prompt)

        json_match = re.search(r'\{.*\}', response.content, re.DOTALL)
        if not json_match:
            raise ValueError("No valid JSON in response")

        data = json.loads(json_match.group(0))
        diagnosis = ConsultantResponse(**data)
        diagnosis.sop_steps = self._validate_sop_steps(diagnosis.sop_steps)

        return diagnosis
