import pytest
from unittest.mock import MagicMock, patch
from product.bsp_agent.core.ingestion import DatasheetIngestor

def test_datasheet_ingestor_initialization():
    """Test that DatasheetIngestor initializes correctly."""
    ingestor = DatasheetIngestor()
    assert ingestor is not None

def test_datasheet_ingestor_ingest_pdf():
    """Test ingesting a PDF file."""
    with patch("product.bsp_agent.core.ingestion.PyPDFLoader") as mock_loader, \
         patch("product.bsp_agent.core.ingestion.RecursiveCharacterTextSplitter") as mock_splitter:

        mock_loader_instance = MagicMock()
        mock_loader.return_value = mock_loader_instance
        mock_loader_instance.load.return_value = [MagicMock(page_content="page1"), MagicMock(page_content="page2")]

        mock_splitter_instance = MagicMock()
        mock_splitter.return_value = mock_splitter_instance
        mock_splitter_instance.split_documents.return_value = [MagicMock(page_content="chunk1"), MagicMock(page_content="chunk2")]

        ingestor = DatasheetIngestor()
        chunks = ingestor.ingest_pdf("mock.pdf")

        assert len(chunks) == 2
        assert chunks[0].page_content == "chunk1"
        mock_loader.assert_called_once_with("mock.pdf")
        mock_splitter_instance.split_documents.assert_called_once()
