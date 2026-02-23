import pytest
import os
from unittest.mock import MagicMock, patch
from product.bsp_agent.core.vector_store import VectorStoreManager

@pytest.fixture
def temp_vector_store(tmp_path):
    # Use a temporary directory for the vector store
    test_path = str(tmp_path / "test_vector_store")
    return test_path

@pytest.mark.asyncio
async def test_vector_store_manager_init(temp_vector_store):
    # Mock settings and embeddings where they are used
    with patch("product.bsp_agent.core.vector_store.get_settings") as mock_get_settings, \
         patch("product.bsp_agent.core.vector_store.VertexAIEmbeddings") as mock_embeddings:
        mock_settings = MagicMock()
        mock_settings.vector_store_path = temp_vector_store
        mock_settings.google_cloud_project = "test-project"
        mock_settings.embedding_model = "test-model"
        mock_get_settings.return_value = mock_settings

        manager = VectorStoreManager()
        assert manager is not None
        assert manager.persist_directory == temp_vector_store
        mock_embeddings.assert_called_once_with(
            model_name="test-model",
            project="test-project"
        )

@pytest.mark.asyncio
async def test_vector_store_manager_add_and_search(temp_vector_store):
    # Mock settings and embeddings
    with patch("product.bsp_agent.core.vector_store.get_settings") as mock_get_settings, \
         patch("product.bsp_agent.core.vector_store.VertexAIEmbeddings") as mock_embeddings:

        mock_settings = MagicMock()
        mock_settings.vector_store_path = temp_vector_store
        mock_settings.google_cloud_project = "test-project"
        mock_settings.embedding_model = "test-model"
        mock_get_settings.return_value = mock_settings

        # We need a mock embeddings instance that Chroma can use
        mock_emb_inst = MagicMock()
        # Chroma expects embedding functions to have embed_documents and embed_query
        # Use different embeddings to ensure deterministic search if Chroma uses them
        def embed_docs(texts):
            return [[0.1 * (i+1)] * 10 for i, t in enumerate(texts)]
        mock_emb_inst.embed_documents.side_effect = embed_docs
        mock_emb_inst.embed_query.return_value = [0.1] * 10
        mock_embeddings.return_value = mock_emb_inst

        manager = VectorStoreManager()

        # Sample data
        texts = ["The PMIC voltage should be 1.8V", "DRAM refresh rate is 64ms"]
        metadatas = [{"source": "pmic_spec.pdf"}, {"source": "dram_spec.pdf"}]

        await manager.add_texts(texts, metadatas=metadatas)

        # Search for PMIC (should match the first text with [0.1...])
        results = await manager.similarity_search("PMIC voltage", k=1)

        assert len(results) > 0
        # Since [0.1]*10 is exactly the same as the first doc's embedding, it should be the top result
        assert "PMIC" in results[0].page_content

@pytest.mark.asyncio
async def test_vector_store_persistence(temp_vector_store):
    # Mock settings and embeddings
    with patch("product.bsp_agent.core.vector_store.get_settings") as mock_get_settings, \
         patch("product.bsp_agent.core.vector_store.VertexAIEmbeddings") as mock_embeddings:

        mock_settings = MagicMock()
        mock_settings.vector_store_path = temp_vector_store
        mock_settings.google_cloud_project = "test-project"
        mock_settings.embedding_model = "test-model"
        mock_get_settings.return_value = mock_settings

        mock_emb_inst = MagicMock()
        mock_emb_inst.embed_documents.return_value = [[0.1] * 10]
        mock_emb_inst.embed_query.return_value = [0.1] * 10
        mock_embeddings.return_value = mock_emb_inst

        # Instance 1: Add data
        manager1 = VectorStoreManager()
        await manager1.add_texts(["Persistent Data"], metadatas=[{"id": 1}])

    # Instance 2: Retrieve data (re-mocking to ensure separate instance)
    with patch("product.bsp_agent.core.vector_store.get_settings") as mock_get_settings, \
         patch("product.bsp_agent.core.vector_store.VertexAIEmbeddings") as mock_embeddings:

        mock_settings = MagicMock()
        mock_settings.vector_store_path = temp_vector_store
        mock_settings.google_cloud_project = "test-project"
        mock_settings.embedding_model = "test-model"
        mock_get_settings.return_value = mock_settings

        mock_emb_inst = MagicMock()
        mock_emb_inst.embed_documents.return_value = [[0.1] * 10]
        mock_emb_inst.embed_query.return_value = [0.1] * 10
        mock_embeddings.return_value = mock_emb_inst

        manager2 = VectorStoreManager()
        results = await manager2.similarity_search("Persistent", k=1)

        assert len(results) > 0
        assert "Persistent Data" in results[0].page_content

@pytest.mark.asyncio
async def test_invalid_settings():
    """Test behavior when settings are invalid."""
    with patch("product.bsp_agent.core.vector_store.get_settings") as mock_get_settings:
        mock_settings = MagicMock()
        mock_settings.vector_store_path = "/tmp/invalid_path"
        mock_settings.google_cloud_project = None # Invalid
        mock_settings.embedding_model = None # Invalid
        mock_get_settings.return_value = mock_settings

        # VertexAIEmbeddings usually raises error if project or model is None
        with patch("product.bsp_agent.core.vector_store.VertexAIEmbeddings", side_effect=ValueError("Invalid config")):
            with pytest.raises(ValueError, match="Invalid config"):
                VectorStoreManager()

@pytest.mark.asyncio
async def test_vector_store_manager_init_vertex_ai():
    # Mock settings to use vertex_ai
    with patch("product.bsp_agent.core.vector_store.get_settings") as mock_get_settings, \
         patch("product.bsp_agent.core.vector_store.VertexAIEmbeddings"), \
         patch("product.bsp_agent.core.vector_store.VectorSearchVectorStore") as mock_vertex_vs:

        mock_settings = MagicMock()
        mock_settings.vector_store_type = "vertex_ai"
        mock_settings.google_cloud_project = "test-project"
        mock_settings.embedding_model = "test-model"
        mock_settings.vertex_ai_index_id = "test-index"
        mock_settings.vertex_ai_endpoint_id = "test-endpoint"
        mock_settings.vertex_ai_region = "us-central1"
        mock_get_settings.return_value = mock_settings

        manager = VectorStoreManager()
        assert manager is not None
        mock_vertex_vs.assert_called_once()
