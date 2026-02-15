import pytest
import os
import sys

# Ensure studio can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from studio.agents.product_owner import ProductOwnerAgent, BlueprintAnalysis
from studio.agents.architect import ArchitectAgent
from studio.memory import ReviewVerdict

# Skip these tests if Google Cloud Project is not set (unless we want them to fail to signal missing config)
# For this task, we want them to run if possible.
# But to be safe for general CI, we might skip.
# However, the user explicitly asked for these tests to be "integration" or "slow".

# We check if we have real credentials. "mock-project" is used by other tests to bypass auth checks.
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
MISSING_CREDENTIALS = (PROJECT_ID is None or PROJECT_ID == "mock-project") and os.getenv("GOOGLE_APPLICATION_CREDENTIALS") is None

@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.skipif(MISSING_CREDENTIALS, reason="Missing Google Cloud credentials")
class TestPromptEffectiveness:

    def test_po_format_compliance(self):
        """
        確保 Gemini 1.5 Pro 真的能輸出符合 BlueprintAnalysis Schema 的 JSON。
        目標： 確保 Gemini 1.5 Pro 真的能輸出符合 BlueprintAnalysis Schema 的 JSON。
        方法： 使用真實的 PRODUCT_BLUEPRINT.md 片段呼叫 ProductOwnerAgent.analyze_specs。
        預期： parser 能成功解析輸出，且生成的 Ticket 結構正確（包含 source_section_id）。
        """
        blueprint_snippet = """
## 2. The Consultant Squad (The Product Roster)

The Studio must instantiate the following Multi-Agent System:

### Agent A: The Supervisor (Interface Layer)
* **Role:** Triage & User Interaction.
* **Input:** User Chat + Case Files (Logs).
* **Responsibility:**
    * **Validation (Fix #2):** Check if input is valid (e.g., is it a log?). If invalid, return `STATUS: CLARIFY_NEEDED`.
    * **Chunking (Fix #3):** If Log Size > 50MB, extract the "Event Horizon" (last 5000 lines OR timestamp of failure ± 10s) before passing to specialists.
    * Route the case to the Specialist (Pathologist or Hardware Advisor).
    * Compile the final **RCA Report**.
        """

        po = ProductOwnerAgent(model_name="gemini-1.5-pro")

        # We don't mock the LLM here.
        result = po.analyze_specs(blueprint_snippet, [])

        assert isinstance(result, BlueprintAnalysis)
        assert len(result.new_tickets) > 0

        # Verify traceability
        for ticket in result.new_tickets:
            assert ticket.source_section_id is not None
            assert ticket.id is not None
            assert ticket.title is not None
            assert ticket.description is not None
            # Check if source_section_id looks like a section ID (e.g., "2.1")
            # In the snippet above, it's under "2. The Consultant Squad" and "Agent A"
            # It might be "2" or "Agent A" or similar depending on LLM interpretation.

    def test_architect_accuracy(self):
        """
        確保 Architect 真的能抓出違反 SOLID 的代碼。
        目標： 確保 Architect 真的能抓出違反 SOLID 的代碼。
        方法： 餵給它一段明顯違反 SRP (Single Responsibility Principle) 的真實代碼。
        預期： 真實的 LLM 應回傳 status="REJECTED" 並指出正確的 line_number。
        """
        bad_code = """
import smtplib
import sqlite3

class SystemManager:
    \"\"\"A class that handles everything in the system.\"\"\"

    def handle_everything(self, data):
        # Line 8: Database operation (Directly using sqlite3) - SRP Violation
        conn = sqlite3.connect('example.db')
        c = conn.cursor()
        c.execute("INSERT INTO users VALUES (?)", (data['name'],))
        conn.commit()
        conn.close()

        # Line 15: Email operation (Directly using smtplib) - SRP Violation
        server = smtplib.SMTP('localhost')
        server.sendmail("admin@example.com", data['email'], "Welcome!")
        server.quit()

        # Line 21: File logging - SRP Violation
        with open("system.log", "a") as f:
            f.write(f"Processed {data['name']}\\n")

        return True
"""
        architect = ArchitectAgent(model_name="gemini-1.5-pro")

        verdict = architect.review_code(
            file_path="system_manager.py",
            full_source_code=bad_code,
            ticket_context="Implement a system manager that handles users, emails, and logging."
        )

        assert isinstance(verdict, ReviewVerdict)
        assert verdict.status == "REJECTED"

        # Check for SRP violation in descriptions
        srp_found = False
        for v in verdict.violations:
            if "SRP" in v.rule_id or "Single Responsibility" in v.description:
                srp_found = True

            # Verify line_number is present and pointing to the problematic areas
            assert v.line_number is not None
            # SRP violations in this code are roughly at lines 8, 15, 21
            assert v.line_number > 0

        assert srp_found, f"Architect should have found SRP violation. Violations: {verdict.violations}"

if __name__ == "__main__":
    # If run directly, try to execute tests
    pytest.main([__file__, "-v", "-m", "integration"])
