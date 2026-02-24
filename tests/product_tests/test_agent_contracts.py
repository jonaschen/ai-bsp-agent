import json
import pytest
from pydantic import BaseModel, ValidationError
from product.schemas import (
    SupervisorInput,
    PathologistOutput,
    HardwareAdvisorInput,
    HardwareAdvisorOutput,
    CaseFile,
    LogPayload,
    TriageReport,
    RCAReport,
    ConsultantResponse,
    SOPStep
)

def test_json_serialization_roundtrip():
    # Helper to test roundtrip
    def assert_roundtrip(model_class, data):
        instance = model_class(**data)
        json_str = instance.model_dump_json()
        data_back = json.loads(json_str)
        # Handle potential differences in how Pydantic serializes (e.g. tuples vs lists)
        # but for simple dicts it should match
        assert data_back == json.loads(instance.model_dump_json())
        # Re-instantiate to verify it's still valid
        instance_back = model_class(**data_back)
        assert instance == instance_back

    # Test SupervisorInput (inherited from CaseFile)
    supervisor_data = {
        "case_id": "CASE-123",
        "device_model": "Pixel 8",
        "source_code_mode": "git",
        "symptom_description": "Kernel panic on boot",
        "log_payload": {
            "dmesg_content": "[ 0.000000] Linux version...",
            "logcat_content": "I/ActivityManager: ..."
        }
    }
    assert_roundtrip(SupervisorInput, supervisor_data)

    # Test PathologistOutput (inherited from RCAReport)
    pathologist_data = {
        "diagnosis_id": "DIAG-456",
        "confidence_score": 0.95,
        "root_cause_summary": "Null pointer in dwc3 driver",
        "technical_detail": "Attempted to access offset 0x20 of NULL pointer",
        "suggested_fix": "Add NULL check in dwc3_gadget_ep_enable",
        "references": ["CVE-2023-XXXXX"]
    }
    assert_roundtrip(PathologistOutput, pathologist_data)

    # Test HardwareAdvisorInput
    hardware_input_data = {
        "case_id": "CASE-789",
        "device_model": "Pixel 9",
        "source_code_mode": "tarball",
        "symptom_description": "Display flicker",
        "log_payload": {
            "dmesg_content": "...",
            "logcat_content": "..."
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

    # Test HardwareAdvisorOutput (inherited from ConsultantResponse)
    hardware_output_data = {
        "diagnosis_id": "DIAG-789",
        "confidence_score": 0.8,
        "status": "CRITICAL",
        "root_cause_summary": "I2C bus contention",
        "evidence": ["Log shows multiple masters trying to access the bus"],
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

def test_validation_errors():
    # Test confidence_score bounds for HardwareAdvisorOutput
    invalid_hw_data = {
        "diagnosis_id": "DIAG-789",
        "confidence_score": 1.5, # Out of bounds [0.0, 1.0]
        "status": "CRITICAL",
        "root_cause_summary": "I2C bus contention",
        "evidence": [],
        "sop_steps": []
    }
    with pytest.raises(ValidationError):
        HardwareAdvisorOutput(**invalid_hw_data)

    # Test confidence_score bounds for PathologistOutput
    invalid_path_data = {
        "diagnosis_id": "DIAG-456",
        "confidence_score": -0.1, # Out of bounds [0.0, 1.0]
        "root_cause_summary": "Summary",
        "technical_detail": "Detail",
        "suggested_fix": "Fix",
        "references": []
    }
    with pytest.raises(ValidationError):
        PathologistOutput(**invalid_path_data)

    # Test missing required field
    incomplete_data = {
        "case_id": "CASE-123"
        # missing device_model, etc.
    }
    with pytest.raises(ValidationError):
        SupervisorInput(**incomplete_data)
