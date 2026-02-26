"""
studio/agents/architect.py
--------------------------
The Architect Agent (The Quality Guard).
Refactored based on Code Audit (2026-02-09).

Updates:
1. Context Awareness: Reviews FULL file content, not just diffs.
2. Topology Alignment: Operates on EngineeringState (Subgraph), not OrchestratorState.
3. Integrity: Verifies AGENTS.md hash against Governance Layer.
4. Granularity: Violations now include line numbers for GitHub integration.

Dependencies:
- Vertex AI
- studio.memory
"""

import logging
import hashlib
from typing import Optional, Dict, Any

from langchain_google_vertexai import ChatVertexAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser

# Import Memory Schema
from studio.memory import Violation, ReviewVerdict

logger = logging.getLogger("studio.agents.architect")

# --- THE AGENT ---

class ArchitectAgent:
    def __init__(self, model_name: str = "gemini-2.5-pro"):
        self.llm = ChatVertexAI(
            model_name=model_name,
            temperature=0.0, # Strict Determinism
            max_output_tokens=4096
        )
        self.parser = PydanticOutputParser(pydantic_object=ReviewVerdict)
        self.constitution_content = ""
        self.constitution_hash = ""
        self._load_constitution()

    def _load_constitution(self):
        """Loads and hashes the Constitution."""
        try:
            with open("AGENTS.md", "r") as f:
                self.constitution_content = f.read()
                self.constitution_hash = hashlib.sha256(self.constitution_content.encode()).hexdigest()
        except FileNotFoundError:
            logger.critical("AGENTS.md missing! Architect operating in emergency mode.")
            self.constitution_content = "CRITICAL: ENFORCE SOLID. NO AGENTS.MD FOUND."
            self.constitution_hash = "EMERGENCY_MODE"

    def review_code(self, file_path: str, full_source_code: str, ticket_context: str, governance_hash: Optional[str] = None) -> ReviewVerdict:
        """
        Conducts a deep architectural review of the FULL file content.

        Args:
            governance_hash: Optional hash from global state to ensure we aren't using stale laws.
        """
        # Integrity Check
        if governance_hash and governance_hash != self.constitution_hash:
            logger.warning(f"Constitution Mismatch! Disk: {self.constitution_hash[:8]}, State: {governance_hash[:8]}")
            # In strict mode, we might raise error. For MVP, we log and proceed (or reload).
            self._load_constitution()

        logger.info(f"Architect is reviewing full content of {file_path}...")

        prompt = ChatPromptTemplate.from_messages([
            ("system", """
            You are the Chief Architect. Review the following FULL SOURCE CODE for architectural integrity.
            You are NOT a linter. You look for Structural, Security, and SOLID violations.

            **THE CONSTITUTION:**
            {constitution}

            **REVIEW CRITERIA:**
            1. **SRP (Single Responsibility):** Does the class do too much?
            2. **DIP (Dependency Inversion):** Are we depending on concrete implementations instead of abstractions?
            3. **Security:** Hardcoded secrets? Unsafe exec?
            4. **Context:** Does this code actually solve Ticket {ticket_context}?

            **OUTPUT:**
            Provide a strict JSON verdict. Use `line_number` to point to the specific offense.
            """),
            ("user", """
            **Ticket:** {ticket_context}
            **File Path:** {file_path}

            **FULL SOURCE CODE:**
            ```python
            {code}
            ```

            {format_instructions}
            """)
        ])

        chain = prompt | self.llm | self.parser

        try:
            verdict = chain.invoke({
                "constitution": self.constitution_content[:10000], # Context management
                "ticket_context": ticket_context,
                "file_path": file_path,
                "code": full_source_code,
                "format_instructions": self.parser.get_format_instructions()
            })

            verdict = self._apply_good_enough_threshold(verdict)
            self._log_verdict(verdict)
            return verdict

        except Exception as e:
            logger.error(f"Architect review failed: {e}")
            return ReviewVerdict(
                status="REJECTED",
                quality_score=0.0,
                violations=[Violation(
                    rule_id="SYS-CRASH",
                    severity="CRITICAL",
                    description=f"LLM Error: {str(e)}",
                    file_path=file_path,
                    suggested_fix="Retry Review"
                )]
            )

    def _apply_good_enough_threshold(self, verdict: ReviewVerdict) -> ReviewVerdict:
        """
        Applies the 'Good Enough' threshold logic to avoid refactor loops.
        Score >= 8.0 and no CRITICAL violations = APPROVED_WITH_TECH_DEBT.
        """
        has_critical = any(v.severity == "CRITICAL" for v in verdict.violations)

        if verdict.quality_score >= 8.0 and not has_critical:
            # If not perfect (already APPROVED), we mark as Good Enough.
            if verdict.status != "APPROVED":
                verdict.status = "APPROVED_WITH_TECH_DEBT"

            # If status is APPROVED_WITH_TECH_DEBT, append the tag as per constraints.
            if verdict.status == "APPROVED_WITH_TECH_DEBT":
                tag = "#TODO: Tech Debt"
                if not verdict.tech_debt_tag:
                    verdict.tech_debt_tag = tag
                elif tag not in verdict.tech_debt_tag:
                    verdict.tech_debt_tag = f"{verdict.tech_debt_tag} {tag}".strip()

        return verdict

    def _log_verdict(self, verdict: ReviewVerdict):
        if verdict.status in ["APPROVED", "APPROVED_WITH_TECH_DEBT"]:
            logger.info(f"✅ Code {verdict.status} (Score: {verdict.quality_score})")
        else:
            logger.warning(f"❌ Code {verdict.status} (Score: {verdict.quality_score})")

