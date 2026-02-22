import os
from typing import List, Optional
from langchain_chroma import Chroma
from langchain_google_vertexai import VertexAIEmbeddings
from studio.config import get_settings

class VectorStoreManager:
    """
    Manages the Vector Store for indexing and retrieving datasheets.
    """
    def __init__(self, collection_name: str = "datasheets"):
        settings = get_settings()
        self.embeddings = VertexAIEmbeddings(
            model_name="textembedding-gecko@003",
            project=settings.google_cloud_project
        )
        self.persist_directory = settings.vector_store_path

        # Ensure the directory exists
        if not os.path.exists(self.persist_directory):
            os.makedirs(self.persist_directory, exist_ok=True)

        self.vector_store = Chroma(
            collection_name=collection_name,
            embedding_function=self.embeddings,
            persist_directory=self.persist_directory
        )

    def add_texts(self, texts: List[str], metadatas: Optional[List[dict]] = None, ids: Optional[List[str]] = None):
        """Adds texts to the vector store."""
        return self.vector_store.add_texts(texts=texts, metadatas=metadatas, ids=ids)

    def similarity_search(self, query: str, k: int = 4):
        """Performs a similarity search."""
        return self.vector_store.similarity_search(query, k=k)

    def delete_collection(self):
        """Deletes the current collection."""
        self.vector_store.delete_collection()
