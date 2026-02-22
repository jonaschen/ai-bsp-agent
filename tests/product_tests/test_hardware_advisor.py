import pytest
from unittest.mock import MagicMock
from product.bsp_agent.agents.hardware_advisor import HardwareAdvisorAgent

def test_get_spec():
    # Arrange
    mock_vsm = MagicMock()
    mock_doc = MagicMock()
    mock_doc.page_content = "Voltage: 1.8V"
    mock_doc.metadata = {"source": "pmic_spec.pdf"}
    mock_vsm.query.return_value = [mock_doc]

    agent = HardwareAdvisorAgent(vector_store_manager=mock_vsm)

    # Act
    spec = agent.get_spec("PMIC")

    # Assert
    assert "Voltage: 1.8V" in spec
    assert "pmic_spec.pdf" in spec
    mock_vsm.query.assert_called_with("Specifications for PMIC", k=2)

def test_get_spec_no_results():
    # Arrange
    mock_vsm = MagicMock()
    mock_vsm.query.return_value = []
    agent = HardwareAdvisorAgent(vector_store_manager=mock_vsm)

    # Act
    spec = agent.get_spec("UnknownComponent")

    # Assert
    assert "No specifications found" in spec
