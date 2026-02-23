import asyncio
from typing import List
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from product.bsp_agent.core.vector_store import VectorStoreManager

class DatasheetIngestor:
    """
    Handles ingestion of datasheet files into the Vector Store.
    """
    def __init__(self):
        self.vector_store_manager = VectorStoreManager()
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )

    async def ingest_pdf(self, filepath: str):
        """
        Asynchronously loads, splits, and adds a PDF datasheet to the vector store.
        """
        # Load PDF in a separate thread to avoid blocking the event loop
        loader = PyPDFLoader(filepath)
        docs = await asyncio.to_thread(loader.load)

        # Split documents
        split_docs = self.text_splitter.split_documents(docs)

        # Add to vector store
        await self.vector_store_manager.add_documents(split_docs)

        return len(split_docs)
