from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

class DatasheetMetadata(BaseModel):
    """
    Metadata for a hardware component datasheet.

    VECTOR EMBEDDING STRATEGY:
    --------------------------
    The following fields are concatenated into a single string for vector embedding:
    - component_type
    - part_number
    - description

    Example embedding string:
    "PMIC TPS6594-Q1 Multi-rail PMIC for automotive applications"

    Metadata filters (for Chroma/Vertex AI):
    - component_type
    - part_number

    EXAMPLE RETRIEVAL QUERIES:
    --------------------------
    1. "Find the voltage requirements for the TPS6594-Q1 PMIC"
    2. "What are the timing specifications for LPDDR5 memory chips?"
    3. "Retrieve the datasheet for the Snapdragon 8 Gen 3 SoC"
    """
    component_type: str = Field(..., description="Type of component (e.g., PMIC, DRAM, SoC)", examples=["PMIC"])
    part_number: str = Field(..., description="Manufacturer part number", examples=["TPS6594-Q1"])
    voltage_range: Optional[str] = Field(None, description="Operating voltage range", examples=["3.3V - 5.0V"])
    timing_specs: Optional[Dict[str, Any]] = Field(None, description="Key timing specifications")
    description: Optional[str] = Field(None, description="Brief description of the component")
