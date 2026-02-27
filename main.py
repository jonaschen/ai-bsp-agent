import os
import json
import argparse
import asyncio
import logging
from studio.memory import StudioState
from studio.orchestrator import Orchestrator
from studio.manager import StudioManager
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

# Configuration
STATE_FILE = "studio_state.json"
CHECKPOINT_DB = "studio_checkpoints.db"
CLEAN_PATH = STATE_FILE  # Exposed for testing

async def run_studio():
    """
    Orchestration Life-cycle Manager.
    Handles startup, execution, and shutdown.
    """
    manager = StudioManager()
    state = manager.state
    logging.info(f"System Online. Version: {state.system_version}")

    # Pre-flight checks
    if not os.path.exists("PRODUCT_BLUEPRINT.md"):
        logging.warning("PRODUCT_BLUEPRINT.md not found. System may lack direction.")

    # Execution Control: Manage LangGraph recursion depth and thread ID
    config = {"configurable": {"thread_id": "studio-session-v1"}, "recursion_limit": 100}

    async with AsyncSqliteSaver.from_conn_string(CHECKPOINT_DB) as checkpointer:
        orchestrator = Orchestrator(checkpointer=checkpointer)

        try:
            logging.info("Starting Orchestration Loop...")
            # Invoke the Supergraph
            final_state_data = await orchestrator.app.ainvoke(state, config=config)

            # Recover final state and persist via manager
            final_state = StudioState.model_validate(final_state_data)
            manager.state = final_state
            manager._save_state()
            logging.info("Sprint cycle completed successfully.")

        except Exception as e:
            logging.critical(f"System Crash in Orchestration Loop: {e}", exc_info=True)

            # Crash Recovery Logic: Attempt to recover the last known state from checkpointer
            logging.info("Attempting state recovery from SQLite checkpointer...")
            try:
                checkpoint_state = await checkpointer.aget(config)
                if checkpoint_state and "channel_values" in checkpoint_state:
                    recovered_state = StudioState.model_validate(checkpoint_state["channel_values"])
                    manager.state = recovered_state
                    manager._save_state()
                    logging.info("Successfully recovered last known state from checkpointer.")
                else:
                    logging.warning("No checkpoint found for recovery.")
            except Exception as recovery_error:
                logging.error(f"Failed to recover state from checkpointer: {recovery_error}")

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
        files_removed = []
        for f in [STATE_FILE, CHECKPOINT_DB]:
            if os.path.exists(f):
                os.remove(f)
                files_removed.append(f)

        if files_removed:
            print(f"Cleaned: {', '.join(files_removed)}")
        else:
            print("Already clean.")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
