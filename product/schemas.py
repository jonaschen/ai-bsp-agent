"""
product/schemas.py: Source of Truth for Agent I/O Contracts.
Includes Pydantic models for Supervisor, Pathologist, and Hardware Advisor agents.
"""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field

# --- Base Support Models ---

class LogPayload(BaseModel):
    """Container for different types of logs."""
    dmesg_content: str = Field(..., description="Raw content of dmesg log", examples=["[ 0.000000] Linux version 6.1.0...", "[ 123.456] Unable to handle kernel NULL pointer dereference"])
    logcat_content: str = Field("", description="Raw content of logcat log", examples=["01-01 12:00:00.000  1000  1000 I ActivityManager: Start proc...", "01-01 12:00:05.123  1000  1000 E AndroidRuntime: FATAL EXCEPTION"])

class SOPStep(BaseModel):
    """A single step in a Standard Operating Procedure."""
    step_id: int = Field(..., description="Order of the step", examples=[1, 2])
    action_type: Literal["MEASUREMENT", "CODE_PATCH"] = Field(..., description="Type of action to take", examples=["CODE_PATCH", "MEASUREMENT"])
    instruction: str = Field(..., description="Detailed instructions for the human", examples=["Add NULL check in drivers/usb/dwc3/gadget.c at line 123", "Probe TP34 with an oscilloscope"])
    expected_value: str = Field(..., description="What the human should see if the step is successful", examples=["Compilation succeeds and kernel panic is no longer reproducible", "1.8V stable DC signal"])
    file_path: str = Field(..., description="File path related to this step (if applicable)", examples=["drivers/usb/dwc3/gadget.c", "N/A"])

class CaseFile(BaseModel):
    """The core input unit containing logs and metadata."""
    case_id: str = Field(..., description="Unique identifier for the case", examples=["CASE-123", "BUG-999"])
    device_model: str = Field(..., description="The device model being debugged", examples=["Pixel 8", "Pixel 9 Pro"])
    source_code_mode: str = Field(..., description="How source code is accessed (e.g., 'git', 'tarball')", examples=["git", "tarball"])
    user_query: str = Field(..., description="User's description of the problem", examples=["Kernel panic on boot", "System hangs during suspend to RAM"])
    log_payload: LogPayload = Field(..., description="The log contents", examples=[{"dmesg_content": "[ 0.000000] Linux version...", "logcat_content": "..."}])

class TriageReport(BaseModel):
    """Initial triage results from the Supervisor."""
    status: Literal["CRITICAL", "WARNING"] = Field(..., description="Severity of the failure", examples=["CRITICAL", "WARNING"])
    failure_type: Literal["KERNEL_PANIC", "WATCHDOG", "HANG_STALL", "RESUME_FAIL"] = Field(..., description="Type of failure detected", examples=["KERNEL_PANIC", "WATCHDOG"])
    event_horizon_timestamp: str = Field(..., description="Timestamp of the failure event", examples=["123.456", "2024-01-01 12:00:00"])
    key_evidence: List[str] = Field(..., description="Key log lines indicating the failure", examples=[["[ 123.456] Unable to handle kernel NULL pointer dereference", "Watchdog detected hard lockup on CPU 0"]])
    suspected_file_hint: str = Field(..., description="Potential file path suspected to be involved", examples=["drivers/gpu/drm/msm/mdss.c", "kernel/sched/core.c"])

class RCAReport(BaseModel):
    """Root Cause Analysis Report as defined in Blueprint Section 3."""
    diagnosis_id: str = Field(..., description="Unique identifier for this diagnosis", examples=["RCA-BSP-001", "RCA-BSP-042"])
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence in the diagnosis", examples=[0.95, 0.80])
    status: Literal["CRITICAL", "WARNING", "INFO"] = Field(..., description="Severity of the failure", examples=["CRITICAL", "WARNING"])
    root_cause_summary: str = Field(..., description="Brief summary of the root cause", examples=["Null pointer dereference in mdss driver", "I2C bus contention during resume"])
    evidence: List[str] = Field(..., description="Evidence supporting the diagnosis (e.g., log lines)", examples=[["[ 1450.02] i2c_transfer_timeout", "pc : [<ffffffc000080000>]"]])
    sop_steps: List[SOPStep] = Field(..., description="Standard Operating Procedure for the human", examples=[[{"step_id": 1, "action_type": "MEASUREMENT", "instruction": "Probe TP34", "expected_value": "1.8V", "file_path": "N/A"}]])

class ConsultantResponse(BaseModel):
    """The standardized output for all Consultant agents."""
    diagnosis_id: str = Field(..., description="Unique ID for this diagnosis", examples=["RCA-BSP-001", "DIAG-PATH-001"])
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in the diagnosis", examples=[0.85, 0.99])
    status: Literal["CRITICAL", "WARNING", "INFO", "CLARIFY_NEEDED"] = Field(..., description="Status of the analysis", examples=["CRITICAL", "INFO"])
    root_cause_summary: str = Field(..., description="Brief summary of the root cause", examples=["I2C bus contention during resume", "Null pointer dereference in kernel"])
    evidence: List[str] = Field(..., description="Evidence supporting the diagnosis (e.g., log lines)", examples=[["[ 1450.02] i2c_transfer_timeout", "pc : [<ffffffc000080000>]"]])
    sop_steps: List[SOPStep] = Field(..., description="Standard Operating Procedure for the human", examples=[[{"step_id": 1, "action_type": "MEASUREMENT", "instruction": "Probe TP34", "expected_value": "1.8V", "file_path": "N/A"}]])

