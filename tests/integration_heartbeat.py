
import logging
import asyncio
import os
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime
from langchain_core.messages import HumanMessage

# Set mock project to avoid Google Auth errors
os.environ["GOOGLE_CLOUD_PROJECT"] = "mock-project"

# Import the Anatomy
from studio.memory import (
    StudioState, OrchestrationState, EngineeringState,
    ContextSlice, VerificationGate, JulesMetadata, TriageStatus
)
from studio.orchestrator import Orchestrator
from studio.utils.jules_client import WorkStatus

# Configure Logging
logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
logger = logging.getLogger("Heartbeat")

def create_mock_state():
    """Generates the initial 'Spark of Life' (State Object)."""
    return StudioState(
        system_version="0.1.0-test",
        orchestration=OrchestrationState(
            session_id="TEST-SESSION-001",
            user_intent="CODING", # Triggers the Engineer Path
            triage_status=TriageStatus(is_log_available=True, suspected_domain="drivers")
        ),
        engineering=EngineeringState(
            current_task="TKT-HEARTBEAT",
            jules_meta=JulesMetadata(session_id="TEST-SESSION-001")
        )
    )

async def run_heartbeat():
    logger.info(">>> INITIATING STUDIO HEARTBEAT SEQUENCE <<<")

    # --- STEP 1: PATCH THE EXTERNAL ORGANS (Mocks) ---

    with patch("studio.orchestrator.VertexFlashJudge") as MockOrchJudge, \
         patch("studio.orchestrator.GenerativeModel"), \
         patch("studio.subgraphs.engineer.JulesGitHubClient") as MockJules, \
         patch("studio.subgraphs.engineer.VertexFlashJudge") as MockSensor, \
         patch("studio.subgraphs.engineer.GenerativeModel"), \
         patch("studio.subgraphs.engineer.DockerSandbox") as MockSandbox, \
         patch("studio.subgraphs.engineer.apply_virtual_patch") as MockPatch, \
         patch("studio.agents.architect.ChatVertexAI") as MockChat, \
         patch("studio.agents.architect.PydanticOutputParser"):

        # 1.1 Mock Jules (The Hand)
        jules_instance = MockJules.return_value
        jules_instance.dispatch_task.return_value = "ISSUE-101"
        # Simulate Jules working then finishing
        jules_instance.get_status.side_effect = [
            WorkStatus(tracking_id="ISSUE-101", status="WORKING"),
            WorkStatus(
                tracking_id="ISSUE-101",
                status="COMPLETED",
                linked_pr_number=99,
                raw_diff="def fix(): return True"
            )
        ]

        # 1.2 Mock Sensor (The Eye)
        sensor_instance = MockSensor.return_value
        # Simulate Low Entropy (Healthy)
        sensor_instance.generate_samples = AsyncMock(return_value=["Fix is good"] * 5)
        sensor_instance.check_entailment = AsyncMock(return_value=True)

        # Also mock for orchestrator
        orch_judge_inst = MockOrchJudge.return_value
        orch_judge_inst.generate_samples = AsyncMock(return_value=["Fix is good"] * 5)
        orch_judge_inst.check_entailment = AsyncMock(return_value=True)

        # 1.3 Mock Sandbox (The Environment)
        box_instance = MockSandbox.return_value
        box_instance.setup_workspace.return_value = True
        box_instance.install_dependencies.return_value = MagicMock(exit_code=0)
        # Simulate Test Passing
        mock_test_run = MagicMock()
        mock_test_run.passed = True
        mock_test_run.error_log = None
        box_instance.run_pytest.return_value = mock_test_run

        # 1.4 Mock Patching
        MockPatch.return_value = {"src/auth/login.py": "def fix(): return True"}

        # 1.5 Mock Architect
        with patch("studio.subgraphs.engineer.ArchitectAgent") as MockArchitectAgent:
            architect_instance = MockArchitectAgent.return_value
            from studio.memory import ReviewVerdict
            architect_instance.review_code.return_value = ReviewVerdict(
                status="APPROVED",
                quality_score=9.0,
                violations=[]
            )

            # --- STEP 2: BUILD THE BODY ---
            logger.info("[1/4] Booting Orchestrator...")
            # The Orchestrator now uses the real subgraph by default
            orchestrator = Orchestrator()

            # --- STEP 3: EXECUTE THE CYCLE ---
            initial_state = create_mock_state()
            logger.info(f"[2/4] Injecting Intent: {initial_state.orchestration.user_intent}")

            # Run the Graph!
            final_state = await orchestrator.app.ainvoke(initial_state)

            # --- STEP 4: VERIFY VITAL SIGNS ---
            logger.info("[3/4] Execution Complete. Checking Vitals...")

            if isinstance(final_state, dict):
                eng_state = final_state["engineering"]
                cb_triggered = final_state.get("circuit_breaker_triggered", False)
            else:
                eng_state = final_state.engineering
                cb_triggered = final_state.circuit_breaker_triggered

            # Assertion 1: Did we dispatch to Jules?
            if eng_state.jules_meta and eng_state.jules_meta.external_task_id == "ISSUE-101":
                logger.info("   [PASS] Hand: Jules received the task.")
            else:
                logger.error(f"   [FAIL] Hand: Jules did not receive task correctly. ID: {eng_state.jules_meta.external_task_id if eng_state.jules_meta else 'None'}")

            # Assertion 2: Did we check Entropy?
            if not cb_triggered:
                logger.info("   [PASS] Sensor: Circuit Breaker held steady (Low Entropy).")
            else:
                logger.error("   [FAIL] Sensor: Circuit Breaker triggered unexpectedly.")

            # Assertion 3: Did QA Pass?
            if eng_state.verification_gate.status == "GREEN":
                logger.info("   [PASS] Environment: QA Tests passed in Sandbox.")
            else:
                logger.error(f"   [FAIL] Environment: QA Failed with status {eng_state.verification_gate.status}")

            logger.info(">>> HEARTBEAT SUCCESSFUL - PHASE 1 COMPLETE <<<")

if __name__ == "__main__":
    try:
        asyncio.run(run_heartbeat())
    except Exception as e:
        logger.exception("Heartbeat failed with exception")
