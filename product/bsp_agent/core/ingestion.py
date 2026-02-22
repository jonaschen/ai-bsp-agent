from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from product.bsp_agent.core.vector_store import VectorStoreManager
import asyncio
from typing import Optional

class DatasheetIngestor:
    """
    Handles ingestion of PDF datasheets into the vector store.
    """
    def __init__(self, vector_store_manager: Optional[VectorStoreManager] = None):
        self.vector_store_manager = vector_store_manager or VectorStoreManager()
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=100
        )

    async def ingest_pdf(self, file_path: str):
        """
        Ingests a PDF file into the vector store asynchronously.
        """
        # Run synchronous PDF loading and splitting in a separate thread
        documents = await asyncio.to_thread(self._load_and_split, file_path)

        # Add to vector store
        self.vector_store_manager.add_documents(documents)
        return len(documents)

    def _load_and_split(self, file_path: str):
        loader = PyPDFLoader(file_path)
        docs = loader.load()
        return self.text_splitter.split_documents(docs)
