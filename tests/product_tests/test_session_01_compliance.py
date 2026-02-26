import os
import pytest
from product import schemas

def test_schema_file_structure():
    """AC: All three agents have formal Pydantic models in product/schemas.py"""
    # Check if product/schemas.py exists and is a file
    schema_path = "product/schemas.py"
    assert os.path.isfile(schema_path), f"{schema_path} should be a file"

    # Check if product/schemas/ directory does not exist
    schema_dir = "product/schemas"
    assert not os.path.isdir(schema_dir), f"{schema_dir} should not be a directory"

def test_supervisor_input_formalization():
    """Deliverable: Supervisor input schema (user query + log file format)"""
    from product.schemas import SupervisorInput
    fields = SupervisorInput.model_fields
    assert "user_query" in fields
    assert "log_file" in fields
    # Check for examples
    assert fields["user_query"].examples
    assert fields["log_file"].examples

def test_pathologist_output_formalization():
    """Deliverable: Pathologist output schema (suspected module, confidence score, evidence)"""
    from product.schemas import PathologistOutput
    fields = PathologistOutput.model_fields
    assert "suspected_module" in fields
    assert "confidence" in fields
    assert "evidence" in fields
    # Check for examples
    assert fields["suspected_module"].examples
    assert fields["confidence"].examples
    assert fields["evidence"].examples

def test_hardware_advisor_input_formalization():
    """Deliverable: Hardware Advisor input schema (component name, query type)"""
    from product.schemas import HardwareAdvisorInput
    fields = HardwareAdvisorInput.model_fields
    assert "component_name" in fields
    assert "query_type" in fields
    # Check for examples
    assert fields["component_name"].examples
    assert fields["query_type"].examples

def test_hardware_advisor_output_formalization():
    """Deliverable: Hardware Advisor output schema (voltage specs, timing specs, SOA)"""
    from product.schemas import HardwareAdvisorOutput
    fields = HardwareAdvisorOutput.model_fields
    assert "voltage_specs" in fields
    assert "timing_specs" in fields
    assert "soa" in fields
    # Check for examples
    assert fields["voltage_specs"].examples
    assert fields["timing_specs"].examples
    assert fields["soa"].examples
