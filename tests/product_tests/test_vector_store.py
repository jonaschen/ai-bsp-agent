import pytest
from unittest.mock import MagicMock, patch
import os

# We need to ensure we patch the classes where they are USED
@pytest.fixture
def mock_vector_store_manager():
    with patch("product.bsp_agent.core.ingestion.VectorStoreManager") as mock_ingest_vsm, \
         patch("product.bsp_agent.agents.hardware_advisor.VectorStoreManager") as mock_agent_vsm:
        # Both should point to the same mock instance for consistency in tests if needed
        mock_vsm_instance = MagicMock()
        mock_ingest_vsm.return_value = mock_vsm_instance
        mock_agent_vsm.return_value = mock_vsm_instance
        yield mock_vsm_instance

def test_vector_store_manager_initialization():
    with patch("langchain_google_vertexai.VertexAIEmbeddings", create=True), \
         patch("langchain_chroma.Chroma", create=True):
        from product.bsp_agent.core.vector_store import VectorStoreManager
        manager = VectorStoreManager()
        assert manager is not None
        assert hasattr(manager, "vector_store")

@pytest.mark.asyncio
async def test_datasheet_ingestor_load(mock_vector_store_manager):
    from product.bsp_agent.core.ingestion import DatasheetIngestor

    with patch("product.bsp_agent.core.ingestion.PyPDFLoader") as mock_loader:
        mock_loader.return_value.load_and_split.return_value = [
            MagicMock(page_content="PMIC voltage: 1.8V", metadata={"source": "pmic.pdf"})
        ]

        ingestor = DatasheetIngestor()
        await ingestor.ingest_pdf("pmic.pdf")

        # Verify it was added to the vector store
        mock_vector_store_manager.add_documents.assert_called()

def test_hardware_advisor_retrieval(mock_vector_store_manager):
    from product.bsp_agent.agents.hardware_advisor import HardwareAdvisorAgent

    mock_vector_store_manager.search.return_value = [
        MagicMock(page_content="DRAM Refresh: 64ms", metadata={"source": "dram.pdf"})
    ]

    agent = HardwareAdvisorAgent()
    response = agent.get_spec("DRAM Refresh")
    assert "64ms" in response
    mock_vector_store_manager.search.assert_called_with("DRAM Refresh")
