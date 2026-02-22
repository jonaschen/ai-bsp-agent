import pytest
from unittest.mock import MagicMock, patch
import os

def test_vector_store_manager_initialization(tmp_path, monkeypatch):
    """Test that VectorStoreManager initializes correctly."""
    from product.bsp_agent.core.vector_store import VectorStoreManager
    from studio.config import get_settings

    # Use tmp_path to avoid creating real directories on disk
    test_persist_dir = str(tmp_path / "vector_store")

    # Patch the settings instance
    settings = get_settings()
    monkeypatch.setattr(settings, "vector_store_path", test_persist_dir)

    with patch("product.bsp_agent.core.vector_store.VertexAIEmbeddings") as mock_embeddings:
        manager = VectorStoreManager()
        assert manager is not None
        assert manager.persist_directory == test_persist_dir
        mock_embeddings.assert_called_once()

def test_vector_store_manager_add_and_query(tmp_path):
    """Test adding documents and querying the vector store."""
    from product.bsp_agent.core.vector_store import VectorStoreManager

    test_persist_dir = str(tmp_path / "vector_store_query")

    with patch("product.bsp_agent.core.vector_store.VertexAIEmbeddings") as mock_embeddings, \
         patch("studio.config.get_settings") as mock_get_settings:

        # Mock settings
        mock_settings = MagicMock()
        mock_settings.vector_store_path = test_persist_dir
        mock_settings.google_cloud_project = "test-project"
        mock_get_settings.return_value = mock_settings

        mock_emb_instance = MagicMock()
        # Mock embed_documents to return a list of floats for each input text
        mock_emb_instance.embed_documents.return_value = [[0.1, 0.2, 0.3]]
        mock_emb_instance.embed_query.return_value = [0.1, 0.2, 0.3]
        mock_embeddings.return_value = mock_emb_instance

        manager = VectorStoreManager()

        manager.add_texts(["This is a test document about PMIC."], ids=["doc1"])
        results = manager.similarity_search("PMIC voltage")

        assert len(results) > 0
        assert "PMIC" in results[0].page_content
