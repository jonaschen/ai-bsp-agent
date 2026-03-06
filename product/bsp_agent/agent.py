"""
BSP Diagnostic Agent — The Brain.

Runs an Anthropic Claude tool-use loop over the registered skills
and produces a structured ConsultantResponse.

The Brain never does math or parses hex/memory values directly;
it delegates those tasks to skills via tool_use.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import anthropic

from product.schemas import CaseFile, ConsultantResponse, SOPStep
from skills.registry import TOOL_DEFINITIONS, dispatch_tool

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an Android BSP (Board Support Package) Diagnostic Expert.
Your role is to analyze kernel logs and hardware diagnostic data to produce
accurate Root Cause Analyses (RCAs) for Android/Linux BSP engineers.

Rules:
- NEVER guess or estimate memory values, thresholds, or hardware states.
- ALWAYS use the provided tools to extract deterministic facts from logs.
- After tool results are available, synthesize a final diagnosis.

Your final response MUST be a single JSON object matching this exact schema:
{
  "diagnosis_id": "<string, e.g. RCA-STD-001>",
  "confidence_score": <float 0.0-1.0>,
  "status": "<CRITICAL | WARNING | INFO | CLARIFY_NEEDED>",
  "root_cause_summary": "<one-sentence summary>",
  "evidence": ["<log line or fact 1>", ...],
  "sop_steps": [
    {
      "step_id": <int>,
      "action_type": "<MEASUREMENT | CODE_PATCH>",
      "instruction": "<detailed instruction>",
      "expected_value": "<expected outcome>",
      "file_path": "<file path or N/A>"
    }
  ]
}
Return ONLY the JSON object. No markdown fences, no surrounding text.
"""


class BSPDiagnosticAgent:
    """
    Diagnostic agent that uses Claude with tool_use to analyse a CaseFile
    and return a structured ConsultantResponse.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 4096,
        max_tool_rounds: int = 5,
        client: Optional[anthropic.Anthropic] = None,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.max_tool_rounds = max_tool_rounds
        self._client = client or anthropic.Anthropic()

    def run(self, case: CaseFile) -> ConsultantResponse:
        """
        Analyse the CaseFile, invoke skills as needed, and return a ConsultantResponse.

        Args:
            case: The input CaseFile containing user query and log payload.

        Returns:
            A validated ConsultantResponse.
        """
        messages = [{"role": "user", "content": self._build_user_message(case)}]

        for round_num in range(self.max_tool_rounds):
            response = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=_SYSTEM_PROMPT,
                tools=TOOL_DEFINITIONS,
                messages=messages,
            )
            logger.debug("Round %d stop_reason=%s", round_num, response.stop_reason)

            if response.stop_reason == "end_turn":
                return self._parse_final_response(response, case)

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                tool_results = self._execute_tool_calls(response.content)
                messages.append({"role": "user", "content": tool_results})
                continue

            # Unexpected stop reason — surface a clarify response
            logger.warning("Unexpected stop_reason: %s", response.stop_reason)
            break

        return _clarify_response(case.case_id, "Agent exceeded max tool rounds or got unexpected stop reason.")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_user_message(self, case: CaseFile) -> str:
        return (
            f"Case ID: {case.case_id}\n"
            f"Device: {case.device_model}\n"
            f"User Query: {case.user_query}\n\n"
            f"--- dmesg ---\n{case.log_payload.dmesg_content}\n\n"
            f"--- meminfo ---\n{case.log_payload.logcat_content}\n"
        )

    def _execute_tool_calls(self, content_blocks: list) -> list[dict]:
        """Execute all tool_use blocks and return a list of tool_result content items."""
        results = []
        for block in content_blocks:
            if block.type != "tool_use":
                continue
            try:
                output = dispatch_tool(block.name, block.input)
                content = json.dumps(output)
            except Exception as exc:
                logger.error("Tool %s failed: %s", block.name, exc)
                content = json.dumps({"error": str(exc)})
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": content,
            })
        return results

    def _parse_final_response(self, response, case: CaseFile) -> ConsultantResponse:
        """Extract and validate the JSON ConsultantResponse from the final LLM turn."""
        for block in response.content:
            if block.type == "text":
                raw = block.text.strip()
                # Strip accidental markdown fences
                if raw.startswith("```"):
                    raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                try:
                    data = json.loads(raw)
                    return ConsultantResponse(**data)
                except Exception as exc:
                    logger.error("Failed to parse ConsultantResponse: %s\nRaw: %s", exc, raw)
                    break

        return _clarify_response(case.case_id, "Agent returned an unparseable response.")


def _clarify_response(case_id: str, reason: str) -> ConsultantResponse:
    return ConsultantResponse(
        diagnosis_id=f"CLARIFY-{case_id}",
        confidence_score=0.0,
        status="CLARIFY_NEEDED",
        root_cause_summary=reason,
        evidence=[],
        sop_steps=[
            SOPStep(
                step_id=1,
                action_type="MEASUREMENT",
                instruction="Please provide a complete dmesg and /proc/meminfo captured at the time of failure.",
                expected_value="Sufficient log context to identify root cause.",
                file_path="N/A",
            )
        ],
    )
