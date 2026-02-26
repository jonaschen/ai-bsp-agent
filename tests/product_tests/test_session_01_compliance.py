import os
from pathlib import Path

def test_schemas_file_structure():
    """Ensure that product/schemas.py exists and product/schemas/ is NOT a directory."""
    schemas_file = Path("product/schemas.py")
    schemas_dir = Path("product/schemas")

    assert schemas_file.is_file(), "product/schemas.py should be a file"
    assert not schemas_dir.is_dir(), "product/schemas/ should not be a directory (it should be consolidated to schemas.py)"

def test_hardware_advisor_output_has_soa_field():
    """Ensure HardwareAdvisorOutput has 'soa' field instead of 'soa_info'."""
    from product.schemas import HardwareAdvisorOutput
    assert "soa" in HardwareAdvisorOutput.model_fields
    assert "soa_info" not in HardwareAdvisorOutput.model_fields

def test_new_agent_contracts_exist():
    """Ensure SupervisorOutput and PathologistInput exist."""
    from product.schemas import SupervisorOutput, PathologistInput
    assert SupervisorOutput
    assert PathologistInput
