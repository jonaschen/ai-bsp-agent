import pytest
from unittest.mock import MagicMock, patch
from studio.subgraphs.engineer import node_qa_verifier
from studio.memory import AgentState, JulesMetadata, ContextSlice
import os

@pytest.mark.asyncio
async def test_node_qa_verifier_excludes_pytest_ini_from_targets():
    # Setup State: pytest.ini is in the context
    jules_data = JulesMetadata(
        status="VERIFYING",
        active_context_slice=ContextSlice(files=["pytest.ini"]),
        generated_artifacts=[]
    )
    state: AgentState = {
        "messages": [],
        "jules_metadata": jules_data,
        "system_constitution": "",
        "next_agent": None
    }

    # Mock Dependencies
    with patch("studio.subgraphs.engineer.DockerSandbox") as MockSandbox, \
         patch("studio.subgraphs.engineer.apply_virtual_patch") as mock_apply, \
         patch("studio.subgraphs.engineer.extract_affected_files") as mock_extract, \
         patch("os.path.exists") as mock_exists, \
         patch("os.walk") as mock_walk, \
         patch("builtins.open", MagicMock()):

        # No affected files from patch
        mock_extract.return_value = []
        # apply_virtual_patch returns what it received
        mock_apply.return_value = {"pytest.ini": "[pytest]"}

        # Simulate existence of pytest.ini
        def side_effect_exists(path):
            if path == "pytest.ini": return True
            if path == "tests": return False # Don't discover more tests
            return False
        mock_exists.side_effect = side_effect_exists

        mock_sandbox_inst = MagicMock()
        MockSandbox.return_value = mock_sandbox_inst
        mock_sandbox_inst.setup_workspace.return_value = True
        mock_sandbox_inst.run_pytest.return_value = MagicMock(passed=True, error_log=None)

        # Execute
        await node_qa_verifier(state)

        # Verify run_pytest target
        # Currently, the bug causes "pytest.ini" to be in test_files
        # and thus target = "pytest.ini"
        run_pytest_call = mock_sandbox_inst.run_pytest.call_args[0][0]

        # Assert that "pytest.ini" is NOT in the target string
        # If it is there, this test should FAIL (Red)
        assert "pytest.ini" not in run_pytest_call, f"Expected pytest.ini NOT to be in target, but got: {run_pytest_call}"
        # It should default to "tests/" if no other tests are found
        assert run_pytest_call == "tests/"
