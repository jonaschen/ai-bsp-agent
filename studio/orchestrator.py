"""
studio/orchestrator.py
----------------------
Implements the Runtime State Machine and Circuit Breaker logic.
Ref: "Engineering Resilient Cognitive Architectures" (Report 588)
"""

from typing import Optional
from studio.memory import (
    StudioState, AgentStepOutput, SemanticHealthMetric,
    ContextSlice, TriageStatus
)

class Orchestrator:
    """
    The Runtime Controller.
    Manages state transitions, routing, and cognitive health checks.
    """

    def __init__(self, state: StudioState):
        self.state = state
        self.entropy_threshold = 7.0

    def ingest_agent_output(self, output: AgentStepOutput):
        """
        Updates the state based on agent output and triggers circuit breakers.
        """
        # 1. Update Cognitive Health
        if output.cognitive_health:
            self._evaluate_health(output.cognitive_health)

        # 2. Halt if Circuit Breaker is triggered
        if self.state.circuit_breaker_triggered:
            raise RuntimeError("Circuit Breaker Triggered: Semantic Entropy exceeded threshold.")

    def _evaluate_health(self, metric: SemanticHealthMetric):
        """
        Ref: [cite: 722] - Semantic Entropy Monitoring
        """
        # Use metric's own threshold if defined, else system default
        threshold = metric.threshold if metric.threshold else self.entropy_threshold

        if metric.entropy_score > threshold:
            metric.is_tunneling = True
            self.state.circuit_breaker_triggered = True
            print(f"🚨 CIRCUIT BREAKER TRIGGERED: Entropy {metric.entropy_score} > {threshold}")

    def route_request(self, user_request: str) -> str:
        """
        Determines the next agent based on intent and system state.
        """
        if self.state.circuit_breaker_triggered:
            return "HumanIntervention"

        request_lower = user_request.lower()

        # Simple keyword-based routing (placeholder for more complex logic)
        if "plan" in request_lower or "strategy" in request_lower:
            self.state.orchestration.user_intent = "PLANNING"
            return "ProductManager"
        elif "fix" in request_lower or "bug" in request_lower:
             self.state.orchestration.user_intent = "DIAGNOSIS"
             return "Architect"
        elif "review" in request_lower:
             self.state.orchestration.user_intent = "REVIEW"
             return "ReviewAgent"
        else:
             self.state.orchestration.user_intent = "UNKNOWN"
             return "Architect" # Default fallback

    def generate_context_slice(self, role: str) -> ContextSlice:
        """
        Generates a role-specific view of the state (Context Slicing).
        """
        # This would implementation logic referenced in memory.py
        # For now, returning a basic slice
        intent = "CODING"
        if role == "ReviewAgent":
            intent = "REVIEW"
        elif role == "ProductManager":
            intent = "DIAGNOSIS" # Or similar

        return ContextSlice(
            slice_id=f"{role}-slice-{self.state.orchestration.session_id}",
            intent=intent,
            active_files={},
            relevant_logs="",
            constraints=["Follow TDD", "Update Memory"]
        )
