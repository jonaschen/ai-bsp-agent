from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class DatasheetMetadata(BaseModel):
    """
    Metadata for a hardware component datasheet.
    Used for filtering and structured retrieval in the RAG pipeline.
    """
    component_type: str = Field(..., description="Type of component (e.g., PMIC, DRAM, SoC)", examples=["PMIC", "DRAM"])
    part_number: str = Field(..., description="Manufacturer part number", examples=["TPS6594", "MT53E"])
    manufacturer: str = Field(..., description="Manufacturer name", examples=["TI", "Micron", "Qualcomm"])
    voltage_range: Optional[Dict[str, Any]] = Field(None, description="Operating voltage range details", examples=[{"min": 0.6, "max": 3.3, "unit": "V"}])
    timing_specs: Optional[Dict[str, Any]] = Field(None, description="Timing characteristics (e.g., clock speeds)", examples=[{"i2c_speed": "400kHz"}])
    interfaces: List[str] = Field(default_factory=list, description="Supported interfaces (e.g., I2C, SPI, LPDDR5)", examples=[["I2C", "GPIO"]])

class Datasheet(BaseModel):
    """
    The core representation of a datasheet in the repository.

    ### Vector Embedding Strategy:
    To optimize for RAG, the following fields are concatenated for vectorization:
    - component_type
    - part_number
    - manufacturer
    - interfaces
    - content (summary or key sections)

    The metadata is stored in the vector store's 'metadata' field for hard-filtering
    (e.g., searching ONLY for 'PMIC' components).

    ### Expected Retrieval Query Patterns:
    1. "What is the voltage range for TPS6594?" -> Filter by part_number='TPS6594'
    2. "List I2C PMICs for Pixel 8" -> Filter by component_type='PMIC' and search 'I2C'
    3. "Timing specs for LPDDR5 on SoC SDM845" -> Search 'LPDDR5 SDM845 timing'
    """
    metadata: DatasheetMetadata = Field(..., description="Structured metadata for the component")
    content: str = Field(..., description="Text content of the datasheet or relevant excerpts")
    source_url: Optional[str] = Field(None, description="Link to the original PDF or source", examples=["https://example.com/datasheet.pdf"])
