from langchain_chroma import Chroma
from langchain_google_vertexai import VertexAIEmbeddings
from studio.config import get_settings
from typing import List, Optional
import os

class VectorStoreManager:
    """
    Manages the ChromaDB vector store for datasheet retrieval.
    Supports text embedding using Vertex AI textembedding-gecko@003.
    """
    def __init__(self, persist_directory: Optional[str] = None):
        settings = get_settings()
        self.persist_directory = persist_directory or settings.vector_store_path

        # Ensure the directory exists
        if not os.path.exists(self.persist_directory):
            os.makedirs(self.persist_directory, exist_ok=True)

        self.embeddings = VertexAIEmbeddings(
            model_name="textembedding-gecko@003",
            project=settings.google_cloud_project
        )

        self.vector_store = Chroma(
            persist_directory=self.persist_directory,
            embedding_function=self.embeddings,
            collection_name="bsp_datasheets"
        )

    def add_texts(self, texts: List[str], metadatas: Optional[List[dict]] = None):
        """Adds texts to the vector store."""
        self.vector_store.add_texts(texts=texts, metadatas=metadatas)

    def search(self, query: str, k: int = 4):
        """Performs a similarity search."""
        return self.vector_store.similarity_search(query, k=k)

    def add_documents(self, documents):
        """Adds LangChain documents to the vector store."""
        self.vector_store.add_documents(documents)
