"""
tests/phase2_simulation.py
--------------------------
The Phase 2 "Cognitive Awakening" Simulation.
Verifies the full autonomous loop: Strategy -> Execution -> Governance -> Optimization.

Flow Verified:
1. Product Owner: Reads Blueprint -> Generates Tickets (DAG).
2. Orchestrator: Picks High-Priority Ticket -> Slices Context.
3. Engineer: Writes Code (Mocked).
4. Architect: Reviews Code (Mocked).
5. Scrum Master: Analyzes the Sprint (Mocked).

Usage:
    python tests/phase2_simulation.py
"""

import logging
import json
import os
from unittest.mock import MagicMock, patch
from datetime import datetime

# Mock Environment for Vertex AI
os.environ["GOOGLE_CLOUD_PROJECT"] = "mock-project"

# Import The Team
from studio.memory import (
    StudioState, OrchestrationState, EngineeringState,
    Ticket, TicketStatus, ContextSlice,
    ArchitecturalDecisionRecord
)
from studio.agents.product_owner import run_po_cycle, POTicket, BlueprintAnalysis
from studio.agents.architect import run_architect_gate, ReviewVerdict, Violation
from studio.agents.scrum_master import run_scrum_retrospective, RetrospectiveReport, ProcessOptimization

# Configure Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("Simulation")

# --- MOCK DATA GENERATORS ---

def mock_blueprint():
    return """
    # PRODUCT BLUEPRINT v1.0
    ## Section 2.1: The Kernel Module
    We need a high-performance Android Binder driver extension.
    It must adhere to strict security protocols.
    """

def mock_po_llm_response(*args, **kwargs):
    """Simulates Gemini-Pro parsing the blueprint."""
    return BlueprintAnalysis(
        blueprint_version_hash="sha256_mock",
        summary_of_changes="Initial Draft",
        new_tickets=[
            POTicket(
                id="TKT-201",
                title="Implement Binder Extensions",
                description="Create drivers/android/binder_ext.c",
                priority="HIGH",
                dependencies=[],
                source_section_id="2.1"
            )
        ]
    )

def mock_architect_llm_response(*args, **kwargs):
    """Simulates Architect REJECTING the first attempt."""
    # We simulate a strict architect finding a violation
    return ReviewVerdict(
        status="REJECTED",
        quality_score=4.5,
        violations=[
            Violation(
                rule_id="SEC-01",
                severity="CRITICAL",
                description="Hardcoded root credentials found.",
                file_path="drivers/android/binder_ext.c",
                line_number=42,
                suggested_fix="Use kernel keyring."
            )
        ]
    )

def mock_scrum_master_llm_response(*args, **kwargs):
    """Simulates Scrum Master finding a pattern."""
    return RetrospectiveReport(
        sprint_id="SPRINT-SIM-01",
        success_rate=0.5,
        avg_entropy_score=3.2,
        key_bottlenecks=["Security Compliance"],
        optimizations=[
            ProcessOptimization(
                target_role="Engineer",
                issue_detected="Repeated Security Violations",
                suggested_prompt_update="ADD: 'NEVER use hardcoded credentials.'",
                expected_impact="Reduce Architect rejection rate."
            )
        ]
    )

# --- THE SIMULATION RUNNER ---

