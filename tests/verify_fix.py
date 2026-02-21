
import asyncio
import time
import sys
import os
from unittest.mock import MagicMock, patch

# Add repo root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock dependencies
mock_pydantic_settings = MagicMock()
mock_pydantic_settings.BaseSettings = object
mock_pydantic_settings.SettingsConfigDict = MagicMock()
sys.modules['pydantic_settings'] = mock_pydantic_settings

sys.modules['langgraph'] = MagicMock()
sys.modules['langgraph.graph'] = MagicMock()
sys.modules['langchain_core'] = MagicMock()
sys.modules['langchain_core.messages'] = MagicMock()
sys.modules['vertexai'] = MagicMock()
sys.modules['vertexai.generative_models'] = MagicMock()
sys.modules['studio.utils.sandbox'] = MagicMock()
sys.modules['studio.utils.entropy_math'] = MagicMock()
sys.modules['studio.agents.architect'] = MagicMock()

# Mock Pydantic SecretStr and Field if needed, or import if available
try:
    from pydantic import SecretStr, Field
except ImportError:
    mock_pydantic = MagicMock()
    mock_pydantic.SecretStr = MagicMock(return_value="mock")
    mock_pydantic.Field = MagicMock()
    mock_pydantic.BaseModel = object
    sys.modules['pydantic'] = mock_pydantic

# Mock types for Optional
class MockMetric:
    pass

class MockStatus:
    def __init__(self, tracking_id, status, linked_pr_number=None, pr_url=None, last_commit_hash=None, diff_stat=None, raw_diff=None):
        self.tracking_id = tracking_id
        self.status = status
        self.linked_pr_number = linked_pr_number
        self.pr_url = pr_url
        self.last_commit_hash = last_commit_hash
        self.diff_stat = diff_stat
        self.raw_diff = raw_diff

# Mock studio.utils.jules_client so we can import engineer
mock_jules_client_mod = MagicMock()
mock_jules_client_mod.WorkStatus = MockStatus
sys.modules['studio.utils.jules_client'] = mock_jules_client_mod


# Mock studio.memory dependencies to allow import
# We need to manually construct studio.memory module with mocked classes
mock_memory = MagicMock()
mock_memory.SemanticHealthMetric = MockMetric
mock_memory.JulesMetadata = MagicMock
mock_memory.AgentState = MagicMock
sys.modules['studio.memory'] = mock_memory

# Import config (will use mocked pydantic_settings)
import studio.config

# Import engineer module to test the real function
from studio.subgraphs import engineer

# Mock settings
with patch('studio.subgraphs.engineer.get_settings') as mock_settings:
    mock_settings.return_value.github_token = "mock_token"
    mock_settings.return_value.github_repository = "mock_repo"
    mock_settings.return_value.jules_username = "mock_user"
    mock_settings.return_value.jules_poll_interval = 0.1

    # Mock JulesGitHubClient inside engineer module
    class MockJulesGitHubClient:
        def __init__(self, *args, **kwargs):
            pass

        def get_status(self, external_id):
            print(f"[{time.time()}] Starting blocking get_status call...")
            time.sleep(1.0) # Simulate blocking network call
            print(f"[{time.time()}] Finished blocking get_status call.")
            return MockStatus(tracking_id=external_id, status="WORKING")

    async def heartbeat(results):
        for i in range(5):
            results.append(time.time())
            await asyncio.sleep(0.1)

    async def main():
        print("--- Starting Verification ---")

        # Setup state
        jules_data = MagicMock()
        jules_data.external_task_id = "123"
        jules_data.status = "WORKING"

        state = {"jules_metadata": jules_data}

        # Patching JulesGitHubClient where it is used in studio.subgraphs.engineer

        heartbeat_timestamps = []
        with patch('studio.subgraphs.engineer.JulesGitHubClient', side_effect=MockJulesGitHubClient):
            start_time = time.time()

            # Run watch_tower and heartbeat concurrently
            await asyncio.gather(
                engineer.node_watch_tower(state),
                heartbeat(heartbeat_timestamps)
            )

            end_time = time.time()

            # Analyze results
            # If blocking, all heartbeats would be delayed until after the 1s sleep.
            # We expect the first heartbeat to be very close to start_time
            if not heartbeat_timestamps:
                print("FAIL: No heartbeats recorded")
                sys.exit(1)

            first_heartbeat = heartbeat_timestamps[0]
            delay = first_heartbeat - start_time
            print(f"First heartbeat delay: {delay:.4f}s")

            # If the delay is significant (e.g. > 0.5s), it means it blocked
            if delay > 0.5:
                print("FAIL: Heartbeat was blocked!")
                sys.exit(1)
            else:
                print("PASS: Heartbeat ran concurrently.")

    if __name__ == "__main__":
        asyncio.run(main())
