
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
from studio.subgraphs.engineer import build_engineer_subgraph, AgentState

def verify_topology():
    print("Building engineer subgraph...")
    graph = build_engineer_subgraph()

    print("Verifying nodes...")
    nodes = graph.nodes
    expected_nodes = [
        "task_dispatcher",
        "watch_tower",
        "entropy_guard",
        "qa_verifier",
        "architect_gate",
        "feedback_loop"
    ]

    missing_nodes = [n for n in expected_nodes if n not in nodes]
    if missing_nodes:
        print(f"FAILED: Missing nodes: {missing_nodes}")
        return False
    else:
        print("PASSED: All expected nodes present.")

    # Note: Accessing edges directly from a compiled StateGraph is tricky as it's compiled into a preamble.
    # But we can verify by running the graph or inspecting the internal structure if possible.
    # Alternatively, we can check the `builder` if we had access to it, but `build_engineer_subgraph` returns `CompiledGraph`.

    # However, we can inspect the conditional edges by looking at the source code or by
    # running the graph with mock state and checking transitions.
    # Let's try to run the graph with mock state to test transitions.

    print("Verifying transitions (Dynamic Verification)...")

    # Test QA -> Architect (Green)
    # We need to mock the node execution.
    # Since we can't easily mock the internal node functions after import without patching `studio.subgraphs.engineer`,
    # we will rely on the fact that we can see the code structure in the file.
    # But let's try to patch the node functions in `studio.subgraphs.engineer` module.

    import studio.subgraphs.engineer as engineer_module

    # Mock the nodes to return specific states to test routing
    async def mock_qa_verifier(state):
        return {"jules_metadata": state["jules_metadata"]}

    engineer_module.node_qa_verifier = mock_qa_verifier

    # We need to re-compile the graph with mocked nodes?
    # No, `build_engineer_subgraph` uses the functions directly.
    # If we patch them *before* calling `build_engineer_subgraph`, it might work
    # IF `build_engineer_subgraph` uses the module attributes.
    # Let's check the import in verify_topology.py...
    # `from studio.subgraphs.engineer import build_engineer_subgraph`
    # build_engineer_subgraph uses `node_qa_verifier` which is defined in the module.
    # So if we modify `engineer_module.node_qa_verifier`, `build_engineer_subgraph` will use the modified one
    # ONLY IF it references it by name at build time. It likely does.

    # Let's try to patch all nodes to be pass-throughs that we can control via state.

    engineer_module.node_task_dispatcher = MagicMock(side_effect=lambda s: {"jules_metadata": s["jules_metadata"]})
    engineer_module.node_watch_tower = MagicMock(side_effect=lambda s: {"jules_metadata": s["jules_metadata"]})
    engineer_module.node_entropy_guard = MagicMock(side_effect=lambda s: {"jules_metadata": s["jules_metadata"]})
    engineer_module.node_qa_verifier = MagicMock(side_effect=lambda s: {"jules_metadata": s["jules_metadata"]})
    # Note: We expect the module to have node_architect_gate now
    if hasattr(engineer_module, "node_architect_gate"):
        engineer_module.node_architect_gate = MagicMock(side_effect=lambda s: {"jules_metadata": s["jules_metadata"]})
    else:
        # If not present yet (Red phase), we can't patch it, but we can verify it's missing or check graph failure
        pass

    # We also need to patch node_architect_review if it exists, to avoid errors if build_engineer_subgraph still uses it
    if hasattr(engineer_module, "node_architect_review"):
         engineer_module.node_architect_review = MagicMock(side_effect=lambda s: {"jules_metadata": s["jules_metadata"]})

    engineer_module.node_feedback_loop = MagicMock(side_effect=lambda s: {"jules_metadata": s["jules_metadata"]})

    # Rebuild graph with mocks
    graph = engineer_module.build_engineer_subgraph()

    # Test 1: QA (Green) -> Architect
    print("Test 1: QA (Green) -> Architect")
    from studio.memory import JulesMetadata, AgentState, ContextSlice

    context_slice = ContextSlice(
        slice_id="test_slice",
        intent="CODING",
        active_files={},
        relevant_logs=""
    )

    state = AgentState(
        jules_metadata=JulesMetadata(
            session_id="test",
            status="COMPLETED", # QA sets this on pass
            active_context_slice=context_slice,
            max_retries=3
        ),
        messages=[]
    )

    # We start at qa_verifier
    # Note: LangGraph `invoke` runs from entry point. We can't easily start at arbitrary node unless we change entry point.
    # But we can verify the routing function logic directly!

    # Let's verify `route_qa_verifier` logic
    print("Verifying route_qa_verifier...")
    route_result = engineer_module.route_qa_verifier(state)
    if route_result == "architect_gate":
        print("PASSED: QA (COMPLETED) -> architect_gate")
    else:
        print(f"FAILED: QA (COMPLETED) -> {route_result}")
        return False

    # Test 2: QA (Red) -> Feedback
    print("Test 2: QA (Red) -> Feedback")
    state["jules_metadata"].status = "FAILED"
    route_result = engineer_module.route_qa_verifier(state)
    if route_result == "feedback_loop":
         print("PASSED: QA (FAILED) -> feedback_loop")
    else:
         print(f"FAILED: QA (FAILED) -> {route_result}")
         return False

    # Test 3: Architect (Green) -> End
    print("Test 3: Architect (Green) -> End")
    state["jules_metadata"].status = "COMPLETED"

    # Expect route_architect_gate to exist
    if not hasattr(engineer_module, "route_architect_gate"):
        print("FAILED: route_architect_gate not found")
        return False

    route_result = engineer_module.route_architect_gate(state)
    if route_result == "end": # Function returns "end", map has "end": END
         print("PASSED: Architect (COMPLETED) -> end")
    else:
         print(f"FAILED: Architect (COMPLETED) -> {route_result}")
         return False

    # Test 4: Architect (Red) -> Feedback
    print("Test 4: Architect (Red) -> Feedback")
    state["jules_metadata"].status = "FAILED" # Architect sets this on reject
    route_result = engineer_module.route_architect_gate(state)
    if route_result == "feedback_loop":
         print("PASSED: Architect (FAILED) -> feedback_loop")
    else:
         print(f"FAILED: Architect (FAILED) -> {route_result}")
         return False

    return True

if __name__ == "__main__":
    if verify_topology():
        print("Topology Verification Successful")
        sys.exit(0)
    else:
        print("Topology Verification Failed")
        sys.exit(1)
