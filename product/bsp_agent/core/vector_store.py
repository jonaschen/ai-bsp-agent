import asyncio
import logging
from typing import List, Optional, Dict, Any
from langchain_google_vertexai import VertexAIEmbeddings, VectorSearchVectorStore
from studio.config import get_settings

logger = logging.getLogger("product.bsp_agent.core.vector_store")

class VectorStoreManager:
    """
    Manages the Vector Database for hardware datasheets.
    Uses Vertex Search (Vertex AI Vector Search) for cloud-native indexing.
    """
    def __init__(self):
        settings = get_settings()
        self.project = settings.google_cloud_project
        self.region = settings.google_cloud_region
        self.index_id = settings.vector_search_index_id
        self.endpoint_id = settings.vector_search_endpoint_id
        self.gcs_bucket = settings.vector_search_gcs_bucket
        self.embedding_model = settings.embedding_model

        self.embeddings = VertexAIEmbeddings(
            model_name=self.embedding_model,
            project=self.project
        )

        # In a real environment, index_id and endpoint_id must be provided
        # For testing/dev, we handle cases where they might be missing
        if self.index_id and self.endpoint_id and self.gcs_bucket:
            self.vector_store = VectorSearchVectorStore.from_components(
                project=self.project,
                location=self.region,
                index_id=self.index_id,
                endpoint_id=self.endpoint_id,
                embedding=self.embeddings,
                gcs_bucket_name=self.gcs_bucket
            )
        else:
            logger.warning("Vertex Vector Search configuration incomplete. VectorStore is in passive mode.")
            self.vector_store = None

    async def aadd_texts(self, texts: List[str], metadatas: Optional[List[Dict]] = None):
        """Asynchronously add texts to the vector store."""
        if not self.vector_store:
             raise ValueError("Vector store not initialized. Index/Endpoint missing.")

        # VertexSearchVectorStore's aadd_texts might not be fully async in all versions
        return await self.vector_store.aadd_texts(texts=texts, metadatas=metadatas)

    async def asimilarity_search(self, query: str, k: int = 4, **kwargs):
        """Asynchronously search for similar documents."""
        if not self.vector_store:
             logger.warning("Vector store not initialized. Returning empty results.")
             return []

        # NOTE: Some versions of VectorSearchVectorStore do not implement asimilarity_search
        # but only similarity_search. We handle both for robustness.
        if hasattr(self.vector_store, "asimilarity_search"):
            return await self.vector_store.asimilarity_search(query, k=k, **kwargs)
        else:
            return await asyncio.to_thread(self.vector_store.similarity_search, query, k=k, **kwargs)

    async def search_components(self, query: str, component_type: Optional[str] = None, part_number: Optional[str] = None, k: int = 4):
        """
        Hardware-specific semantic search with optional metadata filtering.

        Args:
            query: Semantic search query.
            component_type: Filter by component type (e.g., PMIC).
            part_number: Filter by part number (e.g., TPS6594).
            k: Number of results to return.
        """
        if not self.vector_store:
             logger.warning("Vector store not initialized. Returning empty results.")
             return []

        # Build filter if provided
        filters = {}
        if component_type:
            filters["component_type"] = component_type
        if part_number:
            filters["part_number"] = part_number

        if filters:
            # TODO: If simple dictionary filters fail, implement mapping to
            # langchain_google_vertexai.vectorstores.vectorstores.Namespace
            return await self.asimilarity_search(query, k=k, filter=filters)

        return await self.asimilarity_search(query, k=k)
