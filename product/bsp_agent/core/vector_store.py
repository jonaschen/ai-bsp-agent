import os
from langchain_chroma import Chroma
from langchain_google_vertexai import VertexAIEmbeddings
from studio.config import get_settings

class VectorStoreManager:
    def __init__(self):
        settings = get_settings()
        self.embeddings = VertexAIEmbeddings(
            model_name="textembedding-gecko@003",
            project=settings.google_cloud_project
        )
        self.persist_directory = settings.vector_store_path

        # Ensure the directory exists
        os.makedirs(self.persist_directory, exist_ok=True)

        self.vector_store = Chroma(
            persist_directory=self.persist_directory,
            embedding_function=self.embeddings,
            collection_name="datasheets"
        )

    def search(self, query: str, k: int = 4):
        """Perform a similarity search in the vector store."""
        return self.vector_store.similarity_search(query, k=k)

    def add_documents(self, documents):
        """Add documents to the vector store."""
        self.vector_store.add_documents(documents)
