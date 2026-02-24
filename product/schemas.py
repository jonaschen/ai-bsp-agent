from typing import List, Literal, Optional
from pydantic import BaseModel, Field

class LogPayload(BaseModel):
    """Container for different types of logs."""
    dmesg_content: str = Field(..., description="Raw content of dmesg log")
    logcat_content: str = Field("", description="Raw content of logcat log")

class CaseFile(BaseModel):
    """The core input unit containing logs and metadata."""
    case_id: str = Field(..., description="Unique identifier for the case", examples=["CASE-123"])
    device_model: str = Field(..., description="The device model being debugged", examples=["Pixel 8"])
    source_code_mode: str = Field(..., description="How source code is accessed (e.g., 'git', 'tarball')", examples=["git"])
    symptom_description: str = Field(..., description="User's description of the problem", examples=["Kernel panic on boot"])
    log_payload: LogPayload = Field(..., description="The log contents")

class TriageReport(BaseModel):
    """Initial triage results from the Supervisor."""
    status: Literal["CRITICAL", "WARNING"]
    failure_type: Literal["KERNEL_PANIC", "WATCHDOG", "HANG_STALL", "RESUME_FAIL"]
    event_horizon_timestamp: str = Field(..., description="Timestamp of the failure event", examples=["123.456"])
    key_evidence: List[str] = Field(..., description="Key log lines indicating the failure")
    suspected_file_hint: str = Field(..., description="Potential file path suspected to be involved", examples=["drivers/gpu/drm/msm/mdss.c"])

class RCAReport(BaseModel):
    """Root Cause Analysis Report."""
    diagnosis_id: str = Field(..., description="Unique identifier for this diagnosis", examples=["RCA-001"])
    confidence_score: float = Field(ge=0.0, le=1.0, description="Confidence in the diagnosis")
    root_cause_summary: str = Field(..., description="Brief summary of the root cause")
    technical_detail: str = Field(..., description="Deep dive into the technical root cause")
    suggested_fix: str = Field(..., description="Recommended code or hardware fix")
    references: List[str] = Field(..., description="Supporting references (CVEs, Gerrit links, etc.)")

class SOPStep(BaseModel):
    """A single step in a Standard Operating Procedure."""
    step_id: int = Field(..., description="Order of the step")
    action_type: Literal["MEASUREMENT", "CODE_PATCH"] = Field(..., description="Type of action to take")
    instruction: str = Field(..., description="Detailed instructions for the human")
    expected_value: str = Field(..., description="What the human should see if the step is successful")
    file_path: str = Field(..., description="File path related to this step (if applicable)")

class ConsultantResponse(BaseModel):
    """The standardized output for all Consultant agents."""
    diagnosis_id: str = Field(..., description="Unique ID for this diagnosis", examples=["RCA-BSP-001"])
    confidence_score: float = Field(ge=0.0, le=1.0, description="Confidence in the diagnosis")
    status: Literal["CRITICAL", "WARNING", "INFO", "CLARIFY_NEEDED"]
    root_cause_summary: str = Field(..., description="Brief summary of the root cause")
    evidence: List[str] = Field(..., description="Evidence supporting the diagnosis (e.g., log lines)")
    sop_steps: List[SOPStep] = Field(..., description="Standard Operating Procedure for the human")

# Agent Persona Contracts

class SupervisorInput(CaseFile):
    """Input contract for the Supervisor Agent (User Query + Log File)."""
    pass

class PathologistOutput(ConsultantResponse):
    """Output contract for the Kernel Pathologist Agent."""
    suspected_module: str = Field(..., description="The kernel module or subsystem suspected of failure", examples=["drivers/usb/dwc3/"])

class HardwareAdvisorInput(CaseFile):
    """Input contract for the Hardware Advisor Agent."""
    component_name: str = Field(..., description="Name of the hardware component to query", examples=["PMIC", "LPDDR5"])
    query_type: Literal["VOLTAGE", "TIMING", "SOA", "GENERAL"] = Field(..., description="Type of hardware query")
    triage_info: Optional[TriageReport] = None

class HardwareAdvisorOutput(ConsultantResponse):
    """Output contract for the Hardware Advisor Agent."""
    voltage_specs: Optional[str] = Field(None, description="Voltage requirements from datasheet", examples=["1.8V +/- 5%"])
    timing_specs: Optional[str] = Field(None, description="Timing requirements from datasheet", examples=["tVAC min 100ns"])
    soa_info: Optional[str] = Field(None, description="Safe Operating Area details", examples=["Max junction temp 125C"])
