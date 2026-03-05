import re
from langchain_google_vertexai import ChatVertexAI
from product.bsp_agent.core.state import AgentState

# Pre-compiled patterns for optimization
LOG_TS_PATTERN = re.compile(r"\[\s*(\d+\.\d+)\]")
FAILURE_PATTERN = re.compile(
    r"(?:NULL pointer dereference|soft lockup|hard lockup|Kernel panic|Oops:|BUG:|Call trace:|Watchdog detected hard lockup)",
    re.IGNORECASE
)

class SupervisorAgent:
    def __init__(self, model_name: str = "gemini-2.5-pro", chunk_threshold_mb: int = 50):
        self.llm = ChatVertexAI(model_name=model_name)
        self.chunk_threshold = chunk_threshold_mb * 1024 * 1024

    def validate_input(self, text: str) -> bool:
        """Check if input is valid (e.g., is it a log?)."""
        # A simple heuristic: search for kernel timestamp pattern [ 1234.567890]
        if LOG_TS_PATTERN.search(text):
            return True
        return False

    def chunk_log(self, text: str) -> str:
        """
        Extract a concentrated segment of < 500 lines.
        Algorithm:
        1. Search for failure keywords (FAILURE_PATTERN).
        2. If found, identify the LAST occurrence.
        3. Return 400 lines before and ~100 lines after (total < 500).
        4. Fallback to last 499 lines if no pattern found.
        """
        lines = text.splitlines()

        # Find all matches for failure patterns
        matches = list(FAILURE_PATTERN.finditer(text))

        if matches:
            # Get the last match
            last_match = matches[-1]
            # Find which line it belongs to
            pre_text = text[:last_match.start()]
            target_line_idx = pre_text.count('\n')

            start_idx = max(0, target_line_idx - 400)
            end_idx = min(len(lines), target_line_idx + 100)

            # Ensure total lines < 500
            if end_idx - start_idx >= 500:
                end_idx = start_idx + 499

            return "\n".join(lines[start_idx:end_idx])

        # Fallback to last 499 lines
        if len(lines) > 499:
            return "\n".join(lines[-499:])
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
        - If it's a healthy boot or not enough information, return 'clarify_needed'.

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
