"""
studio/agents/pr_monitor.py
--------------------------
The PR Monitor Agent.
Autonomous PR review cycles: Polling -> QA -> Review -> Approval/Merge.
"""

import logging
import asyncio
from typing import List, Dict, Any
from studio.utils.jules_client import JulesGitHubClient, WorkStatus
from studio.config import get_settings
from studio.subgraphs.engineer import node_qa_verifier, node_architect_gate, node_entropy_guard
from studio.memory import AgentState, JulesMetadata, CodeChangeArtifact, EngineeringState

logger = logging.getLogger("studio.agents.pr_monitor")

class PRMonitorAgent:
    def __init__(self):
        settings = get_settings()
        self.client = JulesGitHubClient(
            github_token=settings.github_token,
            repo_name=settings.github_repository,
            jules_username=settings.jules_username
        )

    async def monitor_and_review(self) -> List[int]:
        """
        Polls for open PRs and runs the autonomous review cycle on them.
        Returns a list of processed PR numbers.
        """
        logger.info("PR Monitor: Checking for open PRs...")

        # 1. Fetch Open PRs (Requires get_open_prs in client)
        try:
            prs = await asyncio.to_thread(self.client.get_open_prs)
        except Exception as e:
            logger.error(f"Failed to fetch PRs: {e}")
            return []

        processed_prs = []
        for pr_info in prs:
            pr_number = pr_info["number"]
            logger.info(f"PR Monitor: Analyzing PR #{pr_number}")

            # Skip PRs that are already being handled or have certain labels if needed

            # 2. Run Review Cycle
            # We construct a mock AgentState to reuse Engineer Subgraph nodes
            jules_meta = JulesMetadata(
                external_task_id=str(pr_number),
                status="VERIFYING",
                last_verified_commit=pr_info["last_commit_hash"],
                last_verified_pr_number=pr_number,
                generated_artifacts=[CodeChangeArtifact(
                    diff_content=pr_info["raw_diff"],
                    change_type="MODIFY",
                    pr_link=pr_info["url"]
                )]
            )

            state: AgentState = {
                "messages": [],
                "system_constitution": "ENFORCE SOLID.",
                "jules_metadata": jules_meta,
                "next_agent": None
            }

            # Run Nodes in sequence
            try:
                # A. Entropy Check
                state.update(await node_entropy_guard(state))
                if state["jules_metadata"].status == "FAILED":
                    logger.warning(f"PR #{pr_number} failed Entropy Check.")
                    continue

                # B. QA Verifier (Functional Tests)
                state.update(await node_qa_verifier(state))
                if state["jules_metadata"].status == "FAILED":
                    logger.warning(f"PR #{pr_number} failed QA Verification.")
                    # Feedback loop would normally post a comment here
                    continue

                # C. Architect Gate (Design Review & Merge)
                # This node automatically merges if approved!
                state.update(await node_architect_gate(state))

                if state["jules_metadata"].status == "COMPLETED":
                    logger.info(f"PR #{pr_number} successfully reviewed and merged.")
                    processed_prs.append(pr_number)
                else:
                    logger.warning(f"PR #{pr_number} rejected by Architect.")

            except Exception as e:
                logger.error(f"Error reviewing PR #{pr_number}: {e}")

        return processed_prs
