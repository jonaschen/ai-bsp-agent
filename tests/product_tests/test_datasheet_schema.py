import pytest
from product.schemas.datasheet import DatasheetMetadata

def test_datasheet_metadata_fields():
    """Test that DatasheetMetadata has the required fields."""
    data = {
        "component_type": "PMIC",
        "part_number": "TPS6594",
        "voltage_range": "0.6V - 3.3V",
        "timing_specs": "tON: 2ms",
        "description": "Multi-phase PMIC for SoC power"
    }
    metadata = DatasheetMetadata(**data)
    assert metadata.component_type == "PMIC"
    assert metadata.part_number == "TPS6594"
    assert metadata.voltage_range == "0.6V - 3.3V"
    assert metadata.timing_specs == "tON: 2ms"
    assert metadata.description == "Multi-phase PMIC for SoC power"

def test_datasheet_metadata_serialization():
    """Test that DatasheetMetadata can be serialized and deserialized."""
    data = {
        "component_type": "DRAM",
        "part_number": "LPDDR5",
        "voltage_range": "1.1V",
        "timing_specs": "tCK: 0.5ns",
        "description": "Low power DDR5 SDRAM"
    }
    metadata = DatasheetMetadata(**data)
    json_data = metadata.model_dump_json()
    new_metadata = DatasheetMetadata.model_validate_json(json_data)
    assert new_metadata == metadata
