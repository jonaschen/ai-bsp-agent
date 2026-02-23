from typing import List, Literal, Dict
from pydantic import BaseModel, Field

class LogPayload(BaseModel):
    """Raw log content for analysis."""
    dmesg_content: str = Field(..., description="Raw content of dmesg log")
    logcat_content: str = Field("", description="Raw content of logcat log")

class CaseFile(BaseModel):
    """Container for device metadata and logs."""
    case_id: str = Field(..., description="Unique identifier for the case")
    device_model: str = Field(..., description="Model of the device (e.g., 'Pixel 6')")
    source_code_mode: str = Field(..., description="Source code access mode")
    symptom_description: str = Field(..., description="Description of the failure symptom")
    log_payload: LogPayload = Field(..., description="The log content")

class TriageReport(BaseModel):
    """Initial assessment of the failure."""
    status: Literal["CRITICAL", "WARNING"]
    failure_type: Literal["KERNEL_PANIC", "WATCHDOG", "HANG_STALL", "RESUME_FAIL"]
    event_horizon_timestamp: str
    key_evidence: List[str]
    suspected_file_hint: str

class RCAReport(BaseModel):
    """Detailed Root Cause Analysis report."""
    diagnosis_id: str
    confidence_score: float
    root_cause_summary: str
    technical_detail: str
    suggested_fix: str
    references: List[str]

class SOPStep(BaseModel):
    """A single step in the Standard Operating Procedure."""
    step_id: int
    action_type: Literal["MEASUREMENT", "CODE_PATCH"]
    instruction: str
    expected_value: str
    file_path: str

class ConsultantResponse(BaseModel):
    """The final response from the consultant squad."""
    diagnosis_id: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    status: Literal["CRITICAL", "WARNING", "INFO", "CLARIFY_NEEDED"]
    root_cause_summary: str
    evidence: List[str]
    sop_steps: List[SOPStep]

class SupervisorInput(BaseModel):
    """Input for the Supervisor agent, containing user query and case files."""
    user_chat: str = Field(..., description="The user's query or instruction.")
    case_files: List[CaseFile] = Field(..., description="List of log files and device metadata.")

    model_config = {
        "json_schema_extra": {
            "example": {
                "user_chat": "Analyze the kernel panic in these logs.",
                "case_files": [
                    {
                        "case_id": "CASE-123",
                        "device_model": "Pixel 7",
                        "source_code_mode": "KERNEL_TREE",
                        "symptom_description": "Kernel panic during boot",
                        "log_payload": {
                            "dmesg_content": "[0.000000] Linux version...",
                            "logcat_content": "01-01 00:00:00.000..."
                        }
                    }
                ]
            }
        }
    }

class HardwareAdvisorInput(BaseModel):
    """Input for the Hardware Advisor agent, querying specific component specs."""
    component_name: str = Field(..., description="Name of the hardware component (e.g., 'PMIC', 'DRAM').")
    query_type: str = Field(..., description="Type of information requested (e.g., 'VOLTAGE', 'TIMING', 'SOA').")

    model_config = {
        "json_schema_extra": {
            "example": {
                "component_name": "PMIC",
                "query_type": "VOLTAGE"
            }
        }
    }

class HardwareAdvisorOutput(BaseModel):
    """Output from the Hardware Advisor agent, providing component specifications and SOA validation."""
    voltage_specs: Dict[str, str] = Field(default_factory=dict, description="Voltage requirements and specifications.")
    timing_specs: Dict[str, str] = Field(default_factory=dict, description="Timing requirements and specifications.")
    soa_validation: str = Field(..., description="Safe Operating Area (SOA) validation result.")

    model_config = {
        "json_schema_extra": {
            "example": {
                "voltage_specs": {"VREG_L1": "1.8V", "VREG_L2": "0.9V"},
                "timing_specs": {"startup_delay": "10ms"},
                "soa_validation": "Current readings are within safe operating limits."
            }
        }
    }

class PathologistOutput(BaseModel):
    """Output from the Kernel Pathologist agent, identifying the suspected software module."""
    suspected_module: str = Field(..., description="The software module suspected of causing the issue.")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence score of the diagnosis.")
    evidence: List[str] = Field(..., description="Key log lines or stack trace snippets as evidence.")

    model_config = {
        "json_schema_extra": {
            "example": {
                "suspected_module": "drivers/gpu/drm/msm/mdss.c",
                "confidence_score": 0.92,
                "evidence": [
                    "Unable to handle kernel NULL pointer dereference at virtual address 0000000000000000",
                    "pc : mdss_dsi_panel_power_on+0x3c/0x120"
                ]
            }
        }
    }
