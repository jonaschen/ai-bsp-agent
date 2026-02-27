from studio.memory import StudioState, OrchestrationState, EngineeringState, VerificationGate
import json
import os

def generate_seed():
    state = StudioState(
        system_version="5.2.0",
        orchestration=OrchestrationState(
            session_id="SESSION-00",
            user_intent="BOOTSTRAP"
        ),
        engineering=EngineeringState(
            verification_gate=VerificationGate(status="PENDING")
        )
    )

    seed_content = state.model_dump()

    # We need to handle datetime if any were in the defaults,
    # but looking at the schema, there are none in the top level states
    # except in nested lists which are empty by default.
    # Actually, Pydantic's model_dump with mode='json' is better if we had datetimes.
    # Since we use pydantic v2, let's use model_dump(mode='json')

    seed_json = state.model_dump(mode='json')

    with open("studio_state.seed.json", "w") as f:
        json.dump(seed_json, f, indent=2)

    with open("studio/studio_state.seed.json", "w") as f:
        json.dump(seed_json, f, indent=2)

if __name__ == "__main__":
    generate_seed()
