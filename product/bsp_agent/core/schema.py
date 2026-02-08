from typing import List, Literal
from pydantic import BaseModel, Field

class LogPayload(BaseModel):
    dmesg_content: str = Field(..., description="Raw content of dmesg log")
    logcat_content: str = Field("", description="Raw content of logcat log")

class CaseFile(BaseModel):
    case_id: str
    device_model: str
    source_code_mode: str
    symptom_description: str
    log_payload: LogPayload

class TriageReport(BaseModel):
    status: Literal["CRITICAL", "WARNING"]
    failure_type: Literal["KERNEL_PANIC", "WATCHDOG", "HANG_STALL", "RESUME_FAIL"]
    event_horizon_timestamp: str
    key_evidence: List[str]
    suspected_file_hint: str

class RCAReport(BaseModel):
    diagnosis_id: str
    confidence_score: float
    root_cause_summary: str
    technical_detail: str
    suggested_fix: str
    references: List[str]

class SOPStep(BaseModel):
    step_id: int
    action_type: Literal["MEASUREMENT", "CODE_PATCH"]
    instruction: str
    expected_value: str
    file_path: str

class ConsultantResponse(BaseModel):
    diagnosis_id: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    status: Literal["CRITICAL", "WARNING", "INFO", "CLARIFY_NEEDED"]
    root_cause_summary: str
    evidence: List[str]
    sop_steps: List[SOPStep]
