from unittest.mock import patch, mock_open
import json
from studio.utils.regenerate_seed import generate_seed
from studio.memory import StudioState, OrchestrationState, EngineeringState, VerificationGate

def test_generate_seed():
    """
    Tests that generate_seed creates the correct StudioState and writes it
    to both studio_state.seed.json and studio/studio_state.seed.json
    with the correct JSON formatting.
    """
    with patch("builtins.open", mock_open()) as mocked_file, \
         patch("json.dump") as mocked_json_dump:

        generate_seed()

        # Verify open was called twice with correct paths
        assert mocked_file.call_count == 2
        mocked_file.assert_any_call("studio_state.seed.json", "w")
        mocked_file.assert_any_call("studio/studio_state.seed.json", "w")

        # Construct the expected state to compare
        expected_state = StudioState(
            system_version="5.2.0",
            orchestration=OrchestrationState(
                session_id="SESSION-00",
                user_intent="BOOTSTRAP"
            ),
            engineering=EngineeringState(
                verification_gate=VerificationGate(status="PENDING")
            )
        )
        expected_json = expected_state.model_dump(mode='json')

        # Verify json.dump was called twice with correct arguments
        assert mocked_json_dump.call_count == 2
        for call_args in mocked_json_dump.call_args_list:
            args, kwargs = call_args
            assert args[0] == expected_json
            # args[1] is the mock file object
            assert kwargs == {"indent": 2}
