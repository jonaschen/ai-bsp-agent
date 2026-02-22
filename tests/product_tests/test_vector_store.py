import pytest
from unittest.mock import MagicMock, patch
from product.bsp_agent.core.vector_store import VectorStoreManager

@pytest.fixture
def mock_embeddings():
    with patch("product.bsp_agent.core.vector_store.VertexAIEmbeddings") as mock:
        mock_instance = MagicMock()
        mock_instance.embed_query.return_value = [0.1] * 768
        mock_instance.embed_documents.return_value = [[0.1] * 768]
        mock.return_value = mock_instance
        yield mock_instance

def test_vector_store_initialization(mock_embeddings, tmp_path):
    # Arrange
    persist_dir = str(tmp_path / "chroma_db")

    # Act
    vsm = VectorStoreManager(persist_directory=persist_dir)

    # Assert
    assert vsm.vector_store is not None
    assert vsm.persist_directory == persist_dir

def test_vector_store_add_and_query(mock_embeddings, tmp_path):
    # Arrange
    persist_dir = str(tmp_path / "chroma_db")
    vsm = VectorStoreManager(persist_directory=persist_dir)
    content = "The PMIC voltage for the SoC is 1.8V."
    metadata = {"source": "datasheet_abc.pdf"}

    # Act
    vsm.add_texts(texts=[content], metadatas=[metadata])
    results = vsm.query("What is the PMIC voltage?", k=1)

    # Assert
    assert len(results) > 0
    assert content in results[0].page_content
    assert results[0].metadata["source"] == "datasheet_abc.pdf"
