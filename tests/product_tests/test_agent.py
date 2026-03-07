"""
Isolated pytest for BSPDiagnosticAgent.
All Anthropic API calls and SupervisorAgent are mocked — no LLM is invoked.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

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


def _make_mock_supervisor(route: str = "hardware_advisor") -> MagicMock:
    sup = MagicMock()
    sup.chunk_log.side_effect = lambda text: text
    sup.route.return_value = route
    return sup


@pytest.fixture
def std_failure_case():
    return CaseFile(
        case_id="TEST-STD-001",
        device_model="Pixel_Watch_Proto",
        source_code_mode="git",
        user_query="STD hibernation fails at Checkpoint 2",
        log_payload=LogPayload(
            dmesg_content=DMESG_STD_FAILURE,
            meminfo_content=MEMINFO_HIGH_SUNRECLAIM,
        ),
    )


# ---------------------------------------------------------------------------
# Helpers to build mock Anthropic responses
# ---------------------------------------------------------------------------

def _tool_use_response(tool_name: str, tool_id: str, tool_input: dict) -> MagicMock:
    block = SimpleNamespace(type="tool_use", name=tool_name, id=tool_id, input=tool_input)
    resp = MagicMock()
    resp.stop_reason = "tool_use"
    resp.content = [block]
    return resp


def _text_response(text: str) -> MagicMock:
    block = SimpleNamespace(type="text", text=text)
    resp = MagicMock()
    resp.stop_reason = "end_turn"
    resp.content = [block]
    return resp


# ---------------------------------------------------------------------------
# Tests — supervisor integration
# ---------------------------------------------------------------------------

class TestSupervisorIntegration:
    def test_supervisor_is_called_before_tool_loop(self, std_failure_case):
        mock_supervisor = _make_mock_supervisor("hardware_advisor")
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _text_response(
            json.dumps(VALID_CONSULTANT_RESPONSE)
        )

        agent = BSPDiagnosticAgent(client=mock_client, supervisor=mock_supervisor)
        agent.run(std_failure_case)

        mock_supervisor.chunk_log.assert_called_once_with(DMESG_STD_FAILURE)
        mock_supervisor.route.assert_called_once()

    def test_supervisor_clarify_needed_returns_early_without_llm(self, std_failure_case):
        mock_supervisor = _make_mock_supervisor("clarify_needed")
        mock_client = MagicMock()

        agent = BSPDiagnosticAgent(client=mock_client, supervisor=mock_supervisor)
        result = agent.run(std_failure_case)

        assert result.status == "CLARIFY_NEEDED"
        mock_client.messages.create.assert_not_called()

    def test_hardware_advisor_route_offers_std_tool(self, std_failure_case):
        mock_supervisor = _make_mock_supervisor("hardware_advisor")
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _text_response(
            json.dumps(VALID_CONSULTANT_RESPONSE)
        )

        agent = BSPDiagnosticAgent(client=mock_client, supervisor=mock_supervisor)
        agent.run(std_failure_case)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        tool_names = {t["name"] for t in call_kwargs["tools"]}
        assert "analyze_std_hibernation_error" in tool_names
        assert "decode_esr_el1" not in tool_names

    def test_kernel_pathologist_route_offers_aarch64_tools(self, std_failure_case):
        mock_supervisor = _make_mock_supervisor("kernel_pathologist")
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _text_response(
            json.dumps(VALID_CONSULTANT_RESPONSE)
        )

        agent = BSPDiagnosticAgent(client=mock_client, supervisor=mock_supervisor)
        agent.run(std_failure_case)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        tool_names = {t["name"] for t in call_kwargs["tools"]}
        assert "decode_esr_el1" in tool_names
        assert "check_cache_coherency_panic" in tool_names
        assert "analyze_std_hibernation_error" not in tool_names

    def test_user_message_includes_specialist_label(self, std_failure_case):
        mock_supervisor = _make_mock_supervisor("hardware_advisor")
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _text_response(
            json.dumps(VALID_CONSULTANT_RESPONSE)
        )

        agent = BSPDiagnosticAgent(client=mock_client, supervisor=mock_supervisor)
        agent.run(std_failure_case)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "Hardware Advisor" in user_content

    def test_user_message_includes_meminfo_content(self, std_failure_case):
        mock_supervisor = _make_mock_supervisor("hardware_advisor")
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _text_response(
            json.dumps(VALID_CONSULTANT_RESPONSE)
        )

        agent = BSPDiagnosticAgent(client=mock_client, supervisor=mock_supervisor)
        agent.run(std_failure_case)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "/proc/meminfo" in user_content
        assert "SUnreclaim" in user_content

    def test_user_message_omits_meminfo_section_when_empty(self):
        case = CaseFile(
            case_id="TEST-002",
            device_model="Dev",
            source_code_mode="git",
            user_query="panic",
            log_payload=LogPayload(dmesg_content="[  1.0] Kernel panic\n"),
        )
        mock_supervisor = _make_mock_supervisor("kernel_pathologist")
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _text_response(
            json.dumps(VALID_CONSULTANT_RESPONSE)
        )

        agent = BSPDiagnosticAgent(client=mock_client, supervisor=mock_supervisor)
        agent.run(case)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "/proc/meminfo" not in user_content


# ---------------------------------------------------------------------------
# Tests — tool-use loop behaviour
# ---------------------------------------------------------------------------

class TestAgentToolLoop:
    def test_agent_calls_hibernation_tool_and_returns_consultant_response(self, std_failure_case):
        mock_supervisor = _make_mock_supervisor("hardware_advisor")
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            _tool_use_response(
                "analyze_std_hibernation_error",
                "toolu_01",
                {"dmesg_log": DMESG_STD_FAILURE, "meminfo_log": MEMINFO_HIGH_SUNRECLAIM},
            ),
            _text_response(json.dumps(VALID_CONSULTANT_RESPONSE)),
        ]

        agent = BSPDiagnosticAgent(client=mock_client, supervisor=mock_supervisor)
        result = agent.run(std_failure_case)

        assert isinstance(result, ConsultantResponse)
        assert result.diagnosis_id == "RCA-STD-001"
        assert result.status == "CRITICAL"
        assert result.confidence_score == pytest.approx(0.92)

    def test_agent_makes_two_api_calls_for_tool_use_round(self, std_failure_case):
        mock_supervisor = _make_mock_supervisor("hardware_advisor")
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            _tool_use_response(
                "analyze_std_hibernation_error",
                "toolu_01",
                {"dmesg_log": DMESG_STD_FAILURE, "meminfo_log": MEMINFO_HIGH_SUNRECLAIM},
            ),
            _text_response(json.dumps(VALID_CONSULTANT_RESPONSE)),
        ]

        agent = BSPDiagnosticAgent(client=mock_client, supervisor=mock_supervisor)
        agent.run(std_failure_case)

        assert mock_client.messages.create.call_count == 2

    def test_agent_returns_clarify_when_end_turn_without_parseable_json(self, std_failure_case):
        mock_supervisor = _make_mock_supervisor("hardware_advisor")
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _text_response("I need more information.")

        agent = BSPDiagnosticAgent(client=mock_client, supervisor=mock_supervisor)
        result = agent.run(std_failure_case)

        assert result.status == "CLARIFY_NEEDED"
        assert result.confidence_score == 0.0

    def test_agent_returns_clarify_when_max_rounds_exceeded(self, std_failure_case):
        mock_supervisor = _make_mock_supervisor("hardware_advisor")
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _tool_use_response(
            "analyze_std_hibernation_error",
            "toolu_01",
            {"dmesg_log": DMESG_STD_FAILURE, "meminfo_log": MEMINFO_HIGH_SUNRECLAIM},
        )

        agent = BSPDiagnosticAgent(client=mock_client, supervisor=mock_supervisor, max_tool_rounds=2)
        result = agent.run(std_failure_case)

        assert result.status == "CLARIFY_NEEDED"
        assert mock_client.messages.create.call_count == 2

    def test_agent_passes_system_prompt_to_api(self, std_failure_case):
        mock_supervisor = _make_mock_supervisor("hardware_advisor")
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _text_response(
            json.dumps(VALID_CONSULTANT_RESPONSE)
        )

        agent = BSPDiagnosticAgent(client=mock_client, supervisor=mock_supervisor)
        agent.run(std_failure_case)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert "system" in call_kwargs
        assert "BSP" in call_kwargs["system"]


# ---------------------------------------------------------------------------
# Tests — markdown stripping
# ---------------------------------------------------------------------------

class TestAgentMarkdownStripping:
    def test_strips_markdown_code_fences_from_response(self, std_failure_case):
        fenced = f"```json\n{json.dumps(VALID_CONSULTANT_RESPONSE)}\n```"
        mock_supervisor = _make_mock_supervisor("hardware_advisor")
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _text_response(fenced)

        agent = BSPDiagnosticAgent(client=mock_client, supervisor=mock_supervisor)
        result = agent.run(std_failure_case)

        assert isinstance(result, ConsultantResponse)
        assert result.status == "CRITICAL"


# ---------------------------------------------------------------------------
# Tests — _clarify_response helper
# ---------------------------------------------------------------------------

class TestClarifyResponse:
    def test_clarify_response_has_correct_structure(self):
        result = _clarify_response("CASE-99", "Test reason")

        assert result.status == "CLARIFY_NEEDED"
        assert result.confidence_score == 0.0
        assert "CASE-99" in result.diagnosis_id
        assert len(result.sop_steps) >= 1

    def test_clarify_response_is_consultant_response(self):
        assert isinstance(_clarify_response("CASE-99", "Test reason"), ConsultantResponse)
