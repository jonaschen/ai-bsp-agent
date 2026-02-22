from langchain_chroma import Chroma
from langchain_google_vertexai import VertexAIEmbeddings
from studio.config import get_settings
from typing import List, Optional, Dict
import os

class VectorStoreManager:
    """
    Manages the Vector Database for hardware datasheets.
    Uses Chroma for local persistence and Vertex AI for embeddings.
    """
    def __init__(self, collection_name: str = "bsp_datasheets"):
        settings = get_settings()
        self.persist_directory = settings.vector_store_path

        # Ensure the directory exists
        if not os.path.exists(self.persist_directory):
            os.makedirs(self.persist_directory, exist_ok=True)

        self.embeddings = VertexAIEmbeddings(
            model_name=settings.embedding_model,
            project=settings.google_cloud_project
        )
        self.collection_name = collection_name
        self.vector_store = Chroma(
            collection_name=self.collection_name,
            embedding_function=self.embeddings,
            persist_directory=self.persist_directory
        )

    async def aadd_texts(self, texts: List[str], metadatas: Optional[List[Dict]] = None):
        """Asynchronously add texts to the vector store."""
        return await self.vector_store.aadd_texts(texts=texts, metadatas=metadatas)

    async def asimilarity_search(self, query: str, k: int = 4):
        """Asynchronously search for similar documents."""
        return await self.vector_store.asimilarity_search(query, k=k)
