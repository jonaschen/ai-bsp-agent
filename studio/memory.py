"""
studio/memory.py
----------------
Defines the Schema for the Studio's Single Source of Truth (studio_state.json).
Enforces the "Memory Fabric" architecture for the AI Agent Scrum Team.

Layers:
1. Hot: Runtime Context (Orchestration)
2. Warm: Sprint Board (Task Tracking)
3. Cold: Product Backlog (Requirements)
4. Episodic: Review History (Learning)
"""

from typing import List, Dict, Optional, Literal, Union, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field, HttpUrl, validator

# --- Primitive Types ---
AgentRole = Literal["Orchestrator", "ProductOwner", "ScrumMaster", "Architect", "Engineer", "QA", "Optimizer"]
TicketStatus = Literal["TODO", "IN_PROGRESS", "REVIEW", "DONE", "BLOCKED"]
VerificationStatus = Literal["GREEN", "RED", "PENDING"]
PrivacyLevel = Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL_USER_DATA"]

# --- Layer 4: Episodic Memory (Long-term Wisdom) ---
class ArchitecturalDecisionRecord(BaseModel):
    id: str
    title: str
    date: str
    status: Literal["PROPOSED", "ACCEPTED", "DEPRECATED"]
    consequences: List[str]

class RetrospectiveInsight(BaseModel):
    sprint_id: str
    insight_type: Literal["PROCESS_IMPROVEMENT", "TOOLING_GAP", "TEAM_DYNAMIC"]
    observation: str
    action_item: str

class EpisodicMemory(BaseModel):
    architectural_decision_records: List[ArchitecturalDecisionRecord] = []
    retrospective_insights: List[RetrospectiveInsight] = []

# --- Layer 3: Optimization State (Evolution) ---
class HardNegative(BaseModel):
    input_id: str
    expected: str
    actual: str

class OptimizationTrajectory(BaseModel):
    iteration: int
    prompt_hash: str
    score: float = Field(..., ge=0.0, le=1.0)
    feedback: str

class OptimizationState(BaseModel):
    target_prompt: str  # e.g., "product/prompts/pathologist.yaml"
    optimization_trajectory: List[OptimizationTrajectory] = []
    hard_negatives: List[HardNegative] = []

# --- Layer 2: Engineering & Quality State (The Factory Floor) ---
class WorkspaceSnapshot(BaseModel):
    current_file: str
    git_branch: str
    diff_stat: str

class CodeArtifacts(BaseModel):
    proposed_patch: str
    justification_refs: List[str] = Field(
        ..., 
        description="Must link to specific Ticket Criteria or Blueprint Sections. Traceability is mandatory."
    )
    lint_score: Optional[float] = None

class TestRunResult(BaseModel):
    test_id: str
    outcome: Literal["PASS", "FAIL", "ERROR"]
    error_message: Optional[str] = None
    duration_ms: float

class VerificationGate(BaseModel):
    status: VerificationStatus
    latest_test_run: Optional[TestRunResult] = None
    failure_counter: int = 0

class EngineeringState(BaseModel):
    workspace_snapshot: Optional[WorkspaceSnapshot] = None
    code_artifacts: Optional[CodeArtifacts] = None
    verification_gate: VerificationGate = Field(default_factory=lambda: VerificationGate(status="PENDING"))

# --- Layer 1: Orchestration & Sprint State (The Runtime) ---
class Ticket(BaseModel):
    id: str
    title: str
    status: TicketStatus
    assigned_to: Optional[AgentRole] = None
    priority: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    acceptance_criteria: List[str] = []

class SprintBoard(BaseModel):
    sprint_id: str
    sprint_goal: str
    start_date: str
    end_date: str
    tickets: Dict[str, Ticket] = {}
    blockers: List[str] = []

class InteractionTurn(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class InquirySession(BaseModel):
    privacy_level: PrivacyLevel = "CONFIDENTIAL_USER_DATA"
    session_id: str
    user_intent: str
    interaction_history: List[InteractionTurn] = []
    active_agent: Optional[AgentRole] = None

class OrchestrationState(BaseModel):
    sprint_board: SprintBoard
    inquiry_session: Optional[InquirySession] = None

# --- ROOT: The Studio State (Single Source of Truth) ---
class StudioMeta(BaseModel):
    system_version: str
    constitution_hash: str
    current_phase: str
    simulation_mode: bool = False
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StudioState(BaseModel):
    """
    The Root State Object for the AI Software Studio.
    Managed by LangGraph Checkpointers.
    """
    studio_meta: StudioMeta
    orchestration_state: OrchestrationState
    engineering_state: EngineeringState
    optimization_state: OptimizationState
    episodic_memory: EpisodicMemory

    # --- Access Control Helpers (The Matrix) ---
    def get_view_for_agent(self, role: AgentRole) -> Dict[str, Any]:
        """
        Returns a filtered view of the state based on the Agent's Permission Matrix.
        This prevents agents from hallucinating or accessing restricted data.
        """
        view = {}
        
        # Everyone sees Meta and Blueprint (implied)
        view["meta"] = self.studio_meta.dict()

        if role == "Orchestrator":
            return self.dict() # God View

        elif role == "ProductOwner":
            view["sprint_board"] = self.orchestration_state.sprint_board.dict()
            # PO focuses on tickets, not code or runtime logs

        elif role == "ScrumMaster":
            view["sprint_board"] = self.orchestration_state.sprint_board.dict()
            view["episodic_memory"] = self.episodic_memory.dict()
            view["metrics"] = self.engineering_state.verification_gate.dict()

        elif role == "Engineer":
            # Engineer sees their active ticket and the workspace
            # They do NOT see the full history or strategic insights to save context
            view["active_ticket"] = self._get_active_ticket_for("Engineer")
            view["workspace"] = self.engineering_state.dict()

        elif role == "QA":
            view["artifacts"] = self.engineering_state.code_artifacts.dict()
            view["criteria"] = self._get_active_ticket_for("Engineer").get("acceptance_criteria", [])

        elif role == "Optimizer":
            # Optimizer sees the failure history but NOT User Data (Privacy)
            view["optimization_state"] = self.optimization_state.dict()
            if not self.studio_meta.simulation_mode:
                 # Redact user session in production optimization
                 view["sanitized_session"] = "REDACTED" 
            
        return view

    def _get_active_ticket_for(self, role: str) -> Dict:
        """Helper to find the ticket assigned to the agent."""
        for tid, ticket in self.orchestration_state.sprint_board.tickets.items():
            if ticket.assigned_to == role and ticket.status == "IN_PROGRESS":
                return ticket.dict()
        return {}
