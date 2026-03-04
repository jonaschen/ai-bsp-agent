import re
from langchain_google_vertexai import ChatVertexAI

# Pre-compiled patterns for performance (ref: Memory)
LOG_TS_PATTERN = re.compile(r"\[\s*(\d+\.\d+)\]")
FAILURE_PATTERN = re.compile(
    r"(?:NULL pointer dereference|soft lockup|hard lockup|Kernel panic|Oops:|BUG:|Watchdog detected hard lockup)",
    re.IGNORECASE
)

class SupervisorAgent:
    def __init__(self, model_name: str = "gemini-1.5-pro"):
        self.llm = ChatVertexAI(model_name=model_name)
        # Use a lower line threshold for concentrated segment requirement
        self.line_limit = 500

    def validate_input(self, text: str) -> bool:
        """Check if input is valid (e.g., is it a log?)."""
        # A simple heuristic: search for kernel timestamp pattern [ 1234.567890]
        if LOG_TS_PATTERN.search(text):
            return True
        return False

    def chunk_log(self, text: str) -> str:
        """
        Extract a concentrated segment of < 500 lines from raw logs.
        Uses keyword-analysis to find the 'Event Horizon' of the crash.
        """
        lines = text.splitlines()
        if len(lines) < self.line_limit:
            return text

        # Find all lines with failure patterns
        failure_indices = [i for i, line in enumerate(lines) if FAILURE_PATTERN.search(line)]

        if failure_indices:
            # Focus on the last failure event (the most likely terminal one)
            target_idx = failure_indices[-1]

            # Extract window: 400 lines before, 99 lines after (total 500)
            start_idx = max(0, target_idx - 400)
            end_idx = min(len(lines), target_idx + 100)

            # Ensure we don't exceed the limit strictly
            segment = lines[start_idx:end_idx]
            if len(segment) >= self.line_limit:
                segment = segment[:self.line_limit - 1]

            return "\n".join(segment)

        # Fallback: Extract last 499 lines if no failure pattern found
        return "\n".join(lines[-(self.line_limit - 1):])

    def route(self, state: dict) -> str:
        """Route the case to the Specialist or return CLARIFY_NEEDED."""
        log_content = state.get("current_log_chunk", "")

        if not self.validate_input(log_content):
            return "clarify_needed"

        # Pass the whole chunk to the LLM (Gemini 1.5 Pro handles this easily)
        prompt = f"""
        You are a BSP Supervisor Agent. Triage the following Android kernel log and decide the next specialist to route to.
        - If it's a software panic, null pointer dereference, or kernel oops, route to 'kernel_pathologist'.
        - If it's a hardware hang, watchdog timeout, or power management issue during sleep/resume, route to 'hardware_advisor'.
        - If it's not enough information, return 'clarify_needed'.

        Log content:
        {log_content}

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
