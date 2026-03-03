import os
import json
import asyncio
import logging
from typing import List
from langchain_core.documents import Document
from product.schemas.datasheet import Datasheet
from langchain_google_vertexai import VectorSearchVectorStore, VertexAIEmbeddings
from studio.config import get_settings

logger = logging.getLogger("product.bsp_agent.core.ingestion")

def process_datasheet(filepath: str) -> Document:
    """Parses a datasheet JSON and prepares it for vectorization."""
    with open(filepath, "r") as f:
        data = json.load(f)

    # Validate against schema
    datasheet = Datasheet(**data)

    # Concatenation strategy per PRODUCT_BLUEPRINT.md and datasheet.py
    # strategy: component_type + part_number + manufacturer + interfaces + content
    interfaces_str = ", ".join(datasheet.metadata.interfaces)

    # We create a rich content string for the vector embedding
    vector_content = (
        f"Component: {datasheet.metadata.component_type}\n"
        f"Part Number: {datasheet.metadata.part_number}\n"
        f"Manufacturer: {datasheet.metadata.manufacturer}\n"
        f"Interfaces: {interfaces_str}\n"
        f"Summary: {datasheet.content}"
    )

    return Document(
        page_content=vector_content,
        metadata=datasheet.metadata.model_dump()
    )

def _ingest_sync(directory: str, settings, embeddings):
    """Synchronous helper for ingestion to be run in a thread."""
    documents = []
    for filename in os.listdir(directory):
        if filename.endswith(".json"):
            filepath = os.path.join(directory, filename)
            try:
                doc = process_datasheet(filepath)
                documents.append(doc)
                logger.info(f"Processed {filename}")
            except Exception as e:
                logger.error(f"Failed to process {filename}: {e}")

    if not documents:
        logger.warning("No valid datasheets found for ingestion.")
        return

    if settings.vector_search_index_id and settings.vector_search_endpoint_id and settings.vector_search_gcs_bucket:
        # We first instantiate the vector store via from_components, then add documents.
        # This is a robust way to ensure we're using the correct index/endpoint.
        vs = VectorSearchVectorStore.from_components(
            project_id=settings.google_cloud_project,
            region=settings.google_cloud_region,
            index_id=settings.vector_search_index_id,
            endpoint_id=settings.vector_search_endpoint_id,
            embedding=embeddings,
            gcs_bucket_name=settings.vector_search_gcs_bucket
        )
        vs.add_documents(documents)
        logger.info(f"Successfully triggered indexing for {len(documents)} documents.")
    else:
        logger.error("Indexing skipped: Vector Search IDs not configured in settings.")

async def ingest_datasheets(directory: str = "fixtures/datasheets/"):
    """Ingests all JSON datasheets from a directory into Vertex Search."""
    settings = get_settings()
    embeddings = VertexAIEmbeddings(
        model_name=settings.embedding_model,
        project=settings.google_cloud_project
    )

    # Run blocking I/O in a separate thread to avoid blocking the event loop
    await asyncio.to_thread(_ingest_sync, directory, settings, embeddings)
