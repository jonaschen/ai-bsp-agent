
import asyncio
import os
import uuid
from main import run_studio, STATE_FILE, CHECKPOINT_DB
from studio.memory import StudioState
from studio.manager import StudioManager
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime

async def test_recovery_logic():
    print("Testing recovery logic...")

    # Clean up
    if os.path.exists(STATE_FILE): os.remove(STATE_FILE)
    if os.path.exists(CHECKPOINT_DB): os.remove(CHECKPOINT_DB)

    # Create a mock state
    manager = StudioManager()
    state = manager.state
    state.orchestration.session_id = "RECOVERY-TEST"
    manager._save_state()

    checkpoint_config = {
        "configurable": {
            "thread_id": "studio-session-v1",
            "checkpoint_ns": ""
        }
    }

    # 1. Manually insert a checkpoint into the DB to simulate a saved state
    async with AsyncSqliteSaver.from_conn_string(CHECKPOINT_DB) as checkpointer:
        checkpoint = {
            "v": 1,
            "id": str(uuid.uuid4()),
            "ts": datetime.now().isoformat(),
            "channel_values": state.model_dump(),
            "channel_versions": {},
            "versions_seen": {},
            "pending_sends": []
        }
        await checkpointer.aput(checkpoint_config, checkpoint, {"source": "test"}, {})
        print("Checkpoint inserted.")

    # 2. Mock Orchestrator to fail
    with patch("main.Orchestrator") as MockOrchestrator:
        mock_orch = MockOrchestrator.return_value
        # Mock the app property
        mock_app = AsyncMock()
        mock_app.ainvoke = AsyncMock(side_effect=Exception("Simulated Crash"))
        mock_orch.app = mock_app

        # Run run_studio (it should catch the exception and run recovery)
        print("Running run_studio with simulated crash...")
        # Since run_studio uses AsyncSqliteSaver.from_conn_string(CHECKPOINT_DB) as checkpointer:
        # we can just let it run, but we must make sure it uses the same DB.
        await run_studio()

    # 3. Verify that the recovered state matches what we put in the checkpoint
    recovered_manager = StudioManager()
    print(f"Recovered session_id: {recovered_manager.state.orchestration.session_id}")
    assert recovered_manager.state.orchestration.session_id == "RECOVERY-TEST"
    print("Recovery logic verified successfully!")

if __name__ == "__main__":
    asyncio.run(test_recovery_logic())
