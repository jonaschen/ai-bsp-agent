from typing import List, Literal, Optional
from pydantic import BaseModel, Field

# --- Base Support Models ---

class LogPayload(BaseModel):
    """Container for different types of logs."""
    dmesg_content: str = Field(..., description="Raw content of dmesg log")
    logcat_content: str = Field("", description="Raw content of logcat log")

class SOPStep(BaseModel):
    """A single step in a Standard Operating Procedure."""
    step_id: int = Field(..., description="Order of the step")
    action_type: Literal["MEASUREMENT", "CODE_PATCH"] = Field(..., description="Type of action to take")
    instruction: str = Field(..., description="Detailed instructions for the human")
    expected_value: str = Field(..., description="What the human should see if the step is successful")
    file_path: str = Field(..., description="File path related to this step (if applicable)")

class ConsultantResponse(BaseModel):
    """The standardized output for all Consultant agents."""
    diagnosis_id: str = Field(..., description="Unique ID for this diagnosis")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence in the diagnosis")
    status: Literal["CRITICAL", "WARNING", "INFO", "CLARIFY_NEEDED"] = Field(..., description="Status of the analysis")
    root_cause_summary: str = Field(..., description="Brief summary of the root cause")
    evidence: List[str] = Field(..., description="Evidence supporting the diagnosis (e.g., log lines)")
    sop_steps: List[SOPStep] = Field(..., description="Standard Operating Procedure for the human")
