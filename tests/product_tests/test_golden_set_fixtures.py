import os
import json
import pytest
from product.schemas import ConsultantResponse

FIXTURES_DIR = "fixtures"

REQUIRED_FILES = [
    "panic_log_01.txt",
    "suspend_hang_02.txt",
    "healthy_boot_03.txt",
    "expected_output_panic_log_01.json",
    "expected_output_suspend_hang_02.json",
    "expected_output_healthy_boot_03.json",
]

@pytest.mark.parametrize("filename", REQUIRED_FILES)
def test_fixture_existence(filename):
    """Verify that all required golden set fixtures exist."""
    path = os.path.join(FIXTURES_DIR, filename)
    assert os.path.exists(path), f"Fixture {filename} is missing at {path}"

def test_panic_log_noise_level():
    """Verify that panic_log_01.txt contains at least 1500 lines of noise."""
    path = os.path.join(FIXTURES_DIR, "panic_log_01.txt")
    if not os.path.exists(path):
        pytest.skip("panic_log_01.txt missing")

    with open(path, "r") as f:
        lines = f.readlines()

    assert len(lines) >= 1500, f"panic_log_01.txt only has {len(lines)} lines, expected >= 1500"

@pytest.mark.parametrize("json_file", [
    "expected_output_panic_log_01.json",
    "expected_output_suspend_hang_02.json",
    "expected_output_healthy_boot_03.json",
])
def test_expected_output_schema(json_file):
    """Verify that expected output JSON files adhere to the ConsultantResponse schema."""
    path = os.path.join(FIXTURES_DIR, json_file)
    if not os.path.exists(path):
        pytest.skip(f"{json_file} missing")

    with open(path, "r") as f:
        data = json.load(f)

    # This will fail if the JSON doesn't match the schema or if schema is not updated yet
    # The requirement specifically mentions confidence_score
    assert "confidence_score" in data, f"{json_file} must use 'confidence_score'"
    ConsultantResponse(**data)
