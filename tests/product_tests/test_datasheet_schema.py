import pytest
from pydantic import ValidationError
try:
    from product.schemas.datasheet import Datasheet, DatasheetMetadata
except ImportError:
    Datasheet = None
    DatasheetMetadata = None

def test_datasheet_imports():
    assert Datasheet is not None, "Datasheet model not found in product.schemas.datasheet"
    assert DatasheetMetadata is not None, "DatasheetMetadata model not found in product.schemas.datasheet"

def test_datasheet_metadata_validation():
    if DatasheetMetadata is None:
        pytest.fail("DatasheetMetadata not imported")

    # Test valid metadata
    valid_data = {
        "component_type": "PMIC",
        "part_number": "TPS6594",
        "voltage_range": {"min": 0.6, "max": 3.3, "unit": "V"},
        "timing_specs": {"i2c_speed": "400kHz"},
        "manufacturer": "TI"
    }
    metadata = DatasheetMetadata(**valid_data)
    assert metadata.component_type == "PMIC"
    assert metadata.part_number == "TPS6594"

def test_datasheet_validation():
    if Datasheet is None:
        pytest.fail("Datasheet not imported")

    valid_data = {
        "metadata": {
            "component_type": "DRAM",
            "part_number": "MT53E",
            "manufacturer": "Micron"
        },
        "content": "Full datasheet text content here...",
        "source_url": "https://example.com/datasheet.pdf"
    }
    datasheet = Datasheet(**valid_data)
    assert datasheet.metadata.component_type == "DRAM"
    assert datasheet.content == "Full datasheet text content here..."
