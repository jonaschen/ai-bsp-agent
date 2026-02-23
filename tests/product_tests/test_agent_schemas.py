import pytest
import json
from pydantic import ValidationError
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
    obj = SupervisorInput(**payload)
    assert obj.user_chat == "Analyze the log for kernel panic"
    assert len(obj.case_files) == 1
    assert obj.case_files[0].case_id == "CASE-001"

    # Test JSON serialization
    json_data = obj.model_dump_json()
    assert "Analyze the log for kernel panic" in json_data

def test_pathologist_output_serialization():
    payload = {
        "suspected_module": "drivers/gpu/drm/msm/mdss.c",
        "confidence_score": 0.95,
        "evidence": ["NULL pointer dereference at ..."]
    }
    obj = PathologistOutput(**payload)
    assert obj.suspected_module == "drivers/gpu/drm/msm/mdss.c"
    assert obj.confidence_score == 0.95
    assert "NULL pointer dereference" in obj.evidence[0]

    # Test JSON serialization
    json_data = obj.model_dump_json()
    assert "0.95" in json_data

def test_hardware_advisor_input_serialization():
    payload = {
        "component_name": "PMIC",
        "query_type": "VOLTAGE"
    }
    obj = HardwareAdvisorInput(**payload)
    assert obj.component_name == "PMIC"
    assert obj.query_type == "VOLTAGE"

def test_hardware_advisor_output_serialization():
    payload = {
        "voltage_specs": {"VREG_L1": "1.8V"},
        "timing_specs": {"startup_delay": "10ms"},
        "soa_validation": "Within safe limits"
    }
    obj = HardwareAdvisorOutput(**payload)
    assert obj.voltage_specs["VREG_L1"] == "1.8V"
    assert obj.soa_validation == "Within safe limits"

    # Test JSON serialization
    json_data = obj.model_dump_json()
    assert "VREG_L1" in json_data

def test_triage_report_serialization():
    payload = {
        "status": "CRITICAL",
        "failure_type": "KERNEL_PANIC",
        "event_horizon_timestamp": "2023-10-27T10:00:00Z",
        "key_evidence": ["Panic occurred"],
        "suspected_file_hint": "main.c"
    }
    obj = TriageReport(**payload)
    assert obj.status == "CRITICAL"
    assert obj.model_dump()["status"] == "CRITICAL"

def test_rca_report_serialization():
    payload = {
        "diagnosis_id": "RCA-001",
        "confidence_score": 0.88,
        "root_cause_summary": "Faulty sensor",
        "technical_detail": "Detailed explanation...",
        "suggested_fix": "Replace sensor",
        "references": ["Link 1"]
    }
    obj = RCAReport(**payload)
    assert obj.diagnosis_id == "RCA-001"
    assert obj.confidence_score == 0.88

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
    obj = ConsultantResponse(**payload)
    assert obj.diagnosis_id == "RCA-001"
    assert len(obj.sop_steps) == 1
    assert obj.sop_steps[0].instruction == "Measure VREG"
