import json
import pytest
from pydantic import ValidationError
from product.schemas import (
    LogPayload,
    CaseFile,
    TriageReport,
    RCAReport,
    SOPStep,
    ConsultantResponse,
    SupervisorInput,
    SupervisorOutput,
    PathologistInput,
    PathologistOutput,
    HardwareAdvisorInput,
    HardwareAdvisorOutput
)

def assert_roundtrip(model_class, data):
    """Helper to test roundtrip serialization/deserialization."""
    instance = model_class(**data)
    json_str = instance.model_dump_json()
    data_back = json.loads(json_str)
    # Re-instantiate to verify it's still valid
    instance_back = model_class(**data_back)
    assert instance == instance_back

def test_log_payload_serialization():
    data = {
        "dmesg_content": "[ 0.000000] Linux version...",
        "logcat_content": "I/ActivityManager: ..."
    }
    assert_roundtrip(LogPayload, data)

def test_case_file_serialization():
    data = {
        "case_id": "CASE-123",
        "device_model": "Pixel 8",
        "source_code_mode": "git",
        "user_query": "Kernel panic on boot",
        "log_payload": {
            "dmesg_content": "...",
            "logcat_content": "..."
        }
    }
    assert_roundtrip(CaseFile, data)

def test_triage_report_serialization():
    data = {
        "status": "CRITICAL",
        "failure_type": "KERNEL_PANIC",
        "event_horizon_timestamp": "123.456",
        "key_evidence": ["Panic occurred"],
        "suspected_file_hint": "drivers/usb/dwc3/gadget.c"
    }
    assert_roundtrip(TriageReport, data)

def test_rca_report_serialization():
    data = {
        "diagnosis_id": "RCA-BSP-001",
        "confidence_score": 0.9,
        "status": "CRITICAL",
        "root_cause_summary": "Summary",
        "evidence": ["Evidence 1"],
        "sop_steps": [
            {
                "step_id": 1,
                "action_type": "MEASUREMENT",
                "instruction": "Measure",
                "expected_value": "Value",
                "file_path": "N/A"
            }
        ]
    }
    assert_roundtrip(RCAReport, data)

def test_sop_step_serialization():
    data = {
        "step_id": 1,
        "action_type": "CODE_PATCH",
        "instruction": "Do something",
        "expected_value": "Expected",
        "file_path": "path/to/file"
    }
    assert_roundtrip(SOPStep, data)

def test_consultant_response_serialization():
    data = {
        "diagnosis_id": "DIAG-001",
        "confidence": 0.85,
        "status": "WARNING",
        "root_cause_summary": "Summary",
        "evidence": ["Evidence"],
        "sop_steps": [
            {
                "step_id": 1,
                "action_type": "MEASUREMENT",
                "instruction": "Measure",
                "expected_value": "Value",
                "file_path": "N/A"
            }
        ]
    }
    assert_roundtrip(ConsultantResponse, data)

def test_supervisor_input_serialization():
    supervisor_data = {
        "user_query": "Kernel panic on boot",
        "log_file": {
            "dmesg_content": "[ 0.000000] Linux version...",
            "logcat_content": "I/ActivityManager: ..."
        },
        "case_metadata": {
            "device_model": "Pixel 8",
            "source_code_mode": "git"
        }
    }
    assert_roundtrip(SupervisorInput, supervisor_data)

def test_pathologist_output_serialization():
    pathologist_data = {
        "suspected_module": "drivers/usb/dwc3/",
        "confidence": 0.95,
        "evidence": ["Attempted to access offset 0x20 of NULL pointer"],
        "sop_steps": [
            {
                "step_id": 1,
                "action_type": "CODE_PATCH",
                "instruction": "Add NULL check in dwc3_gadget_ep_enable",
                "expected_value": "No more null pointer dereference",
                "file_path": "drivers/usb/dwc3/gadget.c"
            }
        ]
    }
    assert_roundtrip(PathologistOutput, pathologist_data)

def test_hardware_advisor_input_serialization():
    hardware_input_data = {
        "component_name": "PMIC",
        "query_type": "VOLTAGE",
        "context_case": {
            "case_id": "CASE-789",
            "device_model": "Pixel 9",
            "source_code_mode": "tarball",
            "user_query": "Display flicker",
            "log_payload": {
                "dmesg_content": "...",
                "logcat_content": "..."
            }
        },
        "triage_info": {
            "status": "WARNING",
            "failure_type": "HANG_STALL",
            "event_horizon_timestamp": "123.456",
            "key_evidence": ["I2C timeout"],
            "suspected_file_hint": "drivers/i2c/busses/i2c-designware-core.c"
        }
    }
    assert_roundtrip(HardwareAdvisorInput, hardware_input_data)

def test_hardware_advisor_output_serialization():
    hardware_output_data = {
        "voltage_specs": "1.8V",
        "timing_specs": "400kHz",
        "soa": "Max 85C",
        "confidence": 0.8,
        "evidence": ["Datasheet Table 1"],
        "sop_steps": [
            {
                "step_id": 1,
                "action_type": "MEASUREMENT",
                "instruction": "Measure I2C SCL/SDA lines with oscilloscope",
                "expected_value": "Clean square waves without excessive noise",
                "file_path": "N/A"
            }
        ]
    }
    assert_roundtrip(HardwareAdvisorOutput, hardware_output_data)

def test_hardware_advisor_output_confidence_validation():
    invalid_hw_data = {
        "voltage_specs": "1.8V",
        "timing_specs": "400kHz",
        "soa": "Max 85C",
        "confidence": 1.5, # Out of bounds [0.0, 1.0]
        "evidence": [],
        "sop_steps": []
    }
    with pytest.raises(ValidationError):
        HardwareAdvisorOutput(**invalid_hw_data)

def test_supervisor_output_serialization():
    data = {
        "status": "OK",
        "next_specialist": "kernel_pathologist",
        "triage_report": {
            "status": "CRITICAL",
            "failure_type": "KERNEL_PANIC",
            "event_horizon_timestamp": "123.456",
            "key_evidence": ["Evidence"],
            "suspected_file_hint": "hint"
        }
    }
    assert_roundtrip(SupervisorOutput, data)

def test_pathologist_input_serialization():
    data = {
        "log_chunk": "Panic log",
        "triage_info": {
            "status": "CRITICAL",
            "failure_type": "KERNEL_PANIC",
            "event_horizon_timestamp": "123.456",
            "key_evidence": ["Evidence"],
            "suspected_file_hint": "hint"
        }
    }
    assert_roundtrip(PathologistInput, data)

def test_pathologist_output_confidence_validation():
    invalid_path_data = {
        "suspected_module": "module",
        "confidence": -0.1, # Out of bounds [0.0, 1.0]
        "evidence": [],
        "sop_steps": []
    }
    with pytest.raises(ValidationError):
        PathologistOutput(**invalid_path_data)

def test_supervisor_input_required_fields_validation():
    incomplete_data = {
        "user_query": "CASE-123"
        # missing log_file, etc.
    }
    with pytest.raises(ValidationError):
        SupervisorInput(**incomplete_data)
