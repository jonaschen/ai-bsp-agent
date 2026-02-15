import pytest
import os
from unittest.mock import MagicMock, patch
from studio.memory import (
    JulesMetadata, ContextSlice, CodeChangeArtifact, ReviewVerdict
)
from studio.subgraphs.engineer import node_architect_gate

@pytest.mark.asyncio
async def test_context_fidelity(tmp_path, monkeypatch):
    """
    "Context Fidelity" Test (現場還原測試)
    驗證 node_architect_gate 是否真的拿到了完整的檔案內容，解決 "Context Blindness" 問題。
    情境：
    1. 模擬一個只包含 diff 的 jules_metadata。
    2. 模擬 active_context_slice 指向一個真實存在的檔案。
    驗證點：
    在 Mock 的 Architect Agent 被呼叫時，傳入的 full_source_code 參數必須是 「原始檔案 + Patch」 的結果，而不僅僅是 Patch 本身。
    """

    # 1. Prepare Workspace
    file_path = "src/logic.py"
    # Note: apply_virtual_patch uses relpath, so we need to match the structure
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    logic_file = src_dir / "logic.py"

    original_content = "def calculate(a, b):\n    return a + b\n"
    logic_file.write_text(original_content)

    # Create dummy AGENTS.md as ArchitectAgent looks for it
    (tmp_path / "AGENTS.md").write_text("# Constitution")

    # Change current working directory to tmp_path
    monkeypatch.chdir(tmp_path)

    # 2. Prepare Diff
    # Unified diff format
    diff_content = (
        f"--- a/{file_path}\n"
        f"+++ b/{file_path}\n"
        "@@ -1,2 +1,2 @@\n"
        " def calculate(a, b):\n"
        "-    return a + b\n"
        "+    return a * b\n"
    )
    expected_full_source = "def calculate(a, b):\n    return a * b\n"

    # 3. Setup Agent State
    jules_data = JulesMetadata(
        session_id="fidelity-session",
        status="COMPLETED",
        active_context_slice=ContextSlice(files=[file_path]),
        generated_artifacts=[CodeChangeArtifact(diff_content=diff_content, change_type="MODIFY")]
    )
    # The node expects AgentState which is a TypedDict (or similar) containing jules_metadata
    state = {"jules_metadata": jules_data}

    # 4. Mock Architect Agent
    with patch("studio.subgraphs.engineer.ArchitectAgent") as MockArchitect:
        mock_architect_instance = MockArchitect.return_value
        # Mock the review_code to return an approved verdict
        mock_architect_instance.review_code.return_value = ReviewVerdict(
            status="APPROVED",
            quality_score=10.0,
            violations=[]
        )

        # 5. Execute the Node
        # We don't mock apply_virtual_patch to ensure we test the full reconstruction logic
        await node_architect_gate(state)

        # 6. Verification
        mock_architect_instance.review_code.assert_called_once()
        args, kwargs = mock_architect_instance.review_code.call_args

        # args[0] is file_path, args[1] is full_source_code
        called_file_path = args[0]
        called_full_source = args[1]

        assert called_file_path == file_path
        assert called_full_source == expected_full_source, (
            f"Expected full source:\n{expected_full_source}\n"
            f"Actually received:\n{called_full_source}\n"
            "The Architect Agent should receive the FULL patched content, not just the diff."
        )

if __name__ == "__main__":
    # If run directly, use pytest
    import sys
    pytest.main([__file__])