# --- INTEGRATION HELPER (Patched) ---

def run_architect_gate(engineering_state: Dict[str, Any]):
    """
    Helper for the Engineer Subgraph.
    Operates on local 'EngineeringState', NOT global 'OrchestrationState'.
    """
    # 1. Access Local State (Subgraph Scoped)
    artifacts = engineering_state.get("code_artifacts", {})
    patch = artifacts.get("proposed_patch")

    if not patch:
        logger.error("No patch found to review.")
        return {"verification_gate": {"status": "RED", "blocking_reason": "No patch submitted"}}

    # 2. Context Reconstruction (Fixing Blindness)
    # In a real system, the 'Engineer' node would have loaded the file content
    # into the state (e.g., 'current_file_content').
    # For MVP, we assume it's available in 'workspace_snapshot' or passed explicitly.
    workspace = engineering_state.get("workspace_snapshot", {})

    # CRITICAL FIX: The Architect must review the file AS IT WOULD LOOK after the patch.
    # If we don't have the full content in memory, we assume 'current_file_content' is populated.
    full_source_code = workspace.get("current_file_content", "")

    if not full_source_code:
        # Fallback: If we only have the patch, we warn the system.
        logger.warning("Architect is reviewing a PATCH only (Context Blindness Risk).")
        full_source_code = patch

    file_path = workspace.get("current_file", "unknown.py")
    ticket_id = engineering_state.get("current_task", "UNKNOWN")

    # 3. Governance Check (Optional)
    # We could pull this from a 'governance' key if passed into the subgraph
    gov_hash = None

    # 4. Run Review
    architect = ArchitectAgent()
    verdict = architect.review_code(file_path, full_source_code, ticket_id, gov_hash)

    # 5. Return Subgraph Update
    # We update 'code_artifacts' with the report, and update 'verification_gate' status
    # 'APPROVED_WITH_TECH_DEBT' is also considered 'GREEN'.
    gate_status = "GREEN" if verdict.status in ["APPROVED", "APPROVED_WITH_TECH_DEBT"] else "RED"
    blocking_reason = None
    if gate_status == "RED":
        blocking_reason = "\n".join([f"ARCHITECT REJECT: {v.description}" for v in verdict.violations])

    return {
        "code_artifacts": {
            **artifacts,
            "static_analysis_report": verdict.model_dump() # Store the full report
        },
        "verification_gate": {
            "status": gate_status,
            "blocking_reason": blocking_reason
        }
    }
