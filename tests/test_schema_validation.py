import pytest
import os
from bsp_agent.core.schema import CaseFile, LogPayload

def test_case_file_loading():
    """
    Test that the CaseFile schema can successfully load the panic_log_01.txt fixture.
    """
    # Use relative path or absolute path resolution
    fixture_path = os.path.join(os.path.dirname(__file__), 'fixtures', 'panic_log_01.txt')

    # Verify fixture exists
    assert os.path.exists(fixture_path), f"Fixture not found at {fixture_path}"

    with open(fixture_path, 'r') as f:
        log_content = f.read()

    # Construct the CaseFile payload
    case_data = {
        "case_id": "TEST-CASE-001",
        "device_model": "TestDevice_X",
        "source_code_mode": "USER_UPLOADED_ZIP",
        "symptom_description": "Kernel panic during resume.",
        "log_payload": {
            "dmesg_content": log_content,
            "logcat_content": None
        }
    }

    # Validate against the Pydantic model
    # This will raise ValidationError if schema is incorrect
    case_file = CaseFile(**case_data)

    # Assertions
    assert case_file.case_id == "TEST-CASE-001"
    assert case_file.log_payload.dmesg_content == log_content
    assert "Unable to handle kernel NULL pointer dereference" in case_file.log_payload.dmesg_content
