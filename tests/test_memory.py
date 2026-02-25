import pytest
from studio.memory import TestResult

def test_test_result_summary_success():
    """Test that summary generates correct format for PASS status."""
    result = TestResult(
        test_id="test_login",
        status="PASS",
        logs="Login successful",
        duration_ms=150
    )
    assert result.summary() == "[PASS] test_login (150ms)"

def test_test_result_summary_failure():
    """Test that summary generates correct format for FAIL status."""
    result = TestResult(
        test_id="test_payment",
        status="FAIL",
        logs="Payment declined",
        duration_ms=500
    )
    assert result.summary() == "[FAIL] test_payment (500ms)"

def test_test_result_summary_defaults():
    """Test summary with default values (duration_ms=0)."""
    result = TestResult(
        test_id="test_config",
        status="ERROR",
        logs="Config missing"
    )
    assert result.summary() == "[ERROR] test_config (0ms)"
