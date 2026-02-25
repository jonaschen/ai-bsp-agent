import pytest
from studio.memory import TestResult, ContextSlice

def test_context_slice_footprint_determinism():
    """Test that identical ContextSlice objects produce the same footprint."""
    c1 = ContextSlice(files=["a.py", "b.py"], issues=["1", "2"])
    c2 = ContextSlice(files=["a.py", "b.py"], issues=["1", "2"])
    assert c1.footprint() == c2.footprint()

def test_context_slice_footprint_sorting():
    """Test that footprint is order-independent for files and issues."""
    c1 = ContextSlice(files=["a.py", "b.py"], issues=["1", "2"])
    c2 = ContextSlice(files=["b.py", "a.py"], issues=["2", "1"])
    assert c1.footprint() == c2.footprint()

def test_context_slice_footprint_sensitivity():
    """Test that footprint changes when content changes."""
    c1 = ContextSlice(files=["a.py"], issues=["1"])
    c2 = ContextSlice(files=["a.py", "b.py"], issues=["1"])
    assert c1.footprint() != c2.footprint()

def test_context_slice_footprint_empty():
    """Test footprint generation with empty fields."""
    c1 = ContextSlice(files=[], issues=[])
    assert isinstance(c1.footprint(), str)
    assert len(c1.footprint()) > 0

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
