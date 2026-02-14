"""
studio/memory.py
----------------
Defines the Pydantic Schema for the Studio's Single Source of Truth.
Refined based on "Engineering Resilient Cognitive Architectures" (Report 588).

Updates:
- Added SemanticHealthMetric for SE monitoring[cite: 722].
- Added ContextBundle for strict context slicing.
"""

from typing import List, Dict, Optional, Literal, Any, TypedDict, Annotated, Union
import operator
from datetime import datetime
import uuid
from pydantic import BaseModel, Field, HttpUrl, validator

# --- SECTION 1: Mathematical Guardrails (Semantic Entropy) ---
class SemanticHealthMetric(BaseModel):
    """
    Runtime metric for 'Cognitive Health'.
    Used by Orchestrator to trigger Circuit Breakers.
    Ref: [cite: 722]
    """
    entropy_score: float = Field(..., description="Calculated uncertainty (0.0 - 10.0)")
    threshold: float = 7.0
    sample_size: int = Field(default=5, description="Number of parallel generations")
    is_tunneling: bool = Field(..., description="True if entropy_score > threshold")
    cluster_distribution: Dict[str, float] = Field(default={}, description="Distribution of semantic meanings")

class AgentStepOutput(BaseModel):
    """
    Standardized Output Wrapper for all Agent Actions.
    Forces agents to report their 'Mental State' along with content.
    Ref: [cite: 723]
    """
    content: str
    thought_process: str
    cognitive_health: Optional[SemanticHealthMetric] = None

class SemanticEntropyReading(BaseModel):
    """
    A specific measurement of the agent's cognitive uncertainty.
    Used by the Entropy_Guard node to detect 'Cognitive Tunneling'.

    Research Threshold: SE > 7.0 typically indicates hallucination or
    reasoning loop collapse.
    """
    score: float = Field(..., ge=0.0, description="The calculated entropy score (SE)")
    threshold: float = Field(default=7.0, description="The breaker threshold at time of reading")
    triggered_breaker: bool = Field(..., description="Whether this reading forced an interruption")
    context_hash: str = Field(..., description="Hash of the context slice used for this generation")
    reasoning_trace_summary: Optional[str] = Field(None, description="Summary of thoughts analyzed")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

# --- SECTION 2: Context Slicing Structures ---
class ContextSlice(BaseModel):
    """
    Ephemeral data bundle passed to agents to prevent Context Collapse.
    Ref: [cite: 405, 818]
    """
    slice_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    intent: Literal["DIAGNOSIS", "CODING", "REVIEW"] = "CODING"
    active_files: Dict[str, str] = Field(default_factory=dict, description="Subset of file content (AST or snippets)")
    relevant_logs: str = Field(default="", description="Pre-sliced 'Event Horizon' logs (max 500 lines)")
    constraints: List[str] = Field(default_factory=list, description="Active constitutional rules")

    # New fields for Jules Proxy
    files: List[str] = Field(default_factory=list, description="List of file paths included")
    issues: List[str] = Field(default_factory=list, description="List of issue IDs or summaries")
    ast_summaries: Dict[str, str] = Field(default_factory=dict, description="Compressed AST representations")

    def footprint(self) -> str:
        """Generates a hash or footprint of the context for provenance."""
        return str(hash(tuple(sorted(self.files)) + tuple(sorted(self.issues))))

# --- SECTION 3: The Core State Layers ---

class TestResult(BaseModel):
    """
    Represents the outcome of a TDD cycle step (Red or Green).
    Used by the QA_Verifier node to enforce functional correctness and
    generate 'Evidence Snippets' for the Feedback Loop.
    """
    test_id: str = Field(..., description="Unique identifier for the test case (e.g., test_login_failure)")
    status: Literal["PASS", "FAIL", "ERROR"]
    logs: str = Field(..., description="Console output, stack trace, or compiler error")
    duration_ms: int = Field(default=0, description="Execution time in milliseconds")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    attempt_count: int = Field(default=1, description="Iteration number for this specific test case")

    def summary(self) -> str:
        """Returns a concise summary for log ingestion."""
        return f"[{self.status}] {self.test_id} ({self.duration_ms}ms)"

class CodeChangeArtifact(BaseModel):
    """
    Represents a tangible output from the engineer agent.
    Supports the 'Virtual Patching' capability mentioned in MVP strategy ,
    allowing users to apply 'git diff' patches directly.
    """
    file_path: str = Field(default="")
    diff_content: str = Field(..., description="Git diff format content")
    change_type: Literal["ADD", "MODIFY", "DELETE"] = "MODIFY"
    commit_message: Optional[str] = None
    pr_link: Optional[HttpUrl] = None

