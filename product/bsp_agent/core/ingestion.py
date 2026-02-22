import asyncio
import logging
import os
from typing import List
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from product.bsp_agent.core.vector_store import VectorStoreManager

logger = logging.getLogger(__name__)

class DatasheetIngestor:
    def __init__(self, vector_store_manager: VectorStoreManager):
        self.vsm = vector_store_manager
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )

    async def ingest_pdf(self, file_path: str):
        """Ingests a PDF file into the vector store asynchronously."""
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            raise FileNotFoundError(f"Datasheet PDF not found at {file_path}")

        try:
            # Use asyncio.to_thread for non-blocking PDF loading and splitting
            docs = await asyncio.to_thread(self._load_and_split, file_path)

            if not docs:
                logger.warning(f"No content extracted from {file_path}")
                return 0

            texts = [doc.page_content for doc in docs]
            metadatas = [doc.metadata for doc in docs]

            # Add to vector store
            await asyncio.to_thread(self.vsm.add_texts, texts, metadatas)
            logger.info(f"Successfully ingested {len(docs)} chunks from {file_path}")
            return len(docs)
        except Exception as e:
            logger.exception(f"Failed to ingest PDF {file_path}: {e}")
            raise RuntimeError(f"Failed to process datasheet {file_path}: {e}") from e

    def _load_and_split(self, file_path: str):
        loader = PyPDFLoader(file_path)
        return loader.load_and_split(text_splitter=self.splitter)
