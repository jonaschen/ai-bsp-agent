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
