import pytest
import json
from product.schemas import (
    SupervisorInput,
    PathologistOutput,
    HardwareAdvisorInput,
    HardwareAdvisorOutput,
    CaseFile,
    LogPayload,
    TriageReport,
    RCAReport,
    SOPStep,
    ConsultantResponse
)

def validate_serialization(model_class, payload):
    """
    Robust validation pattern: Payload -> Model -> JSON string -> Dict -> Assert equality
    """
    # 1. Payload -> Model
    obj = model_class(**payload)

    # 2. Model -> JSON string
    json_str = obj.model_dump_json()

    # 3. JSON string -> Dict
    result_dict = json.loads(json_str)

    # 4. Assert equality with original payload
    # Note: Pydantic model_dump_json might convert some types (like dates),
    # but for these simple schemas it should match the input dict.
    # We use model_dump() on the object to compare against result_dict for better consistency.
    assert obj.model_dump() == result_dict

    # Also check against original payload for basic fields
    for key, value in payload.items():
        assert result_dict[key] == value

def test_log_payload_serialization():
    payload = {
        "dmesg_content": "kernel panic",
        "logcat_content": "some logs"
    }
    validate_serialization(LogPayload, payload)

def test_case_file_serialization():
    payload = {
        "case_id": "CASE-001",
        "device_model": "Pixel 6",
        "source_code_mode": "KERNEL_TREE",
        "symptom_description": "Boot loop",
        "log_payload": {
            "dmesg_content": "kernel panic...",
            "logcat_content": ""
        }
    }
    validate_serialization(CaseFile, payload)

def test_triage_report_serialization():
    payload = {
        "status": "CRITICAL",
        "failure_type": "KERNEL_PANIC",
        "event_horizon_timestamp": "2023-10-27T10:00:00Z",
        "key_evidence": ["Panic occurred"],
        "suspected_file_hint": "main.c"
    }
    validate_serialization(TriageReport, payload)

def test_rca_report_serialization():
    payload = {
        "diagnosis_id": "RCA-001",
        "confidence_score": 0.88,
        "root_cause_summary": "Faulty sensor",
        "technical_detail": "Detailed explanation...",
        "suggested_fix": "Replace sensor",
        "references": ["Link 1"]
    }
    validate_serialization(RCAReport, payload)

def test_sop_step_serialization():
    payload = {
        "step_id": 1,
        "action_type": "MEASUREMENT",
        "instruction": "Measure VREG",
        "expected_value": "1.8V",
        "file_path": "N/A"
    }
    validate_serialization(SOPStep, payload)

def test_consultant_response_serialization():
    payload = {
        "diagnosis_id": "RCA-001",
        "confidence_score": 0.9,
        "status": "CRITICAL",
        "root_cause_summary": "Issue found",
        "evidence": ["Evidence 1"],
        "sop_steps": [
            {
                "step_id": 1,
                "action_type": "MEASUREMENT",
                "instruction": "Measure VREG",
                "expected_value": "1.8V",
                "file_path": "N/A"
            }
        ]
    }
    validate_serialization(ConsultantResponse, payload)

def test_supervisor_input_serialization():
    payload = {
        "user_chat": "Analyze the log for kernel panic",
        "case_files": [
            {
                "case_id": "CASE-001",
                "device_model": "Pixel 6",
                "source_code_mode": "KERNEL_TREE",
                "symptom_description": "Boot loop",
                "log_payload": {
                    "dmesg_content": "kernel panic...",
                    "logcat_content": ""
                }
            }
        ]
    }
    validate_serialization(SupervisorInput, payload)

def test_pathologist_output_serialization():
    payload = {
        "suspected_module": "drivers/gpu/drm/msm/mdss.c",
        "confidence_score": 0.95,
        "evidence": ["NULL pointer dereference at ..."]
    }
    validate_serialization(PathologistOutput, payload)

def test_hardware_advisor_input_serialization():
    payload = {
        "component_name": "PMIC",
        "query_type": "VOLTAGE"
    }
    validate_serialization(HardwareAdvisorInput, payload)

def test_hardware_advisor_output_serialization():
    payload = {
        "voltage_specs": {"VREG_L1": "1.8V"},
        "timing_specs": {"startup_delay": "10ms"},
        "soa_validation": "Within safe limits"
    }
    validate_serialization(HardwareAdvisorOutput, payload)
