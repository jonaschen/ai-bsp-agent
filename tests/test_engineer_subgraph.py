
import pytest
import logging
from unittest.mock import MagicMock, patch, AsyncMock
from studio.memory import EngineeringState, JulesMetadata, VerificationGate, ContextSlice

logging.basicConfig(level=logging.INFO)

# We need to import the module to test it.
# However, the module relies on dependencies that might not be configured.
# We will use patches.

@pytest.mark.asyncio
async def test_engineer_subgraph_flow():
    """
    Verifies the Phase 2.5 Wired Subgraph flow:
    Dispatch -> Watch -> Entropy -> QA -> Architect -> End
    """

    # Mock External Dependencies
    with patch("studio.utils.jules_client.JulesGitHubClient") as MockClient, \
         patch("studio.utils.entropy_math.SemanticEntropyCalculator") as MockSensor, \
         patch("studio.utils.sandbox.DockerSandbox") as MockSandbox, \
         patch("studio.subgraphs.engineer.run_architect_gate") as mock_architect_gate:

        # Setup Mocks
        mock_client_instance = MockClient.return_value
        mock_client_instance.dispatch_task.return_value = "123"
        # Simulate PR ready
        mock_status = MagicMock()
        mock_status.status = "REVIEW_READY"
        mock_status.raw_diff = "+ code"
        mock_status.pr_url = "http://github.com/pr/1"
        mock_status.linked_pr_number = 1
        mock_client_instance.get_status.return_value = mock_status

        mock_sensor_instance = MockSensor.return_value
        mock_entropy = MagicMock()
        mock_entropy.entropy_score = 0.5
        mock_entropy.is_tunneling = False
        mock_sensor_instance.measure_uncertainty.return_value = mock_entropy # Async?
        # Check if measure_uncertainty is async in real code. usually yes.
        if hasattr(mock_sensor_instance.measure_uncertainty, "return_value"):
             mock_sensor_instance.measure_uncertainty = AsyncMock(return_value=mock_entropy)

        # Mock Sandbox (QA)
        mock_sandbox_instance = MockSandbox.return_value
        mock_sandbox_instance.setup_workspace.return_value = True
        mock_test_result = MagicMock()
        mock_test_result.passed = True
        mock_test_result.error_log = ""
        mock_sandbox_instance.run_pytest.return_value = mock_test_result

        # Mock Architect
        mock_architect_gate.return_value = {
            "code_artifacts": {"proposed_patch": "+ code", "static_analysis_report": {"status": "APPROVED"}},
            "verification_gate": {"status": "GREEN"}
        }

        # Import the code under test
        # We import here so that patches apply if they are used at import time or global scope (less likely for classes)
        from studio.subgraphs.engineer import build_engineer_subgraph

        # Initialize State
        initial_state = EngineeringState(
            current_task="TKT-101",
            jules_meta=JulesMetadata(
                active_context_slice=ContextSlice(files=["test.py"], intent="CODING")
            )
        )

        # Build Graph
        graph = build_engineer_subgraph()

        # Run Graph
        # We expect the graph to run through all nodes
        # Dispatch -> Watch -> Entropy -> QA -> Architect -> END

        # We can trace the execution or check final state.
        # LangGraph invoke returns the final state.

        final_state = await graph.ainvoke(initial_state)

        # Assertions

        # 1. Check if Architect was called
        mock_architect_gate.assert_called()

        # 2. Check Final State
        assert final_state["verification_gate"].status == "GREEN"
        assert final_state["jules_meta"].status == "VERIFYING" # From Watch Tower

        # If the architect rejected, it would loop back. Since we mocked approval, it should end.

        print("Test Passed: Architect node was visited and approved.")

if __name__ == "__main__":
    # Manually run the test function if executed as script
    import asyncio
    try:
        asyncio.run(test_engineer_subgraph_flow())
    except Exception as e:
        print(f"Test Failed: {e}")
        import traceback
        traceback.print_exc()
