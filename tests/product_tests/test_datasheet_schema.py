import pytest
from pydantic import ValidationError
try:
    from product.schemas.datasheet import DatasheetMetadata
except ImportError:
    DatasheetMetadata = None

def test_datasheet_metadata_import():
    assert DatasheetMetadata is not None, "DatasheetMetadata could not be imported from product.schemas.datasheet"

def test_datasheet_metadata_validation():
    if DatasheetMetadata is None:
        pytest.fail("DatasheetMetadata is not defined")

    data = {
        "component_type": "PMIC",
        "part_number": "TPS6594-Q1",
        "voltage_range": "3.3V - 5.0V",
        "timing_specs": {"t_rise": "10ms", "t_fall": "5ms"},
        "description": "Multi-rail PMIC for automotive applications"
    }
    metadata = DatasheetMetadata(**data)
    assert metadata.component_type == "PMIC"
    assert metadata.part_number == "TPS6594-Q1"

def test_datasheet_metadata_missing_fields():
    if DatasheetMetadata is None:
        pytest.fail("DatasheetMetadata is not defined")

    with pytest.raises(ValidationError):
        DatasheetMetadata(component_type="PMIC") # Missing part_number
