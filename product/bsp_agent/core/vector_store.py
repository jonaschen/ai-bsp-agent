from langchain_chroma import Chroma
from langchain_google_vertexai import VertexAIEmbeddings, VectorSearchVectorStore
from studio.config import get_settings
from typing import List, Optional, Dict
import os

class VectorStoreManager:
    """
    Manages the Vector Database for hardware datasheets.
    Supports Chroma (local) and Vertex AI Vector Search (cloud).
    """
    def __init__(self, collection_name: str = "bsp_datasheets"):
        settings = get_settings()
        self.settings = settings
        self.collection_name = collection_name

        self.embeddings = VertexAIEmbeddings(
            model_name=settings.embedding_model,
            project=settings.google_cloud_project
        )

        if settings.vector_store_type == "vertex_ai":
            if not settings.vertex_ai_index_id or not settings.vertex_ai_endpoint_id:
                raise ValueError("Vertex AI Vector Search requires index_id and endpoint_id")

            self.vector_store = VectorSearchVectorStore(
                project=settings.google_cloud_project,
                location=settings.vertex_ai_region,
                index_id=settings.vertex_ai_index_id,
                endpoint_id=settings.vertex_ai_endpoint_id,
                embedding=self.embeddings
            )
        else:
            # Default to Chroma
            self.persist_directory = settings.vector_store_path
            if not os.path.exists(self.persist_directory):
                os.makedirs(self.persist_directory, exist_ok=True)

            self.vector_store = Chroma(
                collection_name=self.collection_name,
                embedding_function=self.embeddings,
                persist_directory=self.persist_directory
            )

    async def add_texts(self, texts: List[str], metadatas: Optional[List[Dict]] = None):
        """Asynchronously add texts to the vector store."""
        return await self.vector_store.aadd_texts(texts=texts, metadatas=metadatas)

    async def add_documents(self, documents: List):
        """Asynchronously add documents to the vector store."""
        return await self.vector_store.aadd_documents(documents)

    async def similarity_search(self, query: str, k: int = 4):
        """Asynchronously search for similar documents."""
        return await self.vector_store.asimilarity_search(query, k=k)
