from typing import List, Optional
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_chroma import Chroma

class VectorStoreManager:
    def __init__(
        self,
        embeddings: Embeddings,
        collection_name: str = "datasheets",
        persist_directory: Optional[str] = None
    ):
        self.embeddings = embeddings
        self.vector_store = Chroma(
            collection_name=collection_name,
            embedding_function=embeddings,
            persist_directory=persist_directory
        )

    def add_documents(self, documents: List[Document]):
        self.vector_store.add_documents(documents)

    def search(self, query: str, k: int = 4) -> List[Document]:
        return self.vector_store.similarity_search(query, k=k)

    def delete_collection(self):
        self.vector_store.delete_collection()
