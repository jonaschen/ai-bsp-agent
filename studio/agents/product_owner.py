"""
studio/agents/product_owner.py
------------------------------
The Product Owner (PO) Agent.
Refactored based on Code Audit (2026-02-09).

Updates:
1. Schema Alignment: Accesses 'orchestration_layer' and 'task_queue'.
2. DAG Logic: Implements Topological Sort for dependencies.
3. Traceability: Adds 'source_section_id' to link tickets to Blueprint.

Dependencies:
- Vertex AI
- networkx (for DAG sorting)
- studio.memory
"""

import logging
import hashlib
from typing import List, Dict
from pydantic import BaseModel, Field

from langchain_google_vertexai import ChatVertexAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser

from studio.memory import Ticket

# We align the PO's view of a Ticket with the global memory schema.
# Note: The original snippet defined POTicket locally.
# We now use the global Ticket definition from studio.memory.
POTicket = Ticket

class BlueprintAnalysis(BaseModel):
    blueprint_version_hash: str
    summary_of_changes: str
    new_tickets: List[Ticket]
    deprecated_ticket_ids: List[str] = []

logger = logging.getLogger("studio.agents.po")

class ProductOwnerAgent:
    def __init__(self, model_name: str = "gemini-3.5-pro-preview"):
        self.llm = ChatVertexAI(
            model_name=model_name,
            temperature=0.1, # Minimized entropy for strict dependency logic
            location="global",
            max_output_tokens=8192
        )
        self.parser = PydanticOutputParser(pydantic_object=BlueprintAnalysis)

    def analyze_specs(self, blueprint_content: str, current_backlog_titles: List[str]) -> BlueprintAnalysis:
        """
        Analyzes the Blueprint and generates a Dependency-Aware Ticket Graph.
        """
        logger.info("Product Owner is analyzing Blueprint for DAG dependencies...")

        current_hash = hashlib.sha256(blueprint_content.encode()).hexdigest()

        prompt = ChatPromptTemplate.from_messages([
            ("system", """
            You are the Technical Product Owner.
            Your goal: Translate the Product Blueprint into a Directed Acyclic Graph (DAG) of Work Orders.

            CRITICAL RULES:
            1. **Traceability:** Every ticket MUST cite its `source_section_id` from the Blueprint.
            2. **Dependencies:** If Task B requires Task A (e.g., 'Install Docker' before 'Run Container'), list Task A's ID in Task B's `dependencies`.
            3. **Atomic Units:** Tickets must be implementable by a single Engineer agent.
            4. **No Duplicates:** Ignore these existing titles: {existing_titles}
            """),
            ("user", """
            Blueprint:
            ---
            {blueprint}
            ---

            Generate the Work Order JSON:
            {format_instructions}
            """)
        ])

        chain = prompt | self.llm | self.parser

        try:
            result = chain.invoke({
                "existing_titles": str(current_backlog_titles[:50]), # Truncate for context
                "blueprint": blueprint_content,
                "format_instructions": self.parser.get_format_instructions()
            })
            result.blueprint_version_hash = current_hash

            # Post-Process: Topological Sort
            sorted_tickets = self._sort_dag(result.new_tickets)
            result.new_tickets = sorted_tickets

            return result

        except Exception as e:
            logger.error(f"PO Analysis failed: {e}")
            raise e

    def _sort_dag(self, tickets: List[Ticket]) -> List[Ticket]:
        """
        Performs Topological Sort to ensure Parent tickets come before Children.
        """
        try:
            import networkx as nx
        except ImportError:
            # Fallback if networkx is missing in MVP
            logger.warning("NetworkX not found. Returning unsorted list.")
            return tickets

        graph = nx.DiGraph()
        ticket_map = {t.id: t for t in tickets}

        # Add nodes
        for t in tickets:
            graph.add_node(t.id)

        # Add edges (Dependency -> Ticket)
        for t in tickets:
            for dep_id in t.dependencies:
                if dep_id in ticket_map:
                    graph.add_edge(dep_id, t.id)

        try:
            # Return in execution order
            execution_order = list(nx.topological_sort(graph))
            # Validate IDs to prevent crash if graph contains external nodes
            return [ticket_map[tid] for tid in execution_order if tid in ticket_map]
        except nx.NetworkXUnfeasible:
            # Cycle detected
             logger.error("Circular dependency detected in PO suggestions! Returning unsorted list.")
             return tickets

# --- Integration Helper (Patched) ---

def run_po_cycle(orchestrator_state: Dict):
    """
    Executes the PO Cycle with corrected Schema Access.
    """
    try:
        with open("PRODUCT_BLUEPRINT.md", "r") as f:
            content = f.read()
    except FileNotFoundError:
        logger.error("Blueprint not found.")
        return []

    po = ProductOwnerAgent()

    # FIX: Access correct layer based on Audit Report
    # Note: We handle the case where state might be initialized differently in tests
    orch_layer = orchestrator_state.get("orchestration_layer", {})
    if not orch_layer:
        # Fallback to older schema for backward compatibility during migration
        orch_layer = orchestrator_state.get("orchestration", {})

    # Extract existing titles to prevent duplicates
    # We support both 'task_queue' (List) and 'tickets' (Dict) schemas
    task_queue = orch_layer.get("task_queue", [])

    existing_titles = []
    if isinstance(task_queue, dict):
        # Dictionary case: keys are IDs, values are tickets
        for t in task_queue.values():
             if hasattr(t, 'title'):
                existing_titles.append(t.title)
             elif isinstance(t, dict):
                existing_titles.append(t.get('title'))
    elif isinstance(task_queue, list):
        # List case
        for t in task_queue:
            if hasattr(t, 'title'):
                existing_titles.append(t.title)
            elif isinstance(t, dict):
                existing_titles.append(t.get('title'))

    analysis = po.analyze_specs(content, existing_titles)

    logger.info(f"PO Cycle: Generated {len(analysis.new_tickets)} tickets (DAG Sorted).")
    return analysis.new_tickets
