"""
Isolated pytest for BSPDiagnosticAgent.
All Anthropic API calls are mocked — no LLM is invoked.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from product.bsp_agent.agent import BSPDiagnosticAgent, _clarify_response
from product.schemas import CaseFile, ConsultantResponse, LogPayload

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DMESG_STD_FAILURE = """\
[  100.000000] PM: Syncing filesystems ... done.
[  100.123456] PM: Creating hibernation image:
[  100.234567] Error -12 creating hibernation image
[  100.345678] PM: Image saving failed, cleaning up.
"""

MEMINFO_HIGH_SUNRECLAIM = """\
MemTotal:        2097152 kB
MemFree:          512000 kB
SUnreclaim:       307200 kB
SwapTotal:       2097152 kB
SwapFree:        1500000 kB
"""

VALID_CONSULTANT_RESPONSE = {
    "diagnosis_id": "RCA-STD-001",
    "confidence_score": 0.92,
    "status": "CRITICAL",
    "root_cause_summary": "SUnreclaim exceeds 10% of MemTotal preventing hibernation.",
    "evidence": ["Error -12 creating hibernation image", "SUnreclaim: 307200 kB"],
    "sop_steps": [
        {
            "step_id": 1,
            "action_type": "CODE_PATCH",
            "instruction": "echo 3 > /proc/sys/vm/drop_caches",
            "expected_value": "SUnreclaim drops below threshold",
            "file_path": "N/A",
        }
    ],
}


@pytest.fixture
def std_failure_case():
    return CaseFile(
        case_id="TEST-STD-001",
        device_model="Pixel_Watch_Proto",
        source_code_mode="git",
        user_query="STD hibernation fails at Checkpoint 2",
        log_payload=LogPayload(
            dmesg_content=DMESG_STD_FAILURE,
            logcat_content=MEMINFO_HIGH_SUNRECLAIM,
        ),
    )


# ---------------------------------------------------------------------------
# Helpers to build mock Anthropic responses
# ---------------------------------------------------------------------------

def _tool_use_response(tool_name: str, tool_id: str, tool_input: dict) -> MagicMock:
    """Build a mock response that requests a tool call."""
    block = SimpleNamespace(type="tool_use", name=tool_name, id=tool_id, input=tool_input)
    resp = MagicMock()
    resp.stop_reason = "tool_use"
    resp.content = [block]
    return resp


def _text_response(text: str) -> MagicMock:
    """Build a mock response with a text block."""
    block = SimpleNamespace(type="text", text=text)
    resp = MagicMock()
    resp.stop_reason = "end_turn"
    resp.content = [block]
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAgentToolLoop:
    def test_agent_calls_hibernation_tool_and_returns_consultant_response(self, std_failure_case):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            _tool_use_response(
                "analyze_std_hibernation_error",
                "toolu_01",
                {
                    "dmesg_log": DMESG_STD_FAILURE,
                    "meminfo_log": MEMINFO_HIGH_SUNRECLAIM,
                },
            ),
            _text_response(json.dumps(VALID_CONSULTANT_RESPONSE)),
        ]

        agent = BSPDiagnosticAgent(client=mock_client)
        result = agent.run(std_failure_case)

        assert isinstance(result, ConsultantResponse)
        assert result.diagnosis_id == "RCA-STD-001"
        assert result.status == "CRITICAL"
        assert result.confidence_score == pytest.approx(0.92)

    def test_agent_makes_two_api_calls_for_tool_use_round(self, std_failure_case):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            _tool_use_response(
                "analyze_std_hibernation_error",
                "toolu_01",
                {"dmesg_log": DMESG_STD_FAILURE, "meminfo_log": MEMINFO_HIGH_SUNRECLAIM},
            ),
            _text_response(json.dumps(VALID_CONSULTANT_RESPONSE)),
        ]

        agent = BSPDiagnosticAgent(client=mock_client)
        agent.run(std_failure_case)

        assert mock_client.messages.create.call_count == 2

    def test_agent_returns_clarify_when_end_turn_on_first_call(self, std_failure_case):
        """If Claude gives end_turn immediately with no parseable JSON, return CLARIFY_NEEDED."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _text_response("I need more information.")

        agent = BSPDiagnosticAgent(client=mock_client)
        result = agent.run(std_failure_case)

        assert result.status == "CLARIFY_NEEDED"
        assert result.confidence_score == 0.0

    def test_agent_returns_clarify_when_max_rounds_exceeded(self, std_failure_case):
        """Agent should give up and return CLARIFY after hitting max_tool_rounds."""
        mock_client = MagicMock()
        # Always return tool_use, never end_turn
        mock_client.messages.create.return_value = _tool_use_response(
            "analyze_std_hibernation_error",
            "toolu_01",
            {"dmesg_log": DMESG_STD_FAILURE, "meminfo_log": MEMINFO_HIGH_SUNRECLAIM},
        )

        agent = BSPDiagnosticAgent(client=mock_client, max_tool_rounds=2)
        result = agent.run(std_failure_case)

        assert result.status == "CLARIFY_NEEDED"
        assert mock_client.messages.create.call_count == 2

    def test_agent_passes_system_prompt_to_api(self, std_failure_case):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _text_response(
            json.dumps(VALID_CONSULTANT_RESPONSE)
        )

        agent = BSPDiagnosticAgent(client=mock_client)
        agent.run(std_failure_case)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert "system" in call_kwargs
        assert "BSP" in call_kwargs["system"]

    def test_agent_passes_tool_definitions_to_api(self, std_failure_case):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _text_response(
            json.dumps(VALID_CONSULTANT_RESPONSE)
        )

        agent = BSPDiagnosticAgent(client=mock_client)
        agent.run(std_failure_case)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert "tools" in call_kwargs
        tool_names = [t["name"] for t in call_kwargs["tools"]]
        assert "analyze_std_hibernation_error" in tool_names


class TestAgentMarkdownStripping:
    def test_strips_markdown_code_fences_from_response(self, std_failure_case):
        fenced = f"```json\n{json.dumps(VALID_CONSULTANT_RESPONSE)}\n```"
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _text_response(fenced)

        agent = BSPDiagnosticAgent(client=mock_client)
        result = agent.run(std_failure_case)

        assert isinstance(result, ConsultantResponse)
        assert result.status == "CRITICAL"


class TestClarifyResponse:
    def test_clarify_response_has_correct_structure(self):
        result = _clarify_response("CASE-99", "Test reason")

        assert result.status == "CLARIFY_NEEDED"
        assert result.confidence_score == 0.0
        assert "CASE-99" in result.diagnosis_id
        assert len(result.sop_steps) >= 1

    def test_clarify_response_is_consultant_response(self):
        result = _clarify_response("CASE-99", "Test reason")
        assert isinstance(result, ConsultantResponse)
