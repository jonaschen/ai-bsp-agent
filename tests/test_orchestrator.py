import pytest
from studio.memory import StudioState, OrchestrationState, EngineeringState, TriageStatus
from studio.orchestrator import Orchestrator

def test_orchestrator_coding_flow():
    # Setup state for CODING intent
    orch_state = OrchestrationState(
        session_id="test_1",
        user_intent="UNKNOWN", # Router should set this
        triage_status=TriageStatus(is_log_available=True, suspected_domain="drivers")
    )
    eng_state = EngineeringState()
    state = StudioState(orchestration=orch_state, engineering=eng_state)

    orchestrator = Orchestrator()

    # Run the graph
    # LangGraph invoke returns the final state dict or object depending on config.
    # Given StateGraph(StudioState), it usually returns a dict matching the schema if not configured to return object.
    # However, since we return updates, it accumulates.
    # Let's check the type of final_state.
    final_state = orchestrator.app.invoke(state)

    # If final_state is a dict, we access keys.
    if isinstance(final_state, dict):
        orch = final_state["orchestration"]
        eng = final_state["engineering"]
        cb = final_state.get("circuit_breaker_triggered", False)
    else:
        orch = final_state.orchestration
        eng = final_state.engineering
        cb = final_state.circuit_breaker_triggered

    # Assertions
    # 1. Intent should be CODING
    # Pydantic model or dict? LangGraph usually returns a dict if input was dict, or object if object.
    # We passed an object 'state'. LangGraph usually converts to dict internally if not typed strongly?
    # But let's handle both.

    if isinstance(orch, dict):
         assert orch["user_intent"] == "CODING"
         assert orch["current_context_slice"] is not None
         assert orch["current_context_slice"]["slice_id"].startswith("slice_")
         assert eng["proposed_patch"] == "Patch applied."
         assert orch["latest_entropy"] == 0.5
    else:
         assert orch.user_intent == "CODING"
         assert orch.current_context_slice is not None
         assert orch.current_context_slice.slice_id.startswith("slice_")
         assert eng.proposed_patch == "Patch applied."
         assert orch.latest_entropy == 0.5

    assert not cb

def test_orchestrator_sop_flow():
    # Setup state for SOP intent (No Log)
    orch_state = OrchestrationState(
        session_id="test_2",
        user_intent="UNKNOWN",
        triage_status=TriageStatus(is_log_available=False, suspected_domain="unknown")
    )
    eng_state = EngineeringState()
    state = StudioState(orchestration=orch_state, engineering=eng_state)

    orchestrator = Orchestrator()

    final_state = orchestrator.app.invoke(state)

    if isinstance(final_state, dict):
        orch = final_state["orchestration"]
    else:
        orch = final_state.orchestration

    if isinstance(orch, dict):
        assert orch["user_intent"] == "INTERACTIVE_GUIDE"
        sop = orch["guidance_sop"]
        assert sop is not None
        assert sop["active_sop_id"] == "NO_LOG_DEBUG"
        assert sop["current_step_index"] == 1
    else:
        assert orch.user_intent == "INTERACTIVE_GUIDE"
        sop = orch.guidance_sop
        assert sop is not None
        assert sop.active_sop_id == "NO_LOG_DEBUG"
        assert sop.current_step_index == 1
