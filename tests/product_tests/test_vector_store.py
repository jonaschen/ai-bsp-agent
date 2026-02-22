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

        await manager.aadd_texts(texts, metadatas=metadatas)

        # Search for PMIC (should match the first text with [0.1...])
        results = await manager.asimilarity_search("PMIC voltage", k=1)

        assert len(results) > 0
        # Since [0.1]*10 is exactly the same as the first doc's embedding, it should be the top result
        assert "PMIC" in results[0].page_content
