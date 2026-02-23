import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from product.bsp_agent.core.ingestion import DatasheetIngestor
from product.bsp_agent.agents.hardware_advisor import HardwareAdvisorAgent
from langchain_core.documents import Document

@pytest.fixture
def mock_vector_store_ingestion():
    with patch("product.bsp_agent.core.ingestion.VectorStoreManager") as mock_vsm:
        instance = mock_vsm.return_value
        instance.add_documents = AsyncMock()
        yield instance

@pytest.fixture
def mock_vector_store_advisor():
    with patch("product.bsp_agent.agents.hardware_advisor.VectorStoreManager") as mock_vsm:
        instance = mock_vsm.return_value
        instance.similarity_search = AsyncMock()
        yield instance

@pytest.mark.asyncio
async def test_ingest_pdf(mock_vector_store_ingestion):
    # Mock PyPDFLoader
    with patch("product.bsp_agent.core.ingestion.PyPDFLoader") as mock_loader:
        mock_loader_inst = mock_loader.return_value
        mock_loader_inst.load.return_value = [
            Document(page_content="PMIC specs: 1.8V", metadata={"source": "test.pdf", "page": 1})
        ]

        ingestor = DatasheetIngestor()
        await ingestor.ingest_pdf("test.pdf")

        # Verify it was added to vector store
        assert mock_vector_store_ingestion.add_documents.called
        args, _ = mock_vector_store_ingestion.add_documents.call_args
        docs = args[0]
        assert len(docs) > 0
        assert "PMIC" in docs[0].page_content

@pytest.mark.asyncio
async def test_hardware_advisor_get_spec(mock_vector_store_advisor):
    mock_vector_store_advisor.similarity_search.return_value = [
        Document(page_content="The PMIC voltage is 1.8V", metadata={"source": "pmic.pdf"})
    ]

    advisor = HardwareAdvisorAgent()
    spec = await advisor.get_spec("PMIC")

    assert "1.8V" in spec
    assert "PMIC" in spec
    mock_vector_store_advisor.similarity_search.assert_called_with("PMIC specification and requirements", k=3)
