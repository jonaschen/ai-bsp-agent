from pydantic import BaseModel, Field

class DatasheetMetadata(BaseModel):
    """
    Metadata schema for hardware datasheets used in RAG indexing.

    VECTOR EMBEDDING STRATEGY:
    The following fields are combined into a single string for vector embedding:
    - component_type
    - part_number
    - description
    This ensures that semantic searches for component categories (e.g., "PMIC")
    or specific parts (e.g., "TPS6594") yield relevant results.

    EXAMPLE RETRIEVAL QUERIES:
    - "What is the voltage range for the TPS6594 PMIC?"
    - "Find LPDDR5 timing specifications for memory initialization."
    - "Check SOA limits for the main SoC power rail."
    """
    component_type: str = Field(..., description="Category of the component (e.g., PMIC, DRAM, SoC)", examples=["PMIC"])
    part_number: str = Field(..., description="Manufacturer part number", examples=["TPS6594"])
    voltage_range: str = Field(..., description="Operating voltage specifications", examples=["0.6V - 3.3V"])
    timing_specs: str = Field(..., description="Critical timing parameters (e.g., tCK, tVAC)", examples=["tON: 2ms"])
    description: str = Field(..., description="Brief description of the component functionality", examples=["Multi-phase PMIC for SoC power"])
