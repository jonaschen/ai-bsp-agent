import pytest
import os
import time
import asyncio
from unittest.mock import MagicMock, patch
from product.bsp_agent.core.ingestion import ingest_datasheets
from product.bsp_agent.core.vector_store import VectorStoreManager

@pytest.fixture
def mock_vertex_settings():
    mock_settings = MagicMock()
    mock_settings.google_cloud_project = "test-project"
    mock_settings.google_cloud_region = "us-central1"
    mock_settings.embedding_model = "textembedding-gecko@003"
    mock_settings.vector_search_index_id = "test-index"
    mock_settings.vector_search_endpoint_id = "test-endpoint"
    mock_settings.vector_search_gcs_bucket = "test-bucket"

    # Patch get_settings to return the same mock instance everywhere
    with patch("product.bsp_agent.core.ingestion.get_settings", return_value=mock_settings), \
         patch("product.bsp_agent.core.vector_store.get_settings", return_value=mock_settings):
        yield mock_settings

@pytest.mark.asyncio
async def test_datasheet_ingestion_pipeline(mock_vertex_settings):
    # Mock VertexSearchVectorStore and embeddings where they are imported
    with patch("product.bsp_agent.core.ingestion.VectorSearchVectorStore") as mock_vs, \
         patch("product.bsp_agent.core.ingestion.VertexAIEmbeddings") as mock_emb:

        mock_vs_inst = MagicMock()
        mock_vs.from_components.return_value = mock_vs_inst

        fixture_path = "fixtures/datasheets/"
        assert os.path.exists(fixture_path)

        # Run ingestion
        await ingest_datasheets(fixture_path)

        # Verify that indexing was attempted correctly
        assert mock_vs.from_components.called
        assert mock_vs_inst.add_documents.called

        # Check if all 5 fixtures were processed
        documents = mock_vs_inst.add_documents.call_args[0][0]
        assert len(documents) == 5

@pytest.mark.asyncio
async def test_semantic_retrieval_relevance_and_latency(mock_vertex_settings):
    # Mock where they are used in vector_store.py
    with patch("product.bsp_agent.core.vector_store.VectorSearchVectorStore") as mock_vs, \
         patch("product.bsp_agent.core.vector_store.VertexAIEmbeddings") as mock_emb:

        mock_vs_inst = MagicMock()
        mock_doc = MagicMock()
        mock_doc.page_content = "PMIC TPS6594 voltage range 0.6V to 3.3V"
        mock_doc.metadata = {"part_number": "TPS6594", "component_type": "PMIC"}

        # Scenario: Library has asimilarity_search
        f = asyncio.Future()
        f.set_result([mock_doc])
        mock_vs_inst.asimilarity_search = MagicMock(return_value=f)

        mock_vs.from_components.return_value = mock_vs_inst

        manager = VectorStoreManager()

        # Measure latency
        start_time = time.time()
        results = await manager.search_components("voltage range for TPS6594")
        end_time = time.time()

        latency_ms = (end_time - start_time) * 1000

        # Acceptance Criteria: Latency < 500ms
        assert latency_ms < 500
        assert len(results) > 0
        assert "TPS6594" in results[0].page_content

@pytest.mark.asyncio
async def test_semantic_retrieval_fallback(mock_vertex_settings):
    # Mock where they are used in vector_store.py
    with patch("product.bsp_agent.core.vector_store.VectorSearchVectorStore") as mock_vs, \
         patch("product.bsp_agent.core.vector_store.VertexAIEmbeddings") as mock_emb:

        mock_vs_inst = MagicMock()
        mock_doc = MagicMock()
        mock_doc.page_content = "PMIC TPS6594 fallback"

        # Scenario: Library ONLY has similarity_search (sync)
        # We need to ensure asimilarity_search is NOT present on the mock
        del mock_vs_inst.asimilarity_search
        mock_vs_inst.similarity_search.return_value = [mock_doc]

        mock_vs.from_components.return_value = mock_vs_inst

        manager = VectorStoreManager()
        results = await manager.search_components("test fallback")

        assert len(results) > 0
        assert "fallback" in results[0].page_content
        assert mock_vs_inst.similarity_search.called
