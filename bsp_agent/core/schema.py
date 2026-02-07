from typing import List, Optional
from pydantic import BaseModel, Field

class LogPayload(BaseModel):
    dmesg_content: Optional[str] = Field(None, description="Raw content or URL of dmesg log")
    logcat_content: Optional[str] = Field(None, description="Raw content or URL of logcat log")

class CaseFile(BaseModel):
    case_id: str
    device_model: str
    source_code_mode: str
    symptom_description: str
    log_payload: LogPayload

class TriageReport(BaseModel):
    status: str
    failure_type: str
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
