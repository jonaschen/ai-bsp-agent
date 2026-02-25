"""
tests/test_architect_stability_protocol.py
------------------------------------------
Tests for the Architect Stability Protocol (AGENTS.md §1.1).

TDD Compliance:
- Follow Red-Green-Refactor cycle.
- Verify the Architect is limited to ONE (1) refactor attempt per Green solution.
- Verify fallback to Green state with #TODO: Tech Debt tag when limit is exceeded.
- Verify reviewer is reminded to follow TDD and AGENTS.md compliance.
"""

import os
import sys
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "mock-project")

from studio.memory import (
    JulesMetadata, ReviewVerdict, Violation, AgentState, ContextSlice,
    CodeChangeArtifact
)


def _make_state(architect_refactor_attempts: int = 0, status: str = "COMPLETED") -> AgentState:
    """Helper: build a minimal AgentState for architect gate tests."""
    jules = JulesMetadata(
        session_id="test-session",
        status=status,
        architect_refactor_attempts=architect_refactor_attempts,
        current_task_prompt="Implement feature X",
        generated_artifacts=[
            CodeChangeArtifact(diff_content="--- a/src/app.py\n+++ b/src/app.py\n@@ -1 +1 @@\n-old\n+new")
        ],
        active_context_slice=ContextSlice(files=["src/app.py"]),
    )
    return {"messages": [], "system_constitution": "", "next_agent": None, "jules_metadata": jules}


def _rejection_verdict(description: str = "Class is doing too much") -> ReviewVerdict:
    return ReviewVerdict(
        status="REJECTED",
        quality_score=3.0,
        violations=[Violation(
            rule_id="SOLID-SRP",
            severity="MAJOR",
            description=description,
            file_path="src/app.py",
            suggested_fix="Split into smaller classes"
        )]
    )


