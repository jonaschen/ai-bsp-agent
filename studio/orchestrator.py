"""
studio/orchestrator.py
----------------------
The Runtime Executive of the Recursive Cognitive Software Factory.
Implements the "Centralized Architecture" to suppress Error Amplification (4.4x vs 17.2x).

Key Features:
1. Hierarchical State Machine (Supergraph -> Subgraphs).
2. Context Slicing (Data Isolation via transform_state).
3. Circuit Breaker (Semantic Entropy Monitoring).

Ref: [cite: 2018, 2029]
"""

import logging
import asyncio
from typing import Dict, Any, Literal, TypedDict, Annotated, Optional
from datetime import datetime
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode

# Import the Strict Schemas (Pydantic) from memory.py
from studio.memory import (
    StudioState,
    OrchestrationState,
    ContextSlice,
    SOPState,
    SemanticHealthMetric,
    AgentStepOutput,
    TriageStatus
)
from studio.utils.entropy_math import SemanticEntropyCalculator, VertexFlashJudge
from vertexai.generative_models import GenerativeModel
from studio.subgraphs.engineer import build_engineer_subgraph
from langchain_core.messages import HumanMessage
from studio.memory import JulesMetadata, VerificationGate

# --- MOCK SUBGRAPHS (Placeholders for compilation) ---
def engineer_subgraph_node(state: ContextSlice) -> Dict:
    """Mock execution of the Engineer Subgraph"""
    # Returns a dict matching AgentStepOutput schema
    return {
        "content": "Patch applied.",
        "thought_process": "Analyzed dependencies and applied fix.",
        "cognitive_health": {
            "entropy_score": 0.5,
            "threshold": 7.0,
            "sample_size": 5,
            "is_tunneling": False,
            "cluster_distribution": {}
        }
    }

def sop_guide_node(state: SOPState) -> Dict:
    """Mock execution of the Interactive SOP Guide"""
    return {"current_step_index": state.current_step_index + 1}

def reflector_node(state: StudioState) -> Dict:
    """Mock Reflection Node for Circuit Breaker"""
    return {"circuit_breaker_triggered": True}

# --- THE ORCHESTRATOR CLASS ---

