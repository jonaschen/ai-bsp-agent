from typing import List, Literal, Optional
from pydantic import BaseModel, Field

class LogPayload(BaseModel):
    """Container for different types of logs."""
    dmesg_content: str = Field(..., description="Raw content of dmesg log", examples=["[ 0.000000] Linux version 6.1.0..."])
    logcat_content: str = Field("", description="Raw content of logcat log", examples=["01-01 12:00:00.000  1000  1000 I ActivityManager: Start proc..."])

class CaseFile(BaseModel):
    """The core input unit containing logs and metadata."""
    case_id: str = Field(..., description="Unique identifier for the case", examples=["CASE-123"])
    device_model: str = Field(..., description="The device model being debugged", examples=["Pixel 8"])
    source_code_mode: str = Field(..., description="How source code is accessed (e.g., 'git', 'tarball')", examples=["git"])
    user_query: str = Field(..., description="User's description of the problem", examples=["Kernel panic on boot"])
    log_payload: LogPayload = Field(..., description="The log contents", examples=[{"dmesg_content": "[ 0.000000] Linux version...", "logcat_content": "..."}])

class TriageReport(BaseModel):
    """Initial triage results from the Supervisor."""
    status: Literal["CRITICAL", "WARNING"] = Field(..., description="Severity of the failure", examples=["CRITICAL"])
    failure_type: Literal["KERNEL_PANIC", "WATCHDOG", "HANG_STALL", "RESUME_FAIL"] = Field(..., description="Type of failure detected", examples=["KERNEL_PANIC"])
    event_horizon_timestamp: str = Field(..., description="Timestamp of the failure event", examples=["123.456"])
    key_evidence: List[str] = Field(..., description="Key log lines indicating the failure", examples=["[ 123.456] Unable to handle kernel NULL pointer dereference"])
    suspected_file_hint: str = Field(..., description="Potential file path suspected to be involved", examples=["drivers/gpu/drm/msm/mdss.c"])

class RCAReport(BaseModel):
    """Root Cause Analysis Report."""
    diagnosis_id: str = Field(..., description="Unique identifier for this diagnosis", examples=["RCA-001"])
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence in the diagnosis", examples=[0.95])
    root_cause_summary: str = Field(..., description="Brief summary of the root cause", examples=["Null pointer dereference in mdss driver"])
    technical_detail: str = Field(..., description="Deep dive into the technical root cause", examples=["The driver attempted to access a clock pointer before it was initialized..."])
    suggested_fix: str = Field(..., description="Recommended code or hardware fix", examples=["Add a NULL check for clk_ptr in mdss_dsi_probe"])
    references: List[str] = Field(..., description="Supporting references (CVEs, Gerrit links, etc.)", examples=["CVE-2023-1234", "https://android-review.googlesource.com/12345"])

class SOPStep(BaseModel):
    """A single step in a Standard Operating Procedure."""
    step_id: int = Field(..., description="Order of the step", examples=[1])
    action_type: Literal["MEASUREMENT", "CODE_PATCH"] = Field(..., description="Type of action to take", examples=["CODE_PATCH"])
    instruction: str = Field(..., description="Detailed instructions for the human", examples=["Add NULL check in drivers/usb/dwc3/gadget.c at line 123"])
    expected_value: str = Field(..., description="What the human should see if the step is successful", examples=["Compilation succeeds and kernel panic is no longer reproducible"])
    file_path: str = Field(..., description="File path related to this step (if applicable)", examples=["drivers/usb/dwc3/gadget.c"])

class ConsultantResponse(BaseModel):
    """The standardized output for all Consultant agents."""
    diagnosis_id: str = Field(..., description="Unique ID for this diagnosis", examples=["RCA-BSP-001"])
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence in the diagnosis", examples=[0.85])
    status: Literal["CRITICAL", "WARNING", "INFO", "CLARIFY_NEEDED"] = Field(..., description="Status of the analysis", examples=["CRITICAL"])
    root_cause_summary: str = Field(..., description="Brief summary of the root cause", examples=["I2C bus contention during resume"])
    evidence: List[str] = Field(..., description="Evidence supporting the diagnosis (e.g., log lines)", examples=["[ 1450.02] i2c_transfer_timeout"])
    sop_steps: List[SOPStep] = Field(..., description="Standard Operating Procedure for the human", examples=[{"step_id": 1, "action_type": "MEASUREMENT", "instruction": "Probe TP34", "expected_value": "1.8V", "file_path": "N/A"}])

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
    query_type: Literal["VOLTAGE", "TIMING", "SOA", "GENERAL"] = Field(..., description="Type of hardware query", examples=["VOLTAGE"])
    triage_info: Optional[TriageReport] = Field(None, description="Optional triage info from Supervisor", examples=[{"status": "CRITICAL", "failure_type": "KERNEL_PANIC", "event_horizon_timestamp": "123.456", "key_evidence": ["..."], "suspected_file_hint": "..."}])

class HardwareAdvisorOutput(ConsultantResponse):
    """Output contract for the Hardware Advisor Agent."""
    voltage_specs: Optional[str] = Field(None, description="Voltage requirements from datasheet", examples=["1.8V +/- 5%"])
    timing_specs: Optional[str] = Field(None, description="Timing requirements from datasheet", examples=["tVAC min 100ns"])
    soa_info: Optional[str] = Field(None, description="Safe Operating Area details", examples=["Max junction temp 125C"])
