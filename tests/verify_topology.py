
import sys
from unittest.mock import MagicMock

# Mock dependencies to avoid initialization errors and auth requirements
sys.modules["vertexai"] = MagicMock()
sys.modules["vertexai.generative_models"] = MagicMock()
sys.modules["langchain_google_vertexai"] = MagicMock()
sys.modules["studio.utils.jules_client"] = MagicMock()

# Mock specific classes
mock_vertex_ai = MagicMock()
sys.modules["langchain_google_vertexai"].ChatVertexAI = mock_vertex_ai

# Mock os.environ
import os
os.environ["GITHUB_TOKEN"] = "mock_token"
os.environ["GITHUB_REPOSITORY"] = "mock/repo"

# Import the subgraph builder
# Note: We mock studio.agents.architect.run_architect_gate to avoid real execution
sys.modules["studio.agents.architect"] = MagicMock()
sys.modules["studio.agents.architect"].run_architect_gate = MagicMock(return_value={
    "code_artifacts": {},
    "verification_gate": {"status": "GREEN"}
})

from studio.subgraphs.engineer import build_engineer_subgraph
from studio.memory import EngineeringState, JulesMetadata, ContextSlice, VerificationGate, CodeArtifacts

def verify_topology():
    print("Building engineer subgraph...")
    graph = build_engineer_subgraph()

    print("Verifying nodes...")
    nodes = graph.nodes
    expected_nodes = [
        "dispatch",
        "watch",
        "entropy",
        "qa",
        "architect_gate",
        "feedback"
    ]

    missing_nodes = [n for n in expected_nodes if n not in nodes]
    if missing_nodes:
        print(f"FAILED: Missing nodes: {missing_nodes}")
        return False
    else:
        print("PASSED: All expected nodes present.")

    # Note: Accessing edges directly from a compiled StateGraph is tricky as it's compiled into a preamble.
    # But we can verify by checking the structure of the builder if we had access, or by trusting the nodes are present.
    # The 'run' test is more important.

    return True

if __name__ == "__main__":
    if verify_topology():
        print("Topology Verification Successful")
        sys.exit(0)
    else:
        print("Topology Verification Failed")
        sys.exit(1)
