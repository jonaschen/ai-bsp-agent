"""
studio/agents/scrum_master.py
-----------------------------
The Scrum Master Agent (The Optimizer).
Responsible for Continuous Improvement (Kaizen) of the Studio's processes.

Role:
1. Analyst: Reviews Sprint Logs (Success/Failure rates, Entropy Scores).
2. Diagnostic: Identifies root causes of bottlenecks (e.g., "Engineer keeps forgetting TDD").
3. Tuner: Generates 'Retrospective Insights' to update System Prompts (OPRO).

Dependencies:
- Vertex AI (Gemini-1.5-Pro for pattern recognition over large logs)
- studio.memory (EpisodicMemory, Ticket)
"""

import logging
from typing import List, Dict, Any
from pydantic import BaseModel, Field

from langchain_google_vertexai import ChatVertexAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser

# Import Studio Schemas
from studio.memory import Ticket, ProcessOptimization, RetrospectiveReport

logger = logging.getLogger("studio.agents.scrum_master")

# --- THE AGENT ---

class ScrumMasterAgent:
    def __init__(self, model_name: str = "gemini-3.5-pro-preview"):
        self.llm = ChatVertexAI(
            model_name=model_name,
            temperature=0.4, # Balanced for creative problem solving
            location="global",
            max_output_tokens=4096
        )
        self.parser = PydanticOutputParser(pydantic_object=RetrospectiveReport)

    def conduct_retrospective(self, sprint_data: Dict[str, Any]) -> RetrospectiveReport:
        """
        Analyzes the completed Sprint to generate insights.
        """
        sprint_id = sprint_data.get("sprint_id", "UNKNOWN")
        logger.info(f"Scrum Master is conducting Retrospective for {sprint_id}...")

        # 1. Format the Logs for the LLM
        # We need to turn raw state data into a narrative the LLM can analyze.
        completed_tickets = sprint_data.get("completed_tickets_log", [])
        failed_tickets = sprint_data.get("failed_tickets_log", [])

        # Calculate metrics explicitly to guide the LLM
        total = len(completed_tickets) + len(failed_tickets)
        success_rate = len(completed_tickets) / total if total > 0 else 0.0

        log_summary = self._summarize_logs(completed_tickets, failed_tickets)

        prompt = ChatPromptTemplate.from_messages([
            ("system", """
            You are the Scrum Master of an Autonomous AI Studio.
            Your goal is NOT to write code, but to OPTIMIZE the agents who do.

            **YOUR INPUT:**
            A log of the recent Sprint, including:
            - Ticket outcomes (Success/Fail)
            - Verification Failure Reasons (Why tests failed)
            - Architect Rejection Reasons (Why code was bad)
            - Semantic Entropy Scores (Where agents got confused)

            **YOUR TASK:**
            1. Identify **Recurring Failure Patterns** (e.g., "The Engineer consistently ignores Security constraints").
            2. Propose **Specific Prompt Optimizations** (OPRO) to fix these patterns.

            **OUTPUT FORMAT:**
            Strict JSON matching the RetrospectiveReport schema.
            """),
            ("user", """
            **Sprint ID:** {sprint_id}
            **Success Rate:** {success_rate:.2f}

            **SPRINT LOGS:**
            {log_summary}

            {format_instructions}
            """)
        ])

        chain = prompt | self.llm | self.parser

        try:
            report = chain.invoke({
                "sprint_id": sprint_id,
                "success_rate": success_rate,
                "log_summary": log_summary,
                "format_instructions": self.parser.get_format_instructions()
            })

            self._log_report(report)
            return report

        except Exception as e:
            logger.error(f"Scrum Master failed retrospective: {e}")
            # Return empty report on crash
            return RetrospectiveReport(
                sprint_id=sprint_id,
                success_rate=success_rate,
                avg_entropy_score=0.0,
                key_bottlenecks=["Scrum Master Crash"],
                optimizations=[]
            )

    def _summarize_logs(self, completed: List[Ticket], failed: List[Ticket]) -> str:
        """Helper to compress massive logs into token-efficient summaries."""
        summary = []

        for t in failed:
            # We assume the Ticket object has a 'closure_reason' or 'failure_log'
            reason = getattr(t, 'failure_log', 'Unknown Error')
            summary.append(f"[FAIL] {t.id}: {t.title} -> Reason: {reason}")

        for t in completed:
            # Check if there were retries (Architect rejected it once before approval)
            # This is where the 'learning' happens.
            retries = getattr(t, 'retry_count', 0)
            summary.append(f"[PASS] {t.id}: {t.title} (Retries: {retries})")

        return "\n".join(summary)

    def _log_report(self, report: RetrospectiveReport):
        logger.info(f"📊 Sprint {report.sprint_id} Report Generated.")
        logger.info(f"   Success Rate: {report.success_rate:.2%}")
        for opt in report.optimizations:
            logger.info(f"   💡 Insight for {opt.target_role}: {opt.issue_detected}")
            logger.info(f"      -> Suggestion: {opt.suggested_prompt_update[:50]}...")

# --- INTEGRATION HELPER ---

def run_scrum_retrospective(orchestrator_state: Dict[str, Any]):
    """
    Helper for the Orchestrator to run at the end of a Sprint (or periodically).
    """
    orch_layer = orchestrator_state.get("orchestration_layer", {})
    if not orch_layer:
        # Fallback to standard schema
        orch_layer = orchestrator_state.get("orchestration", {})

    # Check if we have enough data to run a retrospective
    completed = orch_layer.get("completed_tasks_log", [])
    failed = orch_layer.get("failed_tasks_log", [])

    if len(completed) + len(failed) < 3: # Arbitrary threshold
        logger.info("Not enough data for Retrospective (Need 3+ tasks). Skipping.")
        return None

    # Construct the Sprint Data Bundle
    sprint_data = {
        "sprint_id": orch_layer.get("current_sprint_id", "SPRINT-ADHOC"),
        "completed_tickets_log": completed,
        "failed_tickets_log": failed
    }

    sm = ScrumMasterAgent()
    report = sm.conduct_retrospective(sprint_data)

    # In Phase 3, we would automatically APPLY these optimizations.
    # For Phase 2, we just store them in Memory.
    return report
