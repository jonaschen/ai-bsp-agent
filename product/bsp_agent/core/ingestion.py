from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from product.bsp_agent.core.vector_store import VectorStoreManager
import os

class DatasheetIngestor:
    """
    Handles ingestion of PDF datasheets into the vector store.
    """
    def __init__(self, vector_store_manager: VectorStoreManager):
        self.vector_store_manager = vector_store_manager
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=100,
            separators=["\n\n", "\n", " ", ""]
        )

    def ingest_pdf(self, pdf_path: str):
        """Loads a PDF, splits it into chunks, and adds it to the vector store."""
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        loader = PyPDFLoader(pdf_path)
        documents = loader.load()

        chunks = self.text_splitter.split_documents(documents)

        self.vector_store_manager.vector_store.add_documents(chunks)
        return len(chunks)
