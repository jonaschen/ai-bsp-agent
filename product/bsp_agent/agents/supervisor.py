import re
from langchain_google_vertexai import ChatVertexAI
from product.bsp_agent.core.state import AgentState

class SupervisorAgent:
    def __init__(self, model_name: str = "gemini-1.5-pro", chunk_threshold_mb: int = 50):
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

        if not log_content or not self.validate_input(log_content):
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

    async def run(self, state: AgentState) -> AgentState:
        """
        Main loop for the Supervisor Agent (Agent A).
        Handles user chat and case files, performing triage and routing.
        """
        messages = state.get("messages", [])
        if not messages:
            return state

        last_message = messages[-1]
        if isinstance(last_message, tuple):
            role, content = last_message
        else:
            role, content = "user", last_message

        # Triage Logic: Is this a log or a chat?
        if self.validate_input(content):
            # Input is a log file
            processed_log = self.chunk_log(content)
            state["current_log_chunk"] = processed_log

            # Use SecureSandbox for initial triage (demonstrates secure processing)
            specialist = self.secure_triage(processed_log)

            # If secure triage is unsure, use LLM for deeper routing
            if specialist == "clarify_needed":
                specialist = self.route(state)

            if specialist == "clarify_needed":
                response_text = "Log received, but I'm unable to determine the cause. Could you provide more context or a different log section?"
            else:
                response_text = f"Log received and validated. I've routed this case to the {specialist.replace('_', ' ').title()} specialist."

            state["messages"].append(("assistant", response_text))
        else:
            # Input is a chat message
            prompt = f"""
            You are the Supervisor Agent (Agent A) for the Android BSP Consultant squad.
            Your role is to triage user inputs and logs.

            User said: {content}

            If they are asking for help without providing a log, ask them to upload a dmesg or kernel log.
            If they are greeting you, respond politely and explain your role.
            """
            response = self.llm.invoke(prompt)
            state["messages"].append(("assistant", response.content))

        return state

    def secure_triage(self, log_content: str) -> str:
        """
        Process logs in a SecureSandbox for privacy and isolation.
        This demonstrates the implementation of secure log processing.
        """
        from studio.utils.sandbox import SecureSandbox

        # Initialize the secure environment
        sandbox = SecureSandbox()

        try:
            # Inject the log into the isolated workspace
            sandbox.setup_workspace({"kernel.log": log_content})

            # Run a basic analysis command in the sandbox
            # In production, this would be a more complex analyzer script
            result = sandbox.run_command("grep -Ei 'panic|null pointer|oops' kernel.log")

            if result.exit_code == 0:
                return "kernel_pathologist"

            result = sandbox.run_command("grep -Ei 'watchdog|timeout|hang' kernel.log")
            if result.exit_code == 0:
                return "hardware_advisor"

            return "clarify_needed"

        except Exception as e:
            # Fallback if Docker is unavailable
            return "clarify_needed"
        finally:
            # Ensure the sandbox is destroyed
            try:
                sandbox.teardown()
            except:
                pass
