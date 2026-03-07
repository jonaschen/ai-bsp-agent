"""
End-to-end integration tests for the full diagnostic pipeline.

Tests the complete flow:
    CaseFile → SupervisorAgent (mocked LLM) → BSPDiagnosticAgent (mocked LLM) → ConsultantResponse

The Anthropic client is mocked at the boundary so no real API calls are made.
Because BSPDiagnosticAgent shares its client with SupervisorAgent by default,
the mock intercepts calls in order:
    call 0 → supervisor triage  (returns routing token)
    call 1 → agent tool-use or end_turn  (returns ConsultantResponse JSON)

Fixture files used are the golden-set logs in tests/fixtures/.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from product.bsp_agent.agent import BSPDiagnosticAgent
from product.schemas import CaseFile, ConsultantResponse, LogPayload

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _triage_response(token: str) -> MagicMock:
    """Mock Haiku triage call that returns a routing token."""
    resp = MagicMock()
    resp.content = [SimpleNamespace(text=token)]
    return resp


def _agent_response(body: dict) -> MagicMock:
    """Mock Sonnet end_turn call that returns a ConsultantResponse JSON."""
    resp = MagicMock()
    resp.stop_reason = "end_turn"
    resp.content = [SimpleNamespace(type="text", text=json.dumps(body))]
    return resp


def _make_client(supervisor_token: str, agent_body: dict | None = None) -> MagicMock:
    """
    Build a mock Anthropic client whose .messages.create() returns:
      - call 0: supervisor triage response
      - call 1: agent response (if supervisor_token != 'clarify_needed')
    """
    client = MagicMock()
    if supervisor_token == "clarify_needed" or agent_body is None:
        client.messages.create.return_value = _triage_response(supervisor_token)
    else:
        client.messages.create.side_effect = [
            _triage_response(supervisor_token),
            _agent_response(agent_body),
        ]
    return client


def _load_expected(filename: str) -> dict:
    return json.loads((FIXTURES / filename).read_text())


def _make_case(log_file: str, meminfo_file: str | None = None, case_id: str = "INT-TEST") -> CaseFile:
    dmesg = (FIXTURES / log_file).read_text()
    meminfo = (FIXTURES / meminfo_file).read_text() if meminfo_file else ""
    return CaseFile(
        case_id=case_id,
        device_model="Test_Device",
        source_code_mode="USER_UPLOADED",
        user_query="Diagnose this kernel log.",
        log_payload=LogPayload(dmesg_content=dmesg, meminfo_content=meminfo),
    )


# ---------------------------------------------------------------------------
# Scenario 1 — Kernel panic (panic_log_01.txt → kernel_pathologist)
# ---------------------------------------------------------------------------

class TestKernelPanicPipeline:
    @pytest.fixture
    def expected(self):
        return _load_expected("expected_output_panic_log_01.json")

    @pytest.fixture
    def agent(self, expected):
        client = _make_client("kernel_pathologist", expected)
        return BSPDiagnosticAgent(client=client)

    @pytest.fixture
    def result(self, agent):
        case = _make_case("panic_log_01.txt", case_id="INT-PANIC-01")
        return agent.run(case)

    def test_returns_consultant_response(self, result):
        assert isinstance(result, ConsultantResponse)

    def test_status_is_critical(self, result):
        assert result.status == "CRITICAL"

    def test_confidence_is_high(self, result):
        assert result.confidence_score >= 0.9

    def test_has_evidence(self, result):
        assert len(result.evidence) >= 1

    def test_has_sop_steps(self, result):
        assert len(result.sop_steps) >= 1

    def test_supervisor_called_first(self, agent):
        case = _make_case("panic_log_01.txt", case_id="INT-PANIC-02")
        agent.run(case)
        first_call = agent._client.messages.create.call_args_list[0]
        # Supervisor uses max_tokens=16 (triage-only)
        assert first_call.kwargs.get("max_tokens") == 16

    def test_kernel_pathologist_tools_offered_to_agent(self, agent):
        case = _make_case("panic_log_01.txt", case_id="INT-PANIC-03")
        agent.run(case)
        second_call = agent._client.messages.create.call_args_list[1]
        tool_names = {t["name"] for t in second_call.kwargs["tools"]}
        assert "decode_esr_el1" in tool_names
        assert "check_cache_coherency_panic" in tool_names
        assert "analyze_std_hibernation_error" not in tool_names

    def test_user_message_contains_log_content(self, agent):
        case = _make_case("panic_log_01.txt", case_id="INT-PANIC-04")
        agent.run(case)
        second_call = agent._client.messages.create.call_args_list[1]
        user_msg = second_call.kwargs["messages"][0]["content"]
        assert "Kernel Pathologist" in user_msg
        assert "INT-PANIC-04" in user_msg


# ---------------------------------------------------------------------------
# Scenario 2 — Watchdog / hard lockup during suspend (suspend_hang_02.txt → kernel_pathologist)
# ---------------------------------------------------------------------------

class TestWatchdogSuspendPipeline:
    @pytest.fixture
    def expected(self):
        return _load_expected("expected_output_suspend_hang_02.json")

    @pytest.fixture
    def agent(self, expected):
        client = _make_client("kernel_pathologist", expected)
        return BSPDiagnosticAgent(client=client)

    @pytest.fixture
    def result(self, agent):
        case = _make_case("suspend_hang_02.txt", case_id="INT-HANG-01")
        return agent.run(case)

    def test_returns_consultant_response(self, result):
        assert isinstance(result, ConsultantResponse)

    def test_status_is_critical(self, result):
        assert result.status == "CRITICAL"

    def test_diagnosis_id_is_set(self, result):
        assert result.diagnosis_id and result.diagnosis_id != ""

    def test_has_at_least_one_sop_step(self, result):
        assert len(result.sop_steps) >= 1

    def test_sop_step_has_valid_action_type(self, result):
        for step in result.sop_steps:
            assert step.action_type in ("MEASUREMENT", "CODE_PATCH")

    def test_two_llm_calls_made(self, agent):
        case = _make_case("suspend_hang_02.txt", case_id="INT-HANG-02")
        agent.run(case)
        assert agent._client.messages.create.call_count == 2


# ---------------------------------------------------------------------------
# Scenario 3 — Healthy boot (healthy_boot_03.txt → clarify_needed)
# ---------------------------------------------------------------------------

class TestHealthyBootPipeline:
    @pytest.fixture
    def agent(self):
        # Supervisor returns clarify_needed — agent LLM never called
        client = _make_client("clarify_needed")
        return BSPDiagnosticAgent(client=client)

    @pytest.fixture
    def result(self, agent):
        case = _make_case("healthy_boot_03.txt", case_id="INT-HEALTHY-01")
        return agent.run(case)

    def test_returns_consultant_response(self, result):
        assert isinstance(result, ConsultantResponse)

    def test_status_is_clarify_needed(self, result):
        assert result.status == "CLARIFY_NEEDED"

    def test_confidence_is_zero(self, result):
        assert result.confidence_score == 0.0

    def test_only_supervisor_llm_call_made(self, agent):
        case = _make_case("healthy_boot_03.txt", case_id="INT-HEALTHY-02")
        agent.run(case)
        # One call: supervisor triage. Agent loop never starts.
        assert agent._client.messages.create.call_count == 1

    def test_clarify_response_has_sop_step(self, result):
        assert len(result.sop_steps) >= 1
        assert result.sop_steps[0].action_type == "MEASUREMENT"


# ---------------------------------------------------------------------------
# Cross-scenario — schema conformance for all fixture expected outputs
# ---------------------------------------------------------------------------

class TestFixtureSchemaConformance:
    @pytest.mark.parametrize("json_file", [
        "expected_output_panic_log_01.json",
        "expected_output_suspend_hang_02.json",
        "expected_output_healthy_boot_03.json",
    ])
    def test_expected_output_parses_as_consultant_response(self, json_file):
        data = _load_expected(json_file)
        response = ConsultantResponse(**data)
        assert response.confidence_score >= 0.0
        assert response.status in ("CRITICAL", "WARNING", "INFO", "CLARIFY_NEEDED")

    @pytest.mark.parametrize("log_file", [
        "panic_log_01.txt",
        "suspend_hang_02.txt",
        "healthy_boot_03.txt",
    ])
    def test_fixture_log_builds_valid_case_file(self, log_file):
        case = _make_case(log_file, case_id="SCHEMA-TEST")
        assert case.log_payload.dmesg_content != ""
        assert case.case_id == "SCHEMA-TEST"
