import unittest
from unittest.mock import MagicMock, patch, mock_open
import hashlib
import sys
import os

# Ensure studio can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from studio.agents.architect import ArchitectAgent, run_architect_gate, ReviewVerdict, Violation

class TestIntegrity(unittest.TestCase):
    @patch("studio.agents.architect.ChatVertexAI")
    @patch("studio.agents.architect.PydanticOutputParser")
    def test_constitution_tampering(self, mock_parser, mock_llm):
        """
        目標： 驗證 ArchitectAgent 的 governance_hash 檢查機制。
        情境： 在測試中修改磁碟上的 AGENTS.md 內容，但傳入舊的 governance_hash 給 review_code 方法。
        預期： Agent 應偵測到 Hash 不匹配，並發出 WARNING 或重新載入憲法。
        """
        original_content = "original laws"
        tampered_content = "tampered laws"
        original_hash = hashlib.sha256(original_content.encode()).hexdigest()
        tampered_hash = hashlib.sha256(tampered_content.encode()).hexdigest()

        # 1. Initialize with original content
        with patch("builtins.open", mock_open(read_data=original_content)):
            agent = ArchitectAgent()
            self.assertEqual(agent.constitution_hash, original_hash)

        # 2. Simulate disk content change and call review_code with new hash
        # The logic is: if governance_hash != self.constitution_hash, reload.
        # If we pass tampered_hash as governance_hash, and agent still has original_hash, it should reload.
        with patch("builtins.open", mock_open(read_data=tampered_content)):
            # Mock LLM verdict
            mock_parser_instance = mock_parser.return_value
            mock_parser_instance.invoke.return_value = ReviewVerdict(
                status="APPROVED",
                quality_score=10.0,
                violations=[]
            )

            # Call review_code with tampered_hash (representing the "State" or "New Law")
            # This should trigger _load_constitution() because tampered_hash != original_hash
            agent.review_code("test.py", "print('hello')", "TKT-1", governance_hash=tampered_hash)

            # Verify that agent's constitution_hash is now the tampered one
            self.assertEqual(agent.constitution_hash, tampered_hash)
            self.assertEqual(agent.constitution_content, tampered_content)

    @patch("studio.agents.architect.ArchitectAgent")
    def test_context_blindness(self, MockArchitectAgent):
        """
        目標： 驗證 run_architect_gate 的容錯邏輯。
        情境： 在 engineering_state 中只提供 proposed_patch，但不提供 workspace_snapshot (模擬檔案讀取失敗)。
        預期： 系統應觸發 fallback 邏輯，印出 "Reviewing a PATCH only" 警告，但不能報錯，必須繼續完成審查。
        """
        mock_agent_instance = MockArchitectAgent.return_value
        mock_verdict = ReviewVerdict(
            status="APPROVED",
            quality_score=9.0,
            violations=[]
        )
        mock_agent_instance.review_code.return_value = mock_verdict

        # engineering_state without workspace_snapshot
        engineering_state = {
            "code_artifacts": {
                "proposed_patch": "PATCH_ONLY_CONTENT"
            },
            # workspace_snapshot is missing
            "current_task": "TKT-BLIND"
        }

        with self.assertLogs("studio.agents.architect", level="WARNING") as cm:
            result = run_architect_gate(engineering_state)

            # Check for the expected warning message
            self.assertTrue(any("Architect is reviewing a PATCH only" in output for output in cm.output))

        self.assertEqual(result["verification_gate"]["status"], "GREEN")
        self.assertEqual(result["code_artifacts"]["static_analysis_report"]["status"], "APPROVED")

        # Verify that the patch was used as the source code for the review
        mock_agent_instance.review_code.assert_called_once()
        args, _ = mock_agent_instance.review_code.call_args
        # args[1] is full_source_code
        self.assertEqual(args[1], "PATCH_ONLY_CONTENT")

if __name__ == '__main__':
    unittest.main()