def run_phase2_simulation():
    logger.info(">>> STARTING PHASE 2 COGNITIVE SIMULATION <<<")

    # 1. Initialize State
    # We add dummy completed tasks to satisfy the Scrum Master's threshold (min 3 tasks)
    t1 = MagicMock()
    t1.id = "TKT-100"
    t1.title = "Setup Repo"
    t1.retry_count = 0

    t2 = MagicMock()
    t2.id = "TKT-101"
    t2.title = "Configure CI"
    t2.retry_count = 1

    state = {
        "orchestration_layer": {
            "task_queue": [],
            "completed_tasks_log": [t1, t2],
            "failed_tasks_log": [],
            "current_sprint_id": "SPRINT-SIM-01"
        },
        "engineering": {
            "code_artifacts": {},
            "workspace_snapshot": {}
        }
    }

    # --- STEP 1: THE PRODUCT OWNER (Strategy) ---
    logger.info("\n--- [STEP 1] PRODUCT OWNER AGENT ACTIVATED ---")
    # Patch ChatVertexAI to prevent auth errors during instantiation
    with patch("studio.agents.product_owner.ChatVertexAI"), \
         patch("builtins.open", new=MagicMock(return_value=MagicMock(read=mock_blueprint))), \
         patch("studio.agents.product_owner.ProductOwnerAgent.analyze_specs", side_effect=mock_po_llm_response):

        new_tickets = run_po_cycle(state)

        # Merge into state
        # In real Orchestrator, this is done by the graph. Here we do it manually.
        state["orchestration_layer"]["task_queue"].extend(new_tickets)

        t = new_tickets[0]
        logger.info(f"PO Generated Ticket: {t.id} - {t.title}")
        logger.info(f"   Dependencies: {t.dependencies}")
        logger.info(f"   Source: Blueprint Section {t.source_section_id}")

    # --- STEP 2: THE ENGINEER (Execution) ---
    logger.info("\n--- [STEP 2] ENGINEER SUBGRAPH SIMULATED ---")
    # We skip the Jules/Sandbox logic here (tested in Heartbeat) and just inject the artifacts.
    logger.info("... Engineer is coding ...")

    state["engineering"]["current_task"] = "TKT-201"
    state["engineering"]["workspace_snapshot"] = {
        "current_file": "drivers/android/binder_ext.c",
        "current_file_content": "void binder_init() { char* p = 'root123'; }" # Vulnerable code
    }
    state["engineering"]["code_artifacts"] = {
        "proposed_patch": "+ char* p = 'root123';"
    }
    logger.info("Engineer submitted patch for review.")

    # --- STEP 3: THE ARCHITECT (Governance) ---
    logger.info("\n--- [STEP 3] ARCHITECT AGENT ACTIVATED ---")
    with patch("studio.agents.architect.ChatVertexAI"), \
         patch("studio.agents.architect.ArchitectAgent.review_code", side_effect=mock_architect_llm_response):

        # Pass the local engineering state
        result = run_architect_gate(state["engineering"])

        verdict = result["code_artifacts"]["static_analysis_report"]
        gate_status = result["verification_gate"]["status"]

        logger.info(f"Architect Verdict: {gate_status}")
        if gate_status == "RED":
            logger.warning(f"Blocking Reason: {result['verification_gate']['blocking_reason']}")

            # Log failure to history (Simulating Orchestrator logic)
            failed_ticket = MagicMock()
            failed_ticket.id = "TKT-201"
            failed_ticket.failure_log = "Architect Rejected: Security Violation"
            state["orchestration_layer"]["failed_tasks_log"].append(failed_ticket)

    # --- STEP 4: THE SCRUM MASTER (Optimization) ---
    logger.info("\n--- [STEP 4] SCRUM MASTER AGENT ACTIVATED ---")
    with patch("studio.agents.scrum_master.ChatVertexAI"), \
         patch("studio.agents.scrum_master.ScrumMasterAgent.conduct_retrospective", side_effect=mock_scrum_master_llm_response):

        report = run_scrum_retrospective(state)

        if report:
            logger.info(f"Retrospective for {report.sprint_id} Complete.")
            logger.info(f"Bottleneck Identified: {report.key_bottlenecks[0]}")

            opt = report.optimizations[0]
            logger.info(f"Proposed Optimization (OPRO):")
            logger.info(f"   Target: {opt.target_role}")
            logger.info(f"   Action: {opt.suggested_prompt_update}")
        else:
            logger.error("Scrum Master failed to generate report.")

    logger.info("\n>>> PHASE 2 SIMULATION COMPLETE: SYSTEM IS COGNITIVE <<<")

if __name__ == "__main__":
    run_phase2_simulation()
