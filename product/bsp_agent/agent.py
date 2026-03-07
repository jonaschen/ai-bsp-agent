"""
BSP Diagnostic Agent — The Brain.

Runs an Anthropic Claude tool-use loop over the registered skills
and produces a structured ConsultantResponse.

Flow:
  1. SupervisorAgent triages the dmesg → routes to 'hardware_advisor' or 'kernel_pathologist'
  2. BSPDiagnosticAgent runs a tool-use loop with route-appropriate skills
  3. Returns a validated ConsultantResponse

The Brain never does math or parses hex/memory values directly;
it delegates those tasks to skills via tool_use.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import anthropic

from product.bsp_agent.agents.supervisor import SupervisorAgent
from product.bsp_agent.core.state import AgentState
from product.schemas import CaseFile, ConsultantResponse, SOPStep
from skills.registry import TOOL_DEFINITIONS, ROUTE_TOOLS, dispatch_tool

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

_SPECIALIST_LABELS = {
    "hardware_advisor": "Hardware Advisor (power management / STD / suspend-resume failures)",
    "kernel_pathologist": "Kernel Pathologist (AArch64 exceptions / kernel panics / oops)",
}


def _tools_for_route(route: str) -> list[dict]:
    """Return the Anthropic tool definitions relevant to the given supervisor route."""
    names = ROUTE_TOOLS.get(route)
    if not names:
        return TOOL_DEFINITIONS  # fallback: offer all tools
    filtered = [t for t in TOOL_DEFINITIONS if t["name"] in names]
    return filtered if filtered else TOOL_DEFINITIONS


class BSPDiagnosticAgent:
    """
    Diagnostic agent that uses Claude with tool_use to analyse a CaseFile
    and return a structured ConsultantResponse.

    The SupervisorAgent triages the case first; BSPDiagnosticAgent then
    runs the tool-use loop with route-appropriate skills.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 4096,
        max_tool_rounds: int = 5,
        client: Optional[anthropic.Anthropic] = None,
        supervisor: Optional[SupervisorAgent] = None,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.max_tool_rounds = max_tool_rounds
        self._client = client or anthropic.Anthropic()
        self._supervisor = supervisor or SupervisorAgent(client=self._client)

    def run(self, case: CaseFile) -> ConsultantResponse:
        """
        Analyse the CaseFile, invoke skills as needed, and return a ConsultantResponse.

        Args:
            case: The input CaseFile containing user query and log payload.

        Returns:
            A validated ConsultantResponse.
        """
        # Step 1: Supervisor triage
        log_chunk = self._supervisor.chunk_log(case.log_payload.dmesg_content)
        state: AgentState = {
            "messages": [],
            "current_log_chunk": log_chunk,
            "diagnosis_report": None,
        }
        route = self._supervisor.route(state)
        logger.debug("Supervisor routed to: %s", route)

        if route == "clarify_needed":
            return _clarify_response(
                case.case_id,
                "Supervisor could not identify the failure domain. "
                "Please provide a more complete kernel log.",
            )

        # Step 2: Tool-use loop with route-appropriate tools
        tools = _tools_for_route(route)
        messages = [{"role": "user", "content": self._build_user_message(case, route)}]

        for round_num in range(self.max_tool_rounds):
            response = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=_SYSTEM_PROMPT,
                tools=tools,
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

            logger.warning("Unexpected stop_reason: %s", response.stop_reason)
            break

        return _clarify_response(
            case.case_id,
            "Agent exceeded max tool rounds or received an unexpected stop reason.",
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_user_message(self, case: CaseFile, route: str) -> str:
        specialist = _SPECIALIST_LABELS.get(route, "BSP Expert")
        parts = [
            f"Case ID: {case.case_id}",
            f"Device: {case.device_model}",
            f"Specialist: {specialist}",
            f"User Query: {case.user_query}",
            "",
            "--- dmesg ---",
            case.log_payload.dmesg_content,
        ]
        if case.log_payload.meminfo_content:
            parts += ["", "--- /proc/meminfo ---", case.log_payload.meminfo_content]
        if case.log_payload.logcat_content:
            parts += ["", "--- logcat ---", case.log_payload.logcat_content]
        return "\n".join(parts)

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
                instruction=(
                    "Please provide a complete dmesg and /proc/meminfo "
                    "captured at the time of failure."
                ),
                expected_value="Sufficient log context to identify root cause.",
                file_path="N/A",
            )
        ],
    )