class Orchestrator:
    def __init__(self, engineer_app=None):
        self.logger = logging.getLogger("Orchestrator")

        # Initialize the Semantic Sensor
        self.judge = VertexFlashJudge(GenerativeModel("gemini-1.5-flash"))
        self.calculator = SemanticEntropyCalculator(self.judge)

        # Initialize the Worker Subgraphs
        self.engineer_app = engineer_app or build_engineer_subgraph()

        # Initialize the Supergraph with the Global StudioState
        self.workflow = StateGraph(StudioState)
        self._setup_graph()

    def _setup_graph(self):
        """
        Defines the System Topology (Nodes & Edges).
        Ref:
        """
        # Wrappers for Context Slicing & State Transformation
        async def _engineer_wrapper(state: StudioState) -> Dict:
            """Wraps engineer subgraph to handle Context Slicing"""
            slice_obj = state.orchestration.current_context_slice
            if not slice_obj:
                # Fallback if no slice
                slice_obj = ContextSlice(
                    slice_id="fallback", intent="CODING",
                    active_files={}, relevant_logs="", constraints=[]
                )

            # 1. Prepare AgentState for the Subgraph
            agent_state = {
                "messages": [HumanMessage(content=state.engineering.current_task or "Fix the bug")],
                "system_constitution": "ENFORCE SOLID.",
                "jules_metadata": state.engineering.jules_meta or JulesMetadata(session_id=state.orchestration.session_id),
                "next_agent": None
            }

            # 2. Invoke the REAL Engineer Subgraph
            self.logger.info("Invoking Engineer Subgraph...")
            result = await self.engineer_app.ainvoke(agent_state)

            # 3. Process results
            jules_meta = result["jules_metadata"]
            updates = {}

            proposed_patch = None
            if jules_meta.generated_artifacts:
                proposed_patch = jules_meta.generated_artifacts[0].diff_content

            # Update Verification Gate based on status
            gate_status = "PENDING"
            if jules_meta.status == "COMPLETED":
                gate_status = "GREEN"
            elif jules_meta.status == "FAILED":
                gate_status = "RED"
                updates["escalation_triggered"] = True

            # 4. Enforce Semantic Entropy Guardrail
            # Real implementation using the actual calculator
            metric = await self.calculator.measure_uncertainty(slice_obj.intent, slice_obj.intent)

            # Parse output into AgentStepOutput
            # Use the actual content from the subgraph if available
            agent_output = AgentStepOutput(
                content=proposed_patch or "No patch generated",
                thought_process="Subgraph execution complete.",
                cognitive_health=metric
            )

            # Map output back to StudioState
            if hasattr(state.engineering, "model_copy"):
                eng_update = state.engineering.model_copy(update={
                    "proposed_patch": agent_output.content,
                    "jules_meta": jules_meta,
                    "verification_gate": VerificationGate(status=gate_status)
                })
            else:
                eng_update = state.engineering.copy(update={
                    "proposed_patch": agent_output.content,
                    "jules_meta": jules_meta,
                    "verification_gate": VerificationGate(status=gate_status)
                })

            updates["engineering"] = eng_update

            # Circuit Breaker Logic
            if metric.is_tunneling:
                self.logger.critical(f"Cognitive Tunneling Detected (SE={metric.entropy_score})! Triggering Circuit Breaker.")
                updates["circuit_breaker_triggered"] = True

            return updates

        def _sop_guide_wrapper(state: StudioState) -> Dict:
            """Wraps SOP guide to handle state isolation"""
            sop_state = state.orchestration.guidance_sop
            if not sop_state:
                sop_state = SOPState()

            output = sop_guide_node(sop_state)

            # Update SOP State
            if hasattr(sop_state, "model_copy"):
                new_sop = sop_state.model_copy(update=output)
                orch_update = state.orchestration.model_copy(update={"guidance_sop": new_sop})
            else:
                new_sop = sop_state.copy(update=output)
                orch_update = state.orchestration.copy(update={"guidance_sop": new_sop})

            return {"orchestration": orch_update}

        # 1. Define Nodes
        self.workflow.add_node("intent_router", self.route_intent)
        self.workflow.add_node("context_slicer", self.slice_context)

        # 2. Define Subgraph Nodes (The Workers)
        self.workflow.add_node("engineer_subgraph", _engineer_wrapper)
        self.workflow.add_node("sop_guide_subgraph", _sop_guide_wrapper)

        # 3. Define Governance Nodes
        self.workflow.add_node("reflector", reflector_node) # Circuit Breaker Target

        # 4. Define Edges (The Control Flow)
        self.workflow.add_edge(START, "intent_router")

        # Conditional Routing based on User Intent
        self.workflow.add_conditional_edges(
            "intent_router",
            self._decide_route,
            {
                "coding": "context_slicer",       # Needs slicing before Engineering
                "interactive_guide": "sop_guide_subgraph", # Direct SOP execution
                "block": END
            }
        )

        # The Slicing Edge: Orchestrator -> Engineer
        self.workflow.add_edge("context_slicer", "engineer_subgraph")

        # Circuit Breaker Logic (Post-Execution Check)
        self.workflow.add_conditional_edges(
            "engineer_subgraph",
            self._check_semantic_health,
            {
                "healthy": END,       # Or loop back
                "tunneling": "reflector" # Hard Stop
            }
        )

        # Reflector ends or loops back (here just END for simplicity)
        self.workflow.add_edge("reflector", END)
        self.workflow.add_edge("sop_guide_subgraph", END)

        self.app = self.workflow.compile()

    # --- NODE: Intent Router ---
    def route_intent(self, state: StudioState) -> Dict:
        """
        Decides the 'Intent' based on Triage Status.
        Handles the 'No-Log' Scenario via SOP Pattern.
        Ref: [cite: 2143]
        """
        orch = state.orchestration

        # Check for No-Log Scenario (The Consultant Pivot)
        if orch.triage_status and not orch.triage_status.is_log_available:
            self.logger.info("No Log detected. Routing to SOP Guide.")

            new_sop = orch.guidance_sop or SOPState(active_sop_id="NO_LOG_DEBUG")

            if hasattr(orch, "model_copy"):
                 updated_orch = orch.model_copy(update={
                    "user_intent": "INTERACTIVE_GUIDE",
                    "guidance_sop": new_sop
                })
            else:
                updated_orch = orch.copy(update={
                    "user_intent": "INTERACTIVE_GUIDE",
                    "guidance_sop": new_sop
                })
            return {"orchestration": updated_orch}

        # Default to Coding/Analysis
        if hasattr(orch, "model_copy"):
            updated_orch = orch.model_copy(update={"user_intent": "CODING"})
        else:
            updated_orch = orch.copy(update={"user_intent": "CODING"})
        return {"orchestration": updated_orch}

    # --- NODE: Context Slicer ---
    def slice_context(self, state: StudioState) -> Dict:
        """
        Implements Context Slicing.
        Physically isolates the Engineer from global noise.
        Ref: [cite: 2066, 2074]
        """
        intent = state.orchestration.user_intent

        # In a real app, we would query a VectorDB here for relevant files.
        # For now, we mock the slicing logic.
        relevant_files = {"drivers/gpu/msm/mdss.c": "void main() { ... }"}

        # Create the Ephemeral Slice
        new_slice = ContextSlice(
            slice_id="slice_" + datetime.now().isoformat(),
            intent=intent if intent in ["DIAGNOSIS", "CODING", "REVIEW"] else "CODING",
            active_files=relevant_files,
            relevant_logs="[1456.789] Panic at...", # Mock sliced log
            constraints=["DO NOT modify outside of drivers/"]
        )

        # We update the 'current_context_slice' in the global state
        if hasattr(state.orchestration, "model_copy"):
            updated_orch = state.orchestration.model_copy(update={"current_context_slice": new_slice})
        else:
            updated_orch = state.orchestration.copy(update={"current_context_slice": new_slice})
        return {"orchestration": updated_orch}

    # --- CONDITIONAL: Circuit Breaker (Semantic Entropy) ---
    def _check_semantic_health(self, state: StudioState) -> Literal["healthy", "tunneling"]:
        """
        The Mathematical Guardrail.
        Checks if circuit breaker was triggered by last agent output.
        Ref: [cite: 2121, 2134]
        """
        if state.circuit_breaker_triggered:
            return "tunneling"
        return "healthy"

    def _decide_route(self, state: StudioState) -> str:
        intent = state.orchestration.user_intent
        if intent == "INTERACTIVE_GUIDE": return "interactive_guide"
        if intent == "CODING": return "coding"
        return "block"
