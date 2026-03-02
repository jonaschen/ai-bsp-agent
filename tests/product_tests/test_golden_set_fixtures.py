import json
import pytest
from product.schemas import ConsultantResponse

# Single Source of Truth for fixtures
FIXTURE_PAIRS = [
    ("panic_log_01.txt", "expected_output_panic_log_01.json"),
    ("suspend_hang_02.txt", "expected_output_suspend_hang_02.json"),
    ("healthy_boot_03.txt", "expected_output_healthy_boot_03.json"),
]

@pytest.fixture
def fixtures_dir(request):
    """Fixture providing the path to the fixtures directory."""
    return request.config.rootpath / "fixtures"

@pytest.mark.parametrize("log_file, json_file", FIXTURE_PAIRS)
def test_fixture_existence(fixtures_dir, log_file, json_file):
    """Verify that all required golden set fixtures exist."""
    assert (fixtures_dir / log_file).exists(), f"Log fixture {log_file} is missing"
    assert (fixtures_dir / json_file).exists(), f"Expected output {json_file} is missing"

def test_panic_log_noise_level(fixtures_dir):
    """Verify that panic_log_01.txt contains at least 1500 lines of noise."""
    path = fixtures_dir / "panic_log_01.txt"
    if not path.exists():
        pytest.skip("panic_log_01.txt missing")

    with open(path, "r") as f:
        lines = f.readlines()

    assert len(lines) >= 1500, f"panic_log_01.txt only has {len(lines)} lines, expected >= 1500"

@pytest.mark.parametrize("log_file, json_file", FIXTURE_PAIRS)
def test_expected_output_schema(fixtures_dir, log_file, json_file):
    """Verify that expected output JSON files adhere to the ConsultantResponse schema."""
    path = fixtures_dir / json_file
    if not path.exists():
        pytest.skip(f"{json_file} missing")

    with open(path, "r") as f:
        data = json.load(f)

    # Verify mandatory use of confidence_score per Blueprint Section 3
    assert "confidence_score" in data, f"{json_file} must use 'confidence_score'"
    ConsultantResponse(**data)
