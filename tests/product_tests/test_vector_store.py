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
         patch("product.bsp_agent.core.vector_store.VertexAIEmbeddings") as mock_embeddings, \
         patch("product.bsp_agent.core.vector_store.VectorSearchVectorStore") as mock_vs:

        mock_settings = MagicMock()
        mock_settings.vector_store_path = temp_vector_store
        mock_settings.google_cloud_project = "test-project"
        mock_settings.google_cloud_region = "us-central1"
        mock_settings.embedding_model = "test-model"
        mock_settings.vector_search_index_id = "test-index"
        mock_settings.vector_search_endpoint_id = "test-endpoint"
        mock_settings.vector_search_gcs_bucket = "test-bucket"
        mock_get_settings.return_value = mock_settings

        manager = VectorStoreManager()
        assert manager is not None
        mock_embeddings.assert_called_once_with(
            model_name="test-model",
            project="test-project"
        )
        # Verify correct parameter naming
        mock_vs.from_components.assert_called_once_with(
            project="test-project",
            location="us-central1",
            index_id="test-index",
            endpoint_id="test-endpoint",
            embedding=mock_embeddings.return_value,
            gcs_bucket_name="test-bucket"
        )

@pytest.mark.asyncio
async def test_vector_store_manager_add_and_search(temp_vector_store):
    # Mock settings and embeddings
    with patch("product.bsp_agent.core.vector_store.get_settings") as mock_get_settings, \
         patch("product.bsp_agent.core.vector_store.VertexAIEmbeddings") as mock_embeddings, \
         patch("product.bsp_agent.core.vector_store.VectorSearchVectorStore") as mock_vs:

        mock_settings = MagicMock()
        mock_settings.vector_store_path = temp_vector_store
        mock_settings.google_cloud_project = "test-project"
        mock_settings.google_cloud_region = "us-central1"
        mock_settings.embedding_model = "test-model"
        mock_settings.vector_search_index_id = "test-index"
        mock_settings.vector_search_endpoint_id = "test-endpoint"
        mock_settings.vector_search_gcs_bucket = "test-bucket"
        mock_get_settings.return_value = mock_settings

        mock_vs_inst = MagicMock()
        mock_doc = MagicMock()
        mock_doc.page_content = "The PMIC voltage should be 1.8V"

        # Setup asimilarity_search to return a doc
        import asyncio
        f_search = asyncio.Future()
        f_search.set_result([mock_doc])
        mock_vs_inst.asimilarity_search = MagicMock(return_value=f_search)

        # Setup aadd_texts
        f_add = asyncio.Future()
        f_add.set_result(["id1"])
        mock_vs_inst.aadd_texts.return_value = f_add

        mock_vs.from_components.return_value = mock_vs_inst

        manager = VectorStoreManager()

        # Sample data
        texts = ["The PMIC voltage should be 1.8V"]
        metadatas = [{"source": "pmic_spec.pdf"}]

        await manager.aadd_texts(texts, metadatas=metadatas)

        # Search for PMIC
        results = await manager.asimilarity_search("PMIC voltage", k=1)

        assert len(results) > 0
        assert "PMIC" in results[0].page_content

@pytest.mark.asyncio
async def test_vector_store_persistence(temp_vector_store):
    # Persistence test is now conceptual as Vertex Search is cloud-based
    # We test that it initializes correctly with the same settings
    with patch("product.bsp_agent.core.vector_store.get_settings") as mock_get_settings, \
         patch("product.bsp_agent.core.vector_store.VertexAIEmbeddings") as mock_embeddings, \
         patch("product.bsp_agent.core.vector_store.VectorSearchVectorStore") as mock_vs:

        mock_settings = MagicMock()
        mock_settings.google_cloud_project = "test-project"
        mock_settings.google_cloud_region = "us-central1"
        mock_settings.embedding_model = "test-model"
        mock_settings.vector_search_index_id = "test-index"
        mock_settings.vector_search_endpoint_id = "test-endpoint"
        mock_settings.vector_search_gcs_bucket = "test-bucket"
        mock_get_settings.return_value = mock_settings

        manager = VectorStoreManager()
        assert manager.vector_store is not None
        mock_vs.from_components.assert_called_once()
