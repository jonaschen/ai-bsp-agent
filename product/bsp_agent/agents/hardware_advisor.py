from typing import List
from product.bsp_agent.core.vector_store import VectorStoreManager

class HardwareAdvisorAgent:
    """
    Agent that provides hardware-specific advice based on datasheet retrieval.
    """
    def __init__(self):
        self.vector_store_manager = VectorStoreManager()

    async def get_spec(self, component_name: str) -> str:
        """
        Retrieves specification information for a given component.
        """
        query = f"{component_name} specification and requirements"
        results = await self.vector_store_manager.similarity_search(query, k=3)

        if not results:
            return f"No specification found for {component_name}."

        response = f"Specifications for {component_name}:\n"
        for i, doc in enumerate(results):
            source = doc.metadata.get("source", "Unknown")
            response += f"--- Source {i+1} ({source}) ---\n"
            response += doc.page_content + "\n"

        return response
