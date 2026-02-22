from langchain_chroma import Chroma
from langchain_google_vertexai import VertexAIEmbeddings
from studio.config import get_settings
from typing import List, Optional

class VectorStoreManager:
    def __init__(self, persist_directory: Optional[str] = None):
        settings = get_settings()
        self.persist_directory = persist_directory or settings.vector_store_path

        # Initialize embeddings with the specific model requested
        self.embeddings = VertexAIEmbeddings(
            model_name="textembedding-gecko@003",
            project=settings.google_cloud_project
        )

        # Initialize Chroma vector store
        self.vector_store = Chroma(
            persist_directory=self.persist_directory,
            embedding_function=self.embeddings,
            collection_name="bsp_datasheets"
        )

    def add_texts(self, texts: List[str], metadatas: Optional[List[dict]] = None):
        """Adds texts to the vector store."""
        return self.vector_store.add_texts(texts=texts, metadatas=metadatas)

    def query(self, query: str, k: int = 4):
        """Performs a similarity search."""
        return self.vector_store.similarity_search(query, k=k)

    def get_retriever(self):
        """Returns the retriever interface of the vector store."""
        return self.vector_store.as_retriever()
