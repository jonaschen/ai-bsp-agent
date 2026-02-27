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
from studio.memory import JulesMetadata, VerificationGate, EngineeringState
from studio.agents.product_owner import run_po_cycle
from studio.agents.scrum_master import run_scrum_retrospective
from studio.agents.optimizer import OptimizerAgent
from studio.utils.git_utils import sync_main_branch

# --- MOCK SUBGRAPHS (Placeholders for compilation) ---
def sop_guide_node(state: SOPState) -> Dict:
    """Mock execution of the Interactive SOP Guide"""
    return {"current_step_index": state.current_step_index + 1}

def reflector_node(state: StudioState) -> Dict:
    """Mock Reflection Node for Circuit Breaker"""
    return {"circuit_breaker_triggered": True}

# --- THE ORCHESTRATOR CLASS ---

class Orchestrator:
    def __init__(self, engineer_app=None, checkpointer=None, manager=None):
        self.logger = logging.getLogger("Orchestrator")
        self.manager = manager

        # Initialize the Semantic Sensor
        self.judge = VertexFlashJudge(GenerativeModel("gemini-2.5-pro"))
        self.calculator = SemanticEntropyCalculator(self.judge)

        # Initialize the Worker Subgraphs
        self.engineer_app = engineer_app or build_engineer_subgraph()

        # Initialize the Supergraph with the Global StudioState
        self.workflow = StateGraph(StudioState)
        self._setup_graph(checkpointer=checkpointer)

    def _setup_graph(self, checkpointer=None):
        """
        Defines the System Topology (Nodes & Edges).
        Implements the Phase 2 Lifecycle Manager while retaining Router capabilities.
        """
        # 1. Define Nodes
        self.workflow.add_node("intent_router", self.route_intent)
        self.workflow.add_node("product_owner", self.node_product_owner)
        self.workflow.add_node("sprint_planning", self.node_sprint_planning)
        self.workflow.add_node("backlog_dispatcher", self.node_backlog_dispatcher)
        self.workflow.add_node("context_slicer", self.slice_context)
        self.workflow.add_node("engineer_subgraph", self._engineer_wrapper)
        self.workflow.add_node("sop_guide_subgraph", self._sop_guide_wrapper)
        self.workflow.add_node("scrum_master", self.node_scrum_master)
        self.workflow.add_node("reflector", reflector_node)

        # 2. Define Edges (The Lifecycle Flow)
        self.workflow.add_edge(START, "intent_router")

        self.workflow.add_conditional_edges(
            "intent_router",
            self._decide_entry_route,
            {
                "plan": "product_owner",
                "execute": "sprint_planning",
                "interactive_guide": "sop_guide_subgraph",
                "block": END
            }
        )

        self.workflow.add_edge("product_owner", "sprint_planning")
        self.workflow.add_edge("sprint_planning", "backlog_dispatcher")

        # Loop over the backlog
        self.workflow.add_conditional_edges(
            "backlog_dispatcher",
            self._decide_loop_route,
            {
                "next": "context_slicer",
                "done": "scrum_master"
            }
        )

        self.workflow.add_edge("context_slicer", "engineer_subgraph")

        # Post-Execution Health Check & Loop Back
        self.workflow.add_conditional_edges(
            "engineer_subgraph",
            self._check_semantic_health,
            {
                "healthy": "backlog_dispatcher",
                "tunneling": "reflector",
                "retry": "engineer_subgraph"
            }
        )

        self.workflow.add_edge("reflector", END)
        self.workflow.add_edge("scrum_master", END)
        self.workflow.add_edge("sop_guide_subgraph", END)

        self.app = self.workflow.compile(checkpointer=checkpointer)

    # --- NODE: Product Owner (PLAN) ---
    async def node_product_owner(self, state: StudioState) -> Dict:
        self.logger.info("Orchestrator: Waking up Product Owner Agent...")
        # run_po_cycle analyzes PRODUCT_BLUEPRINT.md
        # Use model_dump for Pydantic V2 compatibility
        state_dict = state.model_dump() if hasattr(state, "model_dump") else state.dict()
        new_tickets = await asyncio.to_thread(run_po_cycle, state_dict)

        orch = state.orchestration
        # When planning a new sprint, we only populate the global task_queue.
        # node_sprint_planning will move them to the active backlog.
        updated_orch = orch.model_copy(update={
            "task_queue": orch.task_queue + new_tickets
        })
        return {"orchestration": updated_orch}

    # --- NODE: Sprint Planning ---
    async def node_sprint_planning(self, state: StudioState) -> Dict:
        """
        Safely moves a batch of up to 3 unblocked tickets from the global task_queue
        into the active sprint_backlog if it is empty.
        """
        self.logger.info("Orchestrator: Sprint Planning Node...")
        orch = state.orchestration.model_copy(deep=True)

        # If sprint_backlog already has active tasks, return unchanged.
        if orch.sprint_backlog:
            return {}

        # Pop up to 3 OPEN tickets from task_queue
        open_tickets = [t for t in orch.task_queue if t.status == "OPEN"]
        batch = open_tickets[:3]

        if batch:
            self.logger.info(f"Moving {len(batch)} tasks to sprint backlog.")
            # Remove batch from task_queue
            batch_ids = {t.id for t in batch}
            orch.task_queue = [t for t in orch.task_queue if t.id not in batch_ids]
            orch.sprint_backlog = batch
            orch.sprint_goal = f"Execute batch of {len(batch)} tasks."

            return {"orchestration": orch}

        return {}

    # --- NODE: Backlog Dispatcher (EXECUTE LOOP) ---
    async def node_backlog_dispatcher(self, state: StudioState) -> Dict:
        self.logger.info("Orchestrator: Dispatching next task from backlog...")
        # Use deep copy to avoid mutation issues in loops
        orch = state.orchestration.model_copy(deep=True)
        eng = state.engineering
        updated_tkt = None

        # 1. Process results from the previous execution
        if eng.current_task and eng.jules_meta:
            self.logger.info(f"Processing result for task: {eng.current_task}, status: {eng.jules_meta.status}")

            # Helper to update a list and return the updated ticket if found
            def update_and_filter(ticket_list):
                new_list = []
                found_ticket = None
                for t in ticket_list:
                    if t.id == eng.current_task or f"{t.title}: {t.description}" == eng.current_task:
                        if eng.jules_meta.status == "COMPLETED":
                            t.status = "COMPLETED"
                            found_ticket = t
                            continue # Remove from active list
                        elif eng.jules_meta.status == "FAILED":
                            t.status = "FAILED"
                            found_ticket = t
                            continue # Remove from active list
                    new_list.append(t)
                return new_list, found_ticket

            # Update both to keep them in sync
            orch.task_queue, updated_tkt_q = update_and_filter(orch.task_queue)
            orch.sprint_backlog, updated_tkt_s = update_and_filter(orch.sprint_backlog)

            updated_tkt = updated_tkt_s or updated_tkt_q
            if updated_tkt:
                if updated_tkt.status == "COMPLETED":
                    orch.completed_tasks_log.append(updated_tkt)
                    self.logger.info(f"Task {updated_tkt.id} completed. Synchronizing local workspace with main branch.")
                    await asyncio.to_thread(sync_main_branch)
                elif updated_tkt.status == "FAILED":
                    orch.failed_tasks_log.append(updated_tkt)
                    self.logger.info(f"Task {updated_tkt.id} failed.")

                # Critical Transition: Task Completion/Failure - Persist state to disk
                # Triggered only if status is terminal (COMPLETED or FAILED)
                if updated_tkt and updated_tkt.status in ["COMPLETED", "FAILED"] and self.manager:
                    self.manager.state = state.model_copy(update={"orchestration": orch})
                    self.manager._save_state()
                    self.logger.info(f"Explicit persistence triggered for task {updated_tkt.id} terminal status: {updated_tkt.status}.")

        # 2. Pick the next ticket that is OPEN or IN_PROGRESS from the SPRINT BACKLOG
        next_ticket = next((t for t in orch.sprint_backlog if t.status in ["OPEN", "IN_PROGRESS"]), None)

        if next_ticket:
            next_ticket.status = "IN_PROGRESS"

            # Mark as IN_PROGRESS in task_queue for consistency if present
            for t in orch.task_queue:
                if t.id == next_ticket.id:
                    t.status = "IN_PROGRESS"
            new_eng = EngineeringState(
                current_task=f"{next_ticket.title}: {next_ticket.description}",
                jules_meta=JulesMetadata(
                    session_id=orch.session_id,
                    max_retries=orch.task_max_retries
                )
            )
            return {
                "orchestration": orch,
                "engineering": new_eng
            }

        return {"orchestration": orch}

    # --- NODE: Scrum Master (REVIEW) ---
    async def node_scrum_master(self, state: StudioState) -> Dict:
        """
        Invokes the Scrum Master AND the Optimizer.
        """
        self.logger.info("Orchestrator: Sprint Complete. Engaging Scrum Master...")
        state_dict = state.model_dump() if hasattr(state, "model_dump") else state.dict()

        # 1. Generate Report
        report = await asyncio.to_thread(run_scrum_retrospective, state_dict)

        if report:
            # Handle cases where report might be a MagicMock in tests
            try:
                success_rate = report.success_rate
                success_rate_str = f"{success_rate:.2%}" if isinstance(success_rate, (float, int)) else str(success_rate)
            except Exception:
                success_rate_str = "unknown"

            self.logger.info(f"Orchestrator: Optimization Report Generated (Success: {success_rate_str}).")

            # 2. Engage Optimizer (The Phase 3 Addition)
            # Only optimize if there are actual optimizations and it's not a mock from a test
            optimizations = getattr(report, "optimizations", [])
            if optimizations and isinstance(optimizations, list):
                self.logger.info("Orchestrator: Engaging Optimizer to patch prompts...")
                optimizer = OptimizerAgent()
                # Run optimization in thread as it might involve LLM calls
                await asyncio.to_thread(optimizer.apply_optimizations, report)

        return {}

    # --- WRAPPER: SOP Guide ---
    def _sop_guide_wrapper(self, state: StudioState) -> Dict:
        """Wraps SOP guide to handle state isolation"""
        sop_state = state.orchestration.guidance_sop
        if not sop_state:
            sop_state = SOPState()

        output = sop_guide_node(sop_state)

        # Update SOP State
        new_sop = sop_state.model_copy(update=output)
        orch_update = state.orchestration.model_copy(update={"guidance_sop": new_sop})

        return {"orchestration": orch_update}

    # --- WRAPPER: Engineer Subgraph ---
    async def _engineer_wrapper(self, state: StudioState) -> Dict:
        """Wraps engineer subgraph to handle Context Slicing"""
        slice_obj = state.orchestration.current_context_slice
        if not slice_obj:
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
        # Note: The Engineer Subgraph already runs an entropy check on the generated patch.
        # This global check acts as a secondary safety layer on the 'Intent' consistency.
        # We use the task description as the prompt for the global check.
        metric = await self.calculator.measure_uncertainty(state.engineering.current_task or "Fix the bug", slice_obj.intent)

        # Map output back to StudioState
        eng_update = state.engineering.model_copy(update={
            "proposed_patch": proposed_patch or "No patch generated",
            "jules_meta": jules_meta,
            "verification_gate": VerificationGate(status=gate_status)
        })

        updates["engineering"] = eng_update

        # Circuit Breaker Logic
        if metric.is_tunneling:
            self.logger.critical(f"Cognitive Tunneling Detected (SE={metric.entropy_score})! Triggering Circuit Breaker.")
            updates["circuit_breaker_triggered"] = True

            # Critical Transition: Circuit Breaker Triggered - Persist state to disk
            if self.manager:
                self.manager.state = state.model_copy(update={
                    "engineering": eng_update,
                    "circuit_breaker_triggered": True
                })
                self.manager._save_state()
                self.logger.info("Explicit persistence triggered for Circuit Breaker.")

        return updates

    def _decide_loop_route(self, state: StudioState) -> str:
        """Determines if there are more tasks in the backlog."""
        # Check for tickets that are OPEN or currently IN_PROGRESS in the SPRINT BACKLOG
        active_ticket = next((t for t in state.orchestration.sprint_backlog if t.status in ["OPEN", "IN_PROGRESS"]), None)
        return "next" if active_ticket else "done"

    def _decide_entry_route(self, state: StudioState) -> str:
        """Determines the entry point based on user intent."""
        intent = state.orchestration.user_intent
        if intent == "SPRINT": return "plan"
        if intent == "CODING": return "execute"
        if intent == "INTERACTIVE_GUIDE": return "interactive_guide"
        return "block"

    # --- NODE: Intent Router ---
    def route_intent(self, state: StudioState) -> Dict:
        """
        Decides the 'Intent' based on Triage Status.
        Handles the 'No-Log' Scenario via SOP Pattern.
        Ref: [cite: 2143]
        """
        orch = state.orchestration

        # Preserve SPRINT intent if explicitly set
        if orch.user_intent == "SPRINT":
            return {"orchestration": orch}

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

        # Extract the 'Event Horizon' (last 500 lines) - Fix #3
        full_logs = state.orchestration.full_logs or ""
        log_lines = full_logs.splitlines()
        sliced_logs = "\n".join(log_lines[-500:]) if log_lines else ""

        # Create the Ephemeral Slice
        new_slice = ContextSlice(
            slice_id="slice_" + datetime.now().isoformat(),
            intent=intent if intent in ["DIAGNOSIS", "CODING", "REVIEW"] else "CODING",
            active_files=relevant_files,
            relevant_logs=sliced_logs,
            constraints=["DO NOT modify outside of drivers/"]
        )

        # We update the 'current_context_slice' in the global state
        if hasattr(state.orchestration, "model_copy"):
            updated_orch = state.orchestration.model_copy(update={"current_context_slice": new_slice})
        else:
            updated_orch = state.orchestration.copy(update={"current_context_slice": new_slice})
        return {"orchestration": updated_orch}

    # --- CONDITIONAL: Circuit Breaker (Semantic Entropy) ---
    def _check_semantic_health(self, state: StudioState) -> Literal["healthy", "tunneling", "retry"]:
        """
        The Mathematical Guardrail.
        Checks if circuit breaker was triggered by last agent output.
        Also checks if the Engineer Subgraph needs to retry.
        """
        if state.circuit_breaker_triggered:
            return "tunneling"

        jules_meta = state.engineering.jules_meta
        if jules_meta and jules_meta.status == "QUEUED":
            return "retry"

        return "healthy"
