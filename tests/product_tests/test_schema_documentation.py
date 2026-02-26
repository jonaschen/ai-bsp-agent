import pytest
from product.schemas import (
    SupervisorInput,
    SupervisorOutput,
    PathologistInput,
    PathologistOutput,
    HardwareAdvisorInput,
    HardwareAdvisorOutput,
    LogPayload,
    SOPStep,
    TriageReport,
    RCAReport,
    CaseFile,
    ConsultantResponse
)

@pytest.mark.parametrize("model", [
    SupervisorInput,
    SupervisorOutput,
    PathologistInput,
    PathologistOutput,
    HardwareAdvisorInput,
    HardwareAdvisorOutput,
    LogPayload,
    SOPStep,
    TriageReport,
    RCAReport,
    CaseFile,
    ConsultantResponse
])
def test_models_have_examples(model):
    """Verify that all fields in the models have examples for documentation."""
    # We only check top-level properties for now as check_examples_recursive handles them
    schema = model.model_json_schema()
    properties = schema.get('properties', {})
    for prop_name, prop_data in properties.items():
        # For simplicity in TDD, let's just check if 'examples' exists in the Field
        # Note: Pydantic 2 puts examples in 'examples' list in JSON schema
        assert 'examples' in prop_data, f"Field '{prop_name}' in model '{model.__name__}' is missing examples"