class ArchitecturalDecisionRecord(BaseModel):
    """
    Represents an Architectural Decision Record (ADR).
    Captures significant architectural decisions, their context, and consequences.
    """
    id: str = Field(..., description="Unique ADR Identifier (e.g., ADR-001)")
    title: str = Field(..., description="Short title of the decision")
    status: Literal["PROPOSED", "ACCEPTED", "REJECTED", "DEPRECATED"]
    context: str = Field(..., description="Context and problem statement")
    decision: str = Field(..., description="The decision made")
    consequences: Optional[str] = Field(None, description="Positive and negative consequences")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class JulesMetadata(BaseModel):
    """
    Manages the state and lifecycle of the asynchronous Jules-style Engineer Agent.
    This schema acts as the 'Shadow State' for the remote worker, persisting
    across LangGraph checkpoints.
    """
    # Identity & Session Management
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique session ID for the remote Jules instance")
    external_task_id: Optional[str] = Field(None, description="ID assigned by the external provider (e.g., Google Cloud)")

    # Status Tracking
    # QUEUED: Task received from Orchestrator, waiting for dispatch
    # PLANNING: Agent is analyzing context and formulating a plan
    # WORKING: Asynchronous execution in progress (VM active)
    # VERIFYING: Code produced, currently under local QA/Review
    # BLOCKED: Waiting for human input (Interactive Debugging) or Handoff
    # COMPLETED: Work accepted and merged
    # FAILED: Irrecoverable error or max retries exceeded
    status: Literal["QUEUED", "PLANNING", "WORKING", "VERIFYING", "BLOCKED", "COMPLETED", "FAILED"] = "QUEUED"

    # Cognitive Health Metrics (The Mathematical Guardrails)
    current_entropy: float = 0.0
    entropy_history: List[SemanticEntropyReading] = Field(default_factory=list)
    cognitive_tunneling_detected: bool = False

    # Execution Artifacts
    current_branch: Optional[str] = None
    generated_artifacts: List[CodeChangeArtifact] = Field(default_factory=list)
    test_results_history: List[TestResult] = Field(default_factory=list)

    # Feedback & Control
    feedback_log: List[str] = Field(default_factory=list, description="Accumulated feedback from QA and Architect")
    retry_count: int = 0
    max_retries: int = 5

    # Context Slicing (Input to the Agent)
    active_context_slice: ContextSlice = Field(default_factory=ContextSlice)

    # Store the original prompt to allow entropy re-sampling
    current_task_prompt: Optional[str] = None

    class Config:
        frozen = False  # Mutable state for Pydantic V2 compatibility in LangGraph
        arbitrary_types_allowed = True

class AgentState(TypedDict):
    """
    The Global State object for the LangGraph Supergraph.
    Combines conversational history, global context, and sub-agent metadata.
    """
    # Message history with append-only semantics
    messages: Annotated[List[Any], operator.add]

    # Global architectural state (AGENTS.md representation)
    system_constitution: str

    # Handoff routing information - supports the Handoff Protocol
    next_agent: Optional[str]

    # Subgraph Metadata integration
    # This is the dedicated slot for the Jules Proxy state
    jules_metadata: JulesMetadata


# Layer 1: Orchestration (The Runtime)
TicketStatus = Literal["OPEN", "IN_PROGRESS", "BLOCKED", "COMPLETED", "FAILED"]

class Ticket(BaseModel):
    id: str = Field(..., description="Unique Ticket ID (e.g., TKT-101)")
    title: str = Field(..., description="Actionable title")
    description: str = Field(..., description="Technical acceptance criteria")
    priority: str = Field(..., description="CRITICAL, HIGH, MEDIUM, LOW")
    dependencies: List[str] = Field(default_factory=list, description="List of Ticket IDs that must be completed FIRST")
    source_section_id: str = Field(..., description="The Blueprint Section ID this ticket fulfills (e.g., '2.1-Supervisor')")

    # Execution State
    status: TicketStatus = "OPEN"
    failure_log: Optional[str] = None
    retry_count: int = 0
    closure_reason: Optional[str] = None

class TriageStatus(BaseModel):
    is_log_available: bool
    suspected_domain: str
    assigned_specialist: Optional[str] = None
    handoff_reason: Optional[str] = None

