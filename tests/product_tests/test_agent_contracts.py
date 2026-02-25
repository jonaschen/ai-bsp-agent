import json
import pytest
from pydantic import ValidationError
from product.schemas import (
    SupervisorInput,
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

def test_supervisor_input_serialization():
    supervisor_data = {
        "case_id": "CASE-123",
        "device_model": "Pixel 8",
        "source_code_mode": "git",
        "user_query": "Kernel panic on boot",
        "log_payload": {
            "dmesg_content": "[ 0.000000] Linux version...",
            "logcat_content": "I/ActivityManager: ..."
        }
    }
    assert_roundtrip(SupervisorInput, supervisor_data)

def test_pathologist_output_serialization():
    pathologist_data = {
        "diagnosis_id": "DIAG-456",
        "confidence_score": 0.95,
        "status": "CRITICAL",
        "root_cause_summary": "Null pointer in dwc3 driver",
        "evidence": ["Attempted to access offset 0x20 of NULL pointer"],
        "sop_steps": [
            {
                "step_id": 1,
                "action_type": "CODE_PATCH",
                "instruction": "Add NULL check in dwc3_gadget_ep_enable",
                "expected_value": "No more null pointer dereference",
                "file_path": "drivers/usb/dwc3/gadget.c"
            }
        ],
        "suspected_module": "drivers/usb/dwc3/"
    }
    assert_roundtrip(PathologistOutput, pathologist_data)

def test_hardware_advisor_input_serialization():
    hardware_input_data = {
        "case_id": "CASE-789",
        "device_model": "Pixel 9",
        "source_code_mode": "tarball",
        "user_query": "Display flicker",
        "log_payload": {
            "dmesg_content": "...",
            "logcat_content": "..."
        },
        "component_name": "PMIC",
        "query_type": "VOLTAGE",
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
        ],
        "voltage_specs": "1.8V",
        "timing_specs": "400kHz",
        "soa_info": "Max 85C"
    }
    assert_roundtrip(HardwareAdvisorOutput, hardware_output_data)

def test_hardware_advisor_output_confidence_validation():
    invalid_hw_data = {
        "diagnosis_id": "DIAG-789",
        "confidence_score": 1.5, # Out of bounds [0.0, 1.0]
        "status": "CRITICAL",
        "root_cause_summary": "I2C bus contention",
        "evidence": [],
        "sop_steps": [],
        "voltage_specs": None,
        "timing_specs": None,
        "soa_info": None
    }
    with pytest.raises(ValidationError):
        HardwareAdvisorOutput(**invalid_hw_data)

def test_pathologist_output_confidence_validation():
    invalid_path_data = {
        "diagnosis_id": "DIAG-456",
        "confidence_score": -0.1, # Out of bounds [0.0, 1.0]
        "status": "CRITICAL",
        "root_cause_summary": "Summary",
        "evidence": [],
        "sop_steps": [],
        "suspected_module": "module"
    }
    with pytest.raises(ValidationError):
        PathologistOutput(**invalid_path_data)

def test_supervisor_input_required_fields_validation():
    incomplete_data = {
        "case_id": "CASE-123"
        # missing device_model, etc.
    }
    with pytest.raises(ValidationError):
        SupervisorInput(**incomplete_data)
