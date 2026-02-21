import pytest
from unittest.mock import MagicMock, patch
import os
from product.bsp_agent.core.vector_store import VectorStoreManager
from product.bsp_agent.core.ingestion import DatasheetIngestor

@pytest.fixture
def mock_embeddings():
    with patch("langchain_google_vertexai.VertexAIEmbeddings") as mock:
        yield mock

@pytest.fixture
def mock_chroma():
    with patch("product.bsp_agent.core.vector_store.Chroma") as mock:
        yield mock

def test_vector_store_initialization(tmp_path, mock_embeddings, mock_chroma):
    persist_dir = str(tmp_path / "chroma")
    manager = VectorStoreManager(persist_directory=persist_dir)
    assert manager.persist_directory == persist_dir
    assert manager.vector_store is not None
    mock_chroma.assert_called_once()

def test_datasheet_ingestion(tmp_path, mock_embeddings, mock_chroma):
    persist_dir = str(tmp_path / "chroma")
    manager = VectorStoreManager(persist_directory=persist_dir)
    # Mock the vector_store.add_documents
    manager.vector_store = MagicMock()

    ingestor = DatasheetIngestor(vector_store_manager=manager)

    # Create a dummy file to pass the os.path.exists check
    dummy_pdf = tmp_path / "test.pdf"
    dummy_pdf.write_text("dummy content")

    # Mock PyPDFLoader
    with patch("product.bsp_agent.core.ingestion.PyPDFLoader") as MockLoader:
        mock_loader = MockLoader.return_value
        mock_loader.load.return_value = [
            MagicMock(page_content="PMIC Datasheet Content", metadata={"source": str(dummy_pdf)})
        ]

        ingestor.ingest_pdf(str(dummy_pdf))

        assert manager.vector_store.add_documents.called
