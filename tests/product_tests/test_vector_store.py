import pytest
from unittest.mock import MagicMock, patch
from product.bsp_agent.core.vector_store import VectorStoreManager
from product.bsp_agent.core.ingestion import DatasheetIngestor
from studio.config import get_settings
import os
import shutil

@pytest.fixture
def temp_vector_store(tmp_path):
    test_path = str(tmp_path / "vector_store")
    return test_path

@patch("product.bsp_agent.core.vector_store.VertexAIEmbeddings")
def test_vector_store_initialization(mock_embeddings, temp_vector_store):
    # Setup mock
    mock_embeddings.return_value = MagicMock()

    manager = VectorStoreManager(persist_directory=temp_vector_store)
    assert manager.vector_store is not None
    assert os.path.exists(temp_vector_store)

@patch("product.bsp_agent.core.vector_store.VertexAIEmbeddings")
def test_vector_store_add_and_search(mock_embeddings, temp_vector_store):
    # Setup mock
    mock_instance = MagicMock()
    # Mock embed_documents to return a fixed size vector (768)
    mock_instance.embed_documents.return_value = [[0.1] * 768] * 2
    mock_instance.embed_query.return_value = [0.1] * 768
    mock_embeddings.return_value = mock_instance

    manager = VectorStoreManager(persist_directory=temp_vector_store)
    texts = ["Android BSP stands for Board Support Package", "The kernel is the core of the OS"]
    metadatas = [{"source": "doc1"}, {"source": "doc2"}]

    manager.add_texts(texts, metadatas)

    # Similarity search should work with the mock
    results = manager.search("What is BSP?")
    assert len(results) > 0

@pytest.mark.asyncio
@patch("product.bsp_agent.core.vector_store.VertexAIEmbeddings")
@patch("product.bsp_agent.core.ingestion.PyPDFLoader")
async def test_datasheet_ingestor(mock_pdf_loader, mock_embeddings, temp_vector_store):
    # Setup mock embeddings
    mock_emb_instance = MagicMock()
    mock_emb_instance.embed_documents.return_value = [[0.1] * 768]
    mock_emb_instance.embed_query.return_value = [0.1] * 768
    mock_embeddings.return_value = mock_emb_instance

    # Setup mock PDF loader
    mock_loader_instance = mock_pdf_loader.return_value
    mock_doc = MagicMock()
    mock_doc.page_content = "This is a datasheet content about Qualcomm PMIC."
    mock_doc.metadata = {"source": "test.pdf", "page": 1}
    mock_loader_instance.load.return_value = [mock_doc]

    manager = VectorStoreManager(persist_directory=temp_vector_store)
    ingestor = DatasheetIngestor(vector_store_manager=manager)

    num_docs = await ingestor.ingest_pdf("test.pdf")
    assert num_docs > 0

    # Search should find it
    results = manager.search("PMIC")
    assert len(results) > 0
