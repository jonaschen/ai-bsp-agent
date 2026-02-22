from product.bsp_agent.core.vector_store import VectorStoreManager

class HardwareAdvisorAgent:
    def __init__(self):
        self.vector_store_manager = VectorStoreManager()

    def get_spec(self, component_query: str):
        """Retrieve specifications for a given component or query from the vector store."""
        results = self.vector_store_manager.search(component_query)
        if not results:
            return "No specifications found for the given query."

        # Format the results
        formatted_results = []
        for doc in results:
            source = doc.metadata.get('source', 'Unknown')
            formatted_results.append(f"--- Source: {source} ---\n{doc.page_content}")

        return "\n\n".join(formatted_results)
