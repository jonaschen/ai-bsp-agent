import pytest
from unittest.mock import MagicMock, patch

# Now that node_qa_verifier installs requirements.txt, we can use top-level imports.
# This satisfies the architectural preference for clean tests.
from product.bsp_agent.core.vector_store import VectorStoreManager
from product.bsp_agent.core.ingestion import DatasheetIngestor
from product.bsp_agent.agents.hardware_advisor import HardwareAdvisorAgent

@pytest.fixture
def mock_vsm_deps():
    """Provides a context where heavy vector store dependencies are mocked."""
    # We still mock these to avoid needing real API keys or DB setup during unit tests.
    with patch("product.bsp_agent.core.vector_store.Chroma") as mock_chroma, \
         patch("product.bsp_agent.core.vector_store.VertexAIEmbeddings") as mock_embeddings:
        yield {"chroma": mock_chroma, "embeddings": mock_embeddings}

def test_vector_store_manager_initialization(mock_vsm_deps):
    manager = VectorStoreManager()
    assert manager is not None
    mock_vsm_deps["chroma"].assert_called_once()
    mock_vsm_deps["embeddings"].assert_called_once()

@pytest.mark.asyncio
async def test_datasheet_ingestor_load():
    with patch("product.bsp_agent.core.ingestion.VectorStoreManager") as mock_vsm_class:
        mock_vsm_instance = mock_vsm_class.return_value

        ingestor = DatasheetIngestor()
        # Mock the text_splitter instance created in __init__
        ingestor.text_splitter = MagicMock()

        # Mock loader and documents
        with patch("product.bsp_agent.core.ingestion.PyPDFLoader") as mock_loader:
            mock_doc = MagicMock()
            mock_loader.return_value.load_and_split.return_value = [mock_doc]
            ingestor.text_splitter.split_documents.return_value = [mock_doc]

            await ingestor.ingest_pdf("pmic.pdf")

            # Verify it was added to the vector store
            mock_vsm_instance.add_documents.assert_called_once_with([mock_doc])

def test_hardware_advisor_retrieval():
    with patch("product.bsp_agent.agents.hardware_advisor.VectorStoreManager") as mock_vsm_class:
        mock_vsm_instance = mock_vsm_class.return_value
        mock_vsm_instance.search.return_value = [
            MagicMock(page_content="DRAM Refresh: 64ms", metadata={"source": "dram.pdf"})
        ]

        agent = HardwareAdvisorAgent()
        response = agent.get_spec("DRAM Refresh")
        assert "64ms" in response
        mock_vsm_instance.search.assert_called_with("DRAM Refresh")
