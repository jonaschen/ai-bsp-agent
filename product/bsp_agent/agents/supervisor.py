import re
from typing import Optional

import anthropic

from product.bsp_agent.core.state import AgentState

_TRIAGE_SYSTEM = (
    "You are a BSP Supervisor Agent. Triage Android kernel logs and decide "
    "which specialist to route to. Reply with EXACTLY one of these tokens: "
    "'kernel_pathologist', 'hardware_advisor', or 'clarify_needed'. "
    "No other text."
)

_TRIAGE_RULES = """\
- Software panic / null pointer dereference / kernel oops → kernel_pathologist
- Hardware hang / watchdog timeout / power management / suspend-resume failure → hardware_advisor
- Insufficient information → clarify_needed
"""


class SupervisorAgent:
    def __init__(
        self,
        model: str = "claude-haiku-4-5-20251001",
        chunk_threshold_mb: int = 50,
        client: Optional[anthropic.Anthropic] = None,
    ):
        self.model = model
        self.chunk_threshold = chunk_threshold_mb * 1024 * 1024
        self._client = client or anthropic.Anthropic()

    def validate_input(self, text: str) -> bool:
        """Check if input looks like a kernel log (has timestamp pattern)."""
        return bool(re.search(r"\[\s*\d+\.\d+\]", text))

    def chunk_log(self, text: str) -> str:
        """If log exceeds threshold, extract the Event Horizon (±10s around failure)."""
        if len(text) <= self.chunk_threshold:
            return text

        lines = text.splitlines()
        failure_pattern = (
            r"\[\s*(\d+\.\d+)\]\s+.*"
            r"(?:NULL pointer dereference|soft lockup|hard lockup|Kernel panic|Oops:)"
        )
        match = re.search(failure_pattern, text, re.IGNORECASE)

        if match:
            failure_ts = float(match.group(1))
            start_ts, end_ts = failure_ts - 10, failure_ts + 10
            event_horizon = [
                line for line in lines
                if (m := re.search(r"\[\s*(\d+\.\d+)\]", line))
                and start_ts <= float(m.group(1)) <= end_ts
            ]
            if event_horizon:
                return "\n".join(event_horizon)

        return "\n".join(lines[-5000:]) if len(lines) > 5000 else text

    def route(self, state: AgentState) -> str:
        """Route the case to the appropriate specialist."""
        log_content = state.get("current_log_chunk", "")

        if not self.validate_input(log_content):
            return "clarify_needed"

        response = self._client.messages.create(
            model=self.model,
            max_tokens=16,
            system=_TRIAGE_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Routing rules:\n{_TRIAGE_RULES}\n\n"
                        f"Log (first 2000 chars):\n{log_content[:2000]}"
                    ),
                }
            ],
        )

        decision = response.content[0].text.strip().lower()

        if "kernel_pathologist" in decision:
            return "kernel_pathologist"
        if "hardware_advisor" in decision:
            return "hardware_advisor"
        return "clarify_needed"
