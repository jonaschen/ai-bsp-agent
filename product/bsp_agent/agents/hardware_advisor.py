from product.bsp_agent.core.vector_store import VectorStoreManager

class HardwareAdvisorAgent:
    def __init__(self, vector_store_manager: VectorStoreManager):
        self.vsm = vector_store_manager

    def get_spec(self, component_name: str) -> str:
        """Retrieves and formats component specifications from the vector store."""
        query = f"Specifications for {component_name}"
        docs = self.vsm.query(query, k=2)

        if not docs:
            return f"No specifications found for {component_name}."

        specs = []
        for doc in docs:
            specs.append(f"Source: {doc.metadata.get('source', 'Unknown')}\nContent: {doc.page_content}")

        return "\n---\n".join(specs)
