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
            model_name: The Gemini model to use (default gemini-1.5-pro for stability).
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
        # In a real Android BSP environment, the path might be relative to the kernel root.
        # For the purpose of this tool, we check for direct existence.
        return os.path.exists(path)

    def _validate_sop_steps(self, steps: List[SOPStep]) -> List[SOPStep]:
        """Validate SOP steps and ensure file existence for patches."""
        validated_steps = []
        for step in steps:
            if step.action_type == "CODE_PATCH":
                if not self.verify_file_exists(step.file_path):
                    # If the file doesn't exist, we cannot recommend a CODE_PATCH.
                    # We downgrade it to a MEASUREMENT or a generic instruction.
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
        Your task is to analyze kernel logs (dmesg, logcat, kernel_trace) and identify root causes for panics, hangs, or other anomalies.

        You have access to the full kernel source tree via Vertex AI Context Caching. Use this context to pinpoint exact code locations.

        Guidelines:
        - Parse the provided logs carefully, looking for patterns like 'BUG: kernel NULL pointer dereference', 'watchdog:', 'Kernel panic', 'Oops:', 'Call trace:', etc.
        - If you identify a software bug, provide a detailed diagnosis and a recommended fix.
        - If a code patch is suggested, ensure you provide the correct file path.
        - Your output MUST be a valid JSON object matching the ConsultantResponse schema.

        ConsultantResponse Schema:
        {
          "diagnosis_id": "Unique ID (e.g., RCA-BSP-XXX)",
          "confidence_score": 0.0 to 1.0,
          "status": "CRITICAL" | "WARNING" | "INFO",
          "root_cause_summary": "Brief summary of the root cause",
          "evidence": ["Key log lines indicating the failure"],
          "sop_steps": [
            {
              "step_id": 1,
              "action_type": "MEASUREMENT" | "CODE_PATCH",
              "instruction": "Detailed instruction for the human",
              "expected_value": "Expected outcome of the step",
              "file_path": "Relevant file path or 'N/A'"
            }
          ]
        }
        """

        prompt = f"""
        {system_prompt}

        Analyze the following log content:
        {log_content}

        Return ONLY the JSON response.
        """

        response = self.llm.invoke(prompt)

        # Extract JSON from the response content
        json_match = re.search(r'\{.*\}', response.content, re.DOTALL)
        if not json_match:
            # Fallback for poorly formatted responses
            raise ValueError(f"Could not find valid JSON in LLM response: {response.content}")

        try:
            data = json.loads(json_match.group(0))
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse LLM response as JSON: {str(e)}")

        # Create the response object
        diagnosis = ConsultantResponse(**data)

        # Post-process and validate SOP steps using the required tool
        diagnosis.sop_steps = self._validate_sop_steps(diagnosis.sop_steps)

        return diagnosis
