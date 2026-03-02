import json
from studio.memory import StudioState, EngineeringState, JulesMetadata, OrchestrationState
import pytest

def test_jules_metadata_serialization_compliance():
    """
    Verifies that JulesMetadata can be serialized when converted to a dict.
    This simulates the requirement for msgpack compatibility in LangGraph.
    """
    meta = JulesMetadata(session_id="test-session")

    # This is what currently fails in the Orchestrator/Checkpointer if not dumped
    eng_state = EngineeringState(
        current_task="Fix bug",
        jules_meta=meta
    )

    orch_state = OrchestrationState(
        session_id="test-session",
        user_intent="CODING"
    )

    studio_state = StudioState(
        orchestration=orch_state,
        engineering=eng_state
    )

    # Standard json.dumps will fail on Pydantic models unless they are dicts
    # We want to ensure that if we dump it, it works.

    state_dict = studio_state.model_dump()

    try:
        json_str = json.dumps(state_dict)
        assert json_str is not None

        # Verify round-trip
        loaded_dict = json.loads(json_str)
        assert loaded_dict["engineering"]["jules_meta"]["session_id"] == "test-session"

    except TypeError as e:
        pytest.fail(f"Serialization failed even after model_dump: {e}")

def test_jules_metadata_direct_serialization_failure():
    """
    Demonstrates that raw JulesMetadata in a dict fails standard json serialization.
    This mimics the msgpack failure.
    """
    meta = JulesMetadata(session_id="test-session")
    data = {"jules_meta": meta}

    with pytest.raises(TypeError):
        json.dumps(data)

def test_agent_state_serialization_failure():
    """
    Verifies that AgentState (TypedDict) with raw JulesMetadata fails serialization.
    """
    from studio.memory import AgentState
    meta = JulesMetadata(session_id="test")
    state: AgentState = {
        "messages": [],
        "system_constitution": "",
        "next_agent": None,
        "jules_metadata": meta
    }
    with pytest.raises(TypeError):
        json.dumps(state)

def test_jules_metadata_union_type_support():
    """
    Verifies that EngineeringState and AgentState now accept dict as well as object.
    """
    from studio.memory import AgentState
    meta = JulesMetadata(session_id="test-session")
    meta_dict = meta.model_dump()

    # Verify EngineeringState accepts dict
    eng_state = EngineeringState(
        current_task="Fix bug",
        jules_meta=meta_dict
    )
    assert isinstance(eng_state.jules_meta, dict)

    # Verify AgentState accepts dict
    state: AgentState = {
        "messages": [],
        "system_constitution": "",
        "next_agent": None,
        "jules_metadata": meta_dict
    }
    assert isinstance(state["jules_metadata"], dict)

    # Verify that StudioState with dict jules_meta serializes successfully
    orch_state = OrchestrationState(
        session_id="test-session",
        user_intent="CODING"
    )
    studio_state = StudioState(
        orchestration=orch_state,
        engineering=eng_state
    )

    # model_dump() will dump nested models too
    state_dump = studio_state.model_dump()
    json_str = json.dumps(state_dump)
    assert json_str is not None
