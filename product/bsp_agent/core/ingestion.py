import asyncio
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from product.bsp_agent.core.vector_store import VectorStoreManager

class DatasheetIngestor:
    def __init__(self):
        self.vector_store_manager = VectorStoreManager()
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            separators=["\n\n", "\n", ".", "!", "?", " ", ""]
        )

    async def ingest_pdf(self, file_path: str):
        """Load, split, and ingest a PDF datasheet into the vector store."""
        loader = PyPDFLoader(file_path)

        # run synchronous load_and_split in a thread to avoid blocking the event loop
        documents = await asyncio.to_thread(loader.load_and_split)

        # Split documents
        split_docs = self.text_splitter.split_documents(documents)

        # add_documents is likely synchronous too in Chroma
        await asyncio.to_thread(self.vector_store_manager.add_documents, split_docs)

        return len(split_docs)