class TestArchitectStabilityProtocol:
    """
    Tests enforcing AGENTS.md §1.1 Stability Protocol:
    - Architect gets ONE (1) refactor attempt.
    - On second rejection, system falls back to Green with #TODO: Tech Debt.
    """

    @pytest.mark.asyncio
    async def test_first_architect_rejection_increments_counter(self):
        """
        First architectural rejection: refactor attempt counter increments
        and status becomes FAILED to trigger feedback loop.
        """
        with patch("studio.subgraphs.engineer.ArchitectAgent") as mock_architect_class, \
             patch("studio.subgraphs.engineer.apply_virtual_patch") as mock_patch, \
             patch("studio.subgraphs.engineer.os.path.exists", return_value=True), \
             patch("studio.subgraphs.engineer.open", MagicMock()):

            from studio.subgraphs.engineer import node_architect_gate

            mock_architect = mock_architect_class.return_value
            mock_architect.review_code.return_value = _rejection_verdict()
            mock_patch.return_value = {"src/app.py": "class BigClass: pass"}

            state = _make_state(architect_refactor_attempts=0)
            result = await node_architect_gate(state)

        jules = result["jules_metadata"]
        assert jules.status == "FAILED", "First rejection must set status=FAILED to trigger refactor loop"
        assert jules.architect_refactor_attempts == 1, "Counter must be incremented on first rejection"
        assert any("ARCHITECTURAL REVIEW FAILED" in log for log in jules.feedback_log)

    @pytest.mark.asyncio
    async def test_stability_protocol_fallback_on_second_rejection(self):
        """
        AGENTS.md §1.1 Stability Protocol:
        After ONE refactor attempt (architect_refactor_attempts >= 1),
        a second rejection must fall back to Green state with #TODO: Tech Debt.
        """
        with patch("studio.subgraphs.engineer.ArchitectAgent") as mock_architect_class, \
             patch("studio.subgraphs.engineer.apply_virtual_patch") as mock_patch, \
             patch("studio.subgraphs.engineer.os.path.exists", return_value=True), \
             patch("studio.subgraphs.engineer.open", MagicMock()):

            from studio.subgraphs.engineer import node_architect_gate

            mock_architect = mock_architect_class.return_value
            mock_architect.review_code.return_value = _rejection_verdict()
            mock_patch.return_value = {"src/app.py": "class BigClass: pass"}

            # Simulate: already attempted one refactor
            state = _make_state(architect_refactor_attempts=1)
            result = await node_architect_gate(state)

        jules = result["jules_metadata"]
        # Stability Protocol: must approve (fallback to Green)
        assert jules.status == "COMPLETED", (
            "Stability Protocol: after 1 refactor attempt, must fall back to Green (COMPLETED)"
        )
        # Tech debt tag must be present in feedback
        assert any("#TODO: Tech Debt" in log for log in jules.feedback_log), (
            "Stability Protocol: fallback must mark code with #TODO: Tech Debt"
        )

    @pytest.mark.asyncio
    async def test_tech_debt_tag_contains_violation_details(self):
        """
        The #TODO: Tech Debt tag must include the deferred violation details
        so future developers know what needs fixing.
        """
        with patch("studio.subgraphs.engineer.ArchitectAgent") as mock_architect_class, \
             patch("studio.subgraphs.engineer.apply_virtual_patch") as mock_patch, \
             patch("studio.subgraphs.engineer.os.path.exists", return_value=True), \
             patch("studio.subgraphs.engineer.open", MagicMock()):

            from studio.subgraphs.engineer import node_architect_gate

            mock_architect = mock_architect_class.return_value
            mock_architect.review_code.return_value = _rejection_verdict("God class with 20 responsibilities")
            mock_patch.return_value = {"src/app.py": "class God: pass"}

            state = _make_state(architect_refactor_attempts=1)
            result = await node_architect_gate(state)

        jules = result["jules_metadata"]
        tech_debt_logs = [log for log in jules.feedback_log if "#TODO: Tech Debt" in log]
        assert tech_debt_logs, "Tech debt log entry must be present"
        assert "God class with 20 responsibilities" in tech_debt_logs[0], (
            "Tech debt tag must include the violation description"
        )

    @pytest.mark.asyncio
    async def test_architect_approval_resets_no_counter(self):
        """
        When Architect approves on the first review, status stays COMPLETED
        and architect_refactor_attempts stays at 0.
        """
        with patch("studio.subgraphs.engineer.ArchitectAgent") as mock_architect_class, \
             patch("studio.subgraphs.engineer.apply_virtual_patch") as mock_patch, \
             patch("studio.subgraphs.engineer.os.path.exists", return_value=True), \
             patch("studio.subgraphs.engineer.open", MagicMock()):

            from studio.subgraphs.engineer import node_architect_gate

            mock_architect = mock_architect_class.return_value
            mock_architect.review_code.return_value = ReviewVerdict(
                status="APPROVED",
                quality_score=9.5,
                violations=[]
            )
            mock_patch.return_value = {"src/app.py": "class Clean: pass"}

            state = _make_state(architect_refactor_attempts=0)
            result = await node_architect_gate(state)

        jules = result["jules_metadata"]
        assert jules.status == "COMPLETED", "Approved code must keep COMPLETED status"
        assert jules.architect_refactor_attempts == 0, "Counter must not increase on approval"


class TestArchitectRefactorAttemptField:
    """Tests for the architect_refactor_attempts field on JulesMetadata."""

    def test_jules_metadata_has_architect_refactor_attempts_field(self):
        """
        JulesMetadata must have architect_refactor_attempts field defaulting to 0.
        AGENTS.md §1.1 requires tracking refactor attempts.
        """
        jules = JulesMetadata(session_id="test")
        assert hasattr(jules, "architect_refactor_attempts")
        assert jules.architect_refactor_attempts == 0

    def test_review_verdict_supports_approved_with_tech_debt(self):
        """
        ReviewVerdict must support APPROVED_WITH_TECH_DEBT status for
        Stability Protocol fallback (AGENTS.md §1.1).
        """
        verdict = ReviewVerdict(
            status="APPROVED_WITH_TECH_DEBT",
            quality_score=5.0,
            violations=[],
            tech_debt_tag="#TODO: Tech Debt - Refactor needed"
        )
        assert verdict.status == "APPROVED_WITH_TECH_DEBT"
        assert verdict.tech_debt_tag is not None
