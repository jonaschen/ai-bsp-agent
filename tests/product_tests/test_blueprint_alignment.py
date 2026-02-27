import pytest
from pydantic import BaseModel
from product.schemas import (
    PathologistOutput,
    HardwareAdvisorOutput,
    ConsultantResponse,
    RCAReport,
    SupervisorInput
)

def test_pathologist_output_schema_alignment():
    # Should have confidence_score instead of confidence
    assert "confidence_score" in PathologistOutput.model_fields
    assert "confidence" not in PathologistOutput.model_fields

def test_hardware_advisor_output_schema_alignment():
    # Should have confidence_score instead of confidence
    assert "confidence_score" in HardwareAdvisorOutput.model_fields
    assert "confidence" not in HardwareAdvisorOutput.model_fields
    # Should have soa instead of soa_info
    assert "soa" in HardwareAdvisorOutput.model_fields
    assert "soa_info" not in HardwareAdvisorOutput.model_fields

def test_consultant_response_schema_alignment():
    # Should have confidence_score instead of confidence
    assert "confidence_score" in ConsultantResponse.model_fields
    assert "confidence" not in ConsultantResponse.model_fields

def test_rca_report_schema_alignment():
    # Should have confidence_score instead of confidence
    assert "confidence_score" in RCAReport.model_fields
    assert "confidence" not in RCAReport.model_fields

def test_schema_field_documentation():
    # Check that all models have examples in their fields
    models = [PathologistOutput, HardwareAdvisorOutput, ConsultantResponse, RCAReport, SupervisorInput]
    for model in models:
        for field_name, field in model.model_fields.items():
            assert field.examples is not None and len(field.examples) > 0, f"Field '{field_name}' in {model.__name__} is missing examples"