# --- Agent Persona Contracts (Decoupled Architecture) ---

class SupervisorInput(BaseModel):
    """Input contract for the Supervisor Agent (User Query + Log File)."""
    user_query: str = Field(..., description="User's description of the problem", examples=["Kernel panic on boot", "Display flicker"])
    log_file: LogPayload = Field(..., description="The log content container", examples=[{"dmesg_content": "[ 0.000000] Linux version...", "logcat_content": "..."}])
    case_metadata: Optional[dict] = Field(None, description="Optional metadata about the device/source", examples=[{"device_model": "Pixel 8", "source_code_mode": "git"}])

class SupervisorOutput(BaseModel):
    """Output contract for the Supervisor Agent."""
    status: Literal["OK", "CLARIFY_NEEDED"] = Field(..., description="Status of the triage process", examples=["OK", "CLARIFY_NEEDED"])
    next_specialist: Literal["kernel_pathologist", "hardware_advisor", "none"] = Field(..., description="The recommended specialist for the next step", examples=["kernel_pathologist", "hardware_advisor"])
    triage_report: Optional[TriageReport] = Field(None, description="Initial triage results if available", examples=[{"status": "CRITICAL", "failure_type": "KERNEL_PANIC", "event_horizon_timestamp": "123.456", "key_evidence": ["..."], "suspected_file_hint": "..."}])

class PathologistInput(BaseModel):
    """Input contract for the Kernel Pathologist Agent."""
    log_chunk: str = Field(..., description="The extracted 'Event Horizon' log chunk", examples=["[ 123.456] Unable to handle kernel NULL pointer dereference"])
    triage_info: TriageReport = Field(..., description="Triage information from the Supervisor", examples=[{"status": "CRITICAL", "failure_type": "KERNEL_PANIC", "event_horizon_timestamp": "123.456", "key_evidence": ["..."], "suspected_file_hint": "..."}])

class PathologistOutput(BaseModel):
    """Output contract for the Kernel Pathologist Agent."""
    suspected_module: str = Field(..., description="The kernel module or subsystem suspected of failure", examples=["drivers/usb/dwc3/", "kernel/irq/"])
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in the pathologist's diagnosis", examples=[0.95, 0.70])
    evidence: List[str] = Field(..., description="Key log lines or patterns supporting the suspicion", examples=[["[ 123.456] Unable to handle kernel NULL pointer dereference", "pc : [<ffffffc000080000>]"]])
    sop_steps: List[SOPStep] = Field(..., description="Recommended SOP steps for verification or fix", examples=[[{"step_id": 1, "action_type": "CODE_PATCH", "instruction": "Add NULL check", "expected_value": "No panic", "file_path": "drivers/usb/dwc3/gadget.c"}]])

class HardwareAdvisorInput(BaseModel):
    """Input contract for the Hardware Advisor Agent."""
    component_name: str = Field(..., description="Name of the hardware component to query", examples=["PMIC", "LPDDR5", "UFS"])
    query_type: Literal["VOLTAGE", "TIMING", "SOA", "GENERAL"] = Field(..., description="Type of hardware query", examples=["VOLTAGE", "TIMING"])
    context_case: Optional[CaseFile] = Field(None, description="The full case context if available", examples=[{"case_id": "CASE-123", "device_model": "Pixel 8", "source_code_mode": "git", "user_query": "...", "log_payload": {"dmesg_content": "...", "logcat_content": "..."}}])
    triage_info: Optional[TriageReport] = Field(None, description="Optional triage info from Supervisor", examples=[{"status": "CRITICAL", "failure_type": "KERNEL_PANIC", "event_horizon_timestamp": "123.456", "key_evidence": ["..."], "suspected_file_hint": "..."}])

class HardwareAdvisorOutput(BaseModel):
    """Output contract for the Hardware Advisor Agent."""
    voltage_specs: Optional[str] = Field(None, description="Voltage requirements from datasheet", examples=["1.8V +/- 5%", "0.8V VDD_CORE"])
    timing_specs: Optional[str] = Field(None, description="Timing requirements from datasheet", examples=["tVAC min 100ns", "tCK 1.25ns"])
    soa: Optional[str] = Field(None, description="Safe Operating Area details", examples=["Max junction temp 125C", "Max current 2A"])
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in the specs retrieved", examples=[0.99, 0.85])
    evidence: List[str] = Field(..., description="Supporting excerpts from the datasheet", examples=[["Table 5.1: VDD range 1.7V to 1.9V"]])
    sop_steps: List[SOPStep] = Field(..., description="Measurement instructions for the human", examples=[[{"step_id": 1, "action_type": "MEASUREMENT", "instruction": "Measure TP34", "expected_value": "1.8V", "file_path": "N/A"}]])
