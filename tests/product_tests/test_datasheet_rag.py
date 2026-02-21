import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from product.bsp_agent.core.vector_store import VectorStoreManager
from product.bsp_agent.core.ingestion import DatasheetIngestor
from langchain_core.documents import Document

@pytest.fixture
def mock_embeddings():
    embeddings = MagicMock()
    embeddings.embed_documents.side_effect = lambda texts: [[0.1] * 128 for _ in texts]
    embeddings.embed_query.return_value = [0.1] * 128
    return embeddings

@pytest.fixture
def temp_pdf(tmp_path):
    pdf_path = tmp_path / "test_datasheet.pdf"
    # Create a dummy PDF file
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with open(pdf_path, "wb") as f:
        writer.write(f)
    return pdf_path

def test_vector_store_initialization(mock_embeddings, tmp_path):
    manager = VectorStoreManager(embeddings=mock_embeddings, persist_directory=str(tmp_path))
    assert manager is not None

def test_ingestion_pipeline(mock_embeddings, temp_pdf, tmp_path):
    # Mocking PyPDFLoader to return controlled content since we created a blank PDF
    with patch("product.bsp_agent.core.ingestion.PyPDFLoader") as MockLoader:
        mock_loader = MockLoader.return_value
        mock_loader.load.return_value = [
            Document(page_content="PMIC Voltage Range: 1.2V to 1.8V", metadata={"source": str(temp_pdf)})
        ]

        manager = VectorStoreManager(embeddings=mock_embeddings, persist_directory=str(tmp_path))
        ingestor = DatasheetIngestor(vector_store_manager=manager)

        ingestor.ingest_pdf(str(temp_pdf))

        results = manager.search("PMIC Voltage")
        assert len(results) > 0
        assert "PMIC" in results[0].page_content
