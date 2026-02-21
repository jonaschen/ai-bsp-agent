import re
from langchain_google_vertexai import ChatVertexAI
from product.bsp_agent.core.state import AgentState

class SupervisorAgent:
    def __init__(self, model_name: str = "gemini-2.5-pro", chunk_threshold_mb: int = 50):
        self.llm = ChatVertexAI(model_name=model_name)
        self.chunk_threshold = chunk_threshold_mb * 1024 * 1024

    def validate_input(self, text: str) -> bool:
        """Check if input is valid (e.g., is it a log?)."""
        # A simple heuristic: search for kernel timestamp pattern [ 1234.567890]
        if re.search(r"\[\s*\d+\.\d+\]", text):
            return True
        return False

    def chunk_log(self, text: str) -> str:
        """If Log Size > threshold, extract the 'Event Horizon' (last 5000 lines OR ±10s window)."""
        if len(text) <= self.chunk_threshold:
            return text

        lines = text.splitlines()

        # Look for failure timestamp
        failure_pattern = r"\[\s*(\d+\.\d+)\]\s+.*(?:NULL pointer dereference|soft lockup|hard lockup|Kernel panic|Oops:)"
        match = re.search(failure_pattern, text, re.IGNORECASE)

        if match:
            failure_ts = float(match.group(1))
            start_ts = failure_ts - 10
            end_ts = failure_ts + 10

            event_horizon = []
            for line in lines:
                ts_match = re.search(r"\[\s*(\d+\.\d+)\]", line)
                if ts_match:
                    ts = float(ts_match.group(1))
                    if start_ts <= ts <= end_ts:
                        event_horizon.append(line)

            if event_horizon:
                return "\n".join(event_horizon)

        # Fallback to last 5000 lines
        if len(lines) > 5000:
            return "\n".join(lines[-5000:])
        return text

    def route(self, state: AgentState) -> str:
        """Route the case to the Specialist or return CLARIFY_NEEDED."""
        log_content = state.get("current_log_chunk", "")

        if not self.validate_input(log_content):
            return "clarify_needed"

        prompt = f"""
        You are a BSP Supervisor Agent. Triage the following Android kernel log and decide the next specialist to route to.
        - If it's a software panic, null pointer dereference, or kernel oops, route to 'kernel_pathologist'.
        - If it's a hardware hang, watchdog timeout, or power management issue during sleep/resume, route to 'hardware_advisor'.
        - If it's not enough information, return 'clarify_needed'.

        Log content:
        {log_content[:2000]}

        Return ONLY the name of the specialist: 'kernel_pathologist', 'hardware_advisor', or 'clarify_needed'.
        """

        response = self.llm.invoke(prompt)
        decision = response.content.strip().lower()

        if "kernel_pathologist" in decision:
            return "kernel_pathologist"
        elif "hardware_advisor" in decision:
            return "hardware_advisor"
        else:
            return "clarify_needed"
