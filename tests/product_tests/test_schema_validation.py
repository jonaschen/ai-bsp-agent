import pytest
from pathlib import Path
from product.schemas import CaseFile

def test_case_file_ingestion():
    # Arrange
    fixture_path = Path("tests/fixtures/panic_log_01.txt")
    with open(fixture_path, "r") as f:
        raw_log = f.read()

    payload = {
        "case_id": "TEST-001",
        "device_model": "Pixel_Prototype_Unit",
        "source_code_mode": "USER_UPLOADED_ZIP",
        "user_query": "Kernel panic during resume",
        "log_payload": {
            "dmesg_content": raw_log,
            "logcat_content": ""
        }
    }

    # Act
    case = CaseFile(**payload)

    # Assert
    assert case.case_id == "TEST-001"
    assert "Unable to handle kernel NULL pointer" in case.log_payload.dmesg_content
    assert case.log_payload.logcat_content == ""
