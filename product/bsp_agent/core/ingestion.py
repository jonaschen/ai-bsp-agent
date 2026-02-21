from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from product.bsp_agent.core.vector_store import VectorStoreManager

class DatasheetIngestor:
    def __init__(
        self,
        vector_store_manager: VectorStoreManager,
        chunk_size: int = 1000,
        chunk_overlap: int = 200
    ):
        self.vector_store_manager = vector_store_manager
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )

    def ingest_pdf(self, file_path: str):
        loader = PyPDFLoader(file_path)
        documents = loader.load()
        split_docs = self.text_splitter.split_documents(documents)
        self.vector_store_manager.add_documents(split_docs)