class SOPState(BaseModel):
    """Tracks Interactive Debugging flow for No-Log scenarios """
    active_sop_id: Optional[str] = None
    current_step_index: int = 0
    pending_steps: List[str] = []

class OrchestrationState(BaseModel):
    session_id: str
    user_intent: str
    triage_status: Optional[TriageStatus] = None
    guidance_sop: Optional[SOPState] = None
    # The active context slice being processed
    current_context_slice: Optional[ContextSlice] = None
    task_queue: List[Ticket] = Field(default_factory=list, description="The Product Backlog")

    # Sprint Management
    current_sprint_id: Optional[str] = None
    completed_tasks_log: List[Ticket] = []
    failed_tasks_log: List[Ticket] = []

# --- SECTION 4: Shared Agent Artifacts ---

class StudioMeta(BaseModel):
    """Metadata about the Studio Environment."""
    pass

class SprintBoard(BaseModel):
    """Represents the current Sprint Board state."""
    pass

class OptimizationLog(BaseModel):
    """Log of applied optimizations."""
    pass

# From Architect Agent
class Violation(BaseModel):
    """A specific breach of the Constitution."""
    rule_id: str = Field(..., description="e.g., 'SRP' or 'Security-01'")
    severity: Literal["CRITICAL", "MAJOR", "MINOR"]
    description: str
    file_path: str
    line_number: Optional[int] = Field(None, description="Line number where violation occurs (for PR comments)")
    suggested_fix: str

class ReviewVerdict(BaseModel):
    """The Architect's Final Decision."""
    status: Literal["APPROVED", "REJECTED", "NEEDS_REFACTOR"]
    quality_score: float = Field(..., description="0.0 to 10.0 scale")
    violations: List[Violation] = []
    adr_entry: Optional[ArchitecturalDecisionRecord] = Field(None, description="New rule to record if needed")

# Legacy / Review Agent Artifacts
class ReviewSummary(BaseModel):
    """
    Summary of the semantic review from the Review Agent.
    """
    status: Literal["PASSED", "FAILED"]
    root_cause: str
    suggested_fix: str

class ReviewResult(BaseModel):
    """
    Final result of the review process.
    """
    approved: bool
    feedback: str

# From Scrum Master Agent
class ProcessOptimization(BaseModel):
    """A specific suggestion to improve the System."""
    target_role: str = Field(..., description="The Agent needing improvement (e.g., 'Engineer', 'Product Owner')")
    issue_detected: str = Field(..., description="The recurring failure pattern")
    suggested_prompt_update: str = Field(..., description="Specific text to add/change in the Agent's System Prompt")
    expected_impact: str = Field(..., description="Why this will help")

class RetrospectiveReport(BaseModel):
    """The Output of a Sprint Retrospective."""
    sprint_id: str
    success_rate: float = Field(..., description="0.0 to 1.0")
    avg_entropy_score: float = Field(..., description="Average Semantic Entropy of the sprint")
    key_bottlenecks: List[str]
    optimizations: List[ProcessOptimization]

# Layer 2: Engineering (The TDD Loop)
class VerificationGate(BaseModel):
    status: Literal["RED", "GREEN", "PENDING"]
    failure_counter: int = 0
    blocking_reason: Optional[str] = None

class EngineeringState(BaseModel):
    current_task: Optional[str] = None
    verification_gate: VerificationGate = Field(default_factory=lambda: VerificationGate(status="PENDING"))
    # Code artifacts are stored here, but only sliced versions are sent to agents
    proposed_patch: Optional[str] = None
    jules_meta: Optional[JulesMetadata] = None

# --- ROOT: Studio State ---
class StudioState(BaseModel):
    """
    The Single Source of Truth.
    Managed by LangGraph Checkpointer.
    Ref: [cite: 829]
    """
    # Meta-Data
    system_version: str = "5.2.0"
    circuit_breaker_triggered: bool = False # Hard Stop for SE > 7.0 [cite: 733]

    # Layers
    orchestration: OrchestrationState
    engineering: EngineeringState

    # Privacy & Security
    privacy_mode: bool = True # If True, redact PII from Optimizer

    def get_agent_slice(self, role: str) -> ContextSlice:
        """
        Logic to generate the specific view for an agent.
        Implementation of the 'Context Slicing' principle.
        Ref:
        """
        # (This logic will be implemented in the Orchestrator,
        # but the structure is defined here)
        pass
