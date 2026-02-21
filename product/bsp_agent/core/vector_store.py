from langchain_chroma import Chroma
from langchain_google_vertexai import VertexAIEmbeddings
from studio.config import get_settings
import os

class VectorStoreManager:
    """
    Manages the lifecycle of the Vector Store used for RAG.
    Initializes Chroma with VertexAI embeddings.
    """
    def __init__(self, persist_directory: str = None):
        settings = get_settings()
        self.persist_directory = persist_directory or settings.vector_store_path

        # Ensure the directory exists
        if self.persist_directory:
            os.makedirs(self.persist_directory, exist_ok=True)

        self.embeddings = VertexAIEmbeddings(
            model_name="textembedding-gecko@003",
            project=settings.google_cloud_project
        )

        self.vector_store = Chroma(
            persist_directory=self.persist_directory,
            embedding_function=self.embeddings,
            collection_name="datasheets"
        )

    def get_retriever(self, search_kwargs: dict = None):
        """Returns a retriever interface for the vector store."""
        search_kwargs = search_kwargs or {"k": 5}
        return self.vector_store.as_retriever(search_kwargs=search_kwargs)
