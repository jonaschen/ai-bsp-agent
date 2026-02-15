import os
import json
import argparse
import asyncio
import tempfile
import logging
from studio.memory import StudioState, OrchestrationState, EngineeringState, VerificationGate
from studio.orchestrator import Orchestrator

# Configuration
STATE_FILE = "studio_state.json"
CLEAN_PATH = STATE_FILE  # Exposed for testing

def load_state() -> StudioState:
    """
    State Loading & Recovery Logic.
    Prioritizes loading from disk; falls back to 'Cold Start' if missing.
    """
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                # Pydantic Validation ensures disk JSON matches memory Schema
                return StudioState.model_validate(data)
        except Exception as e:
            logging.error(f"Failed to load state: {e}. Reverting to cold start.")

    # Cold Start: Initialize a brand new StudioState
    logging.info("Initializing fresh StudioState (Cold Start)...")
    return StudioState(
        system_version="1.0.0",
        orchestration=OrchestrationState(
            session_id="SESSION-01",
            user_intent="SPRINT"
        ),
        engineering=EngineeringState(
            verification_gate=VerificationGate(status="PENDING")
        )
    )

def save_state(state: StudioState):
    """
    Atomic State Persistence.
    Writes to a temporary file first, then renames to prevent corruption.
    """
    fd, temp_path = tempfile.mkstemp(dir=".", text=True)
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(state.model_dump_json(indent=4))
        os.replace(temp_path, STATE_FILE)
    except Exception as e:
        os.remove(temp_path)
        logging.error(f"Failed to save state: {e}")

async def run_studio():
    """
    Orchestration Life-cycle Manager.
    Handles startup, execution, and shutdown.
    """
    state = load_state()
    logging.info(f"System Online. Version: {state.system_version}")

    # Pre-flight checks
    if not os.path.exists("PRODUCT_BLUEPRINT.md"):
        logging.warning("PRODUCT_BLUEPRINT.md not found. System may lack direction.")

    orchestrator = Orchestrator()

    # Execution Control: Manage LangGraph recursion depth
    config = {"recursion_limit": 100}

    try:
        logging.info("Starting Orchestration Loop...")
        # Invoke the Supergraph
        final_state_data = await orchestrator.app.ainvoke(state, config=config)

        # Recover final state and persist
        final_state = StudioState.model_validate(final_state_data)
        save_state(final_state)
        logging.info("Sprint cycle completed successfully.")

    except Exception as e:
        logging.critical(f"System Crash in Orchestration Loop: {e}", exc_info=True)

def main():
    parser = argparse.ArgumentParser(description="Jules Studio - Production Entry Point")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("run", help="Execute the factory cycle (Plan -> Execute -> Review)")
    subparsers.add_parser("clean", help="Wipe the local state (Fresh Start)")

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    if args.command == "run":
        asyncio.run(run_studio())
    elif args.command == "clean":
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
            print(f"State wiped. {STATE_FILE} removed.")
        else:
            print("Already clean.")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
