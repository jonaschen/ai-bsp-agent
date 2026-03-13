"""
Isolated pytest for SupervisorAgent.
All Anthropic API calls are mocked — no LLM is invoked.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from product.bsp_agent.agents.supervisor import SupervisorAgent
from product.bsp_agent.core.state import AgentState

KERNEL_PANIC_LOG = """\
[  123.456789] Unable to handle kernel NULL pointer dereference at virtual address 0000000000000010
[  123.456790] Oops: 0000000000000000 [#1] PREEMPT SMP
[  123.456791] CPU: 3 PID: 1234 Comm: kworker/u8:2 Tainted: G   W
[  123.456792] pc : drm_atomic_helper_commit+0x1c/0x88 [drm_kms_helper]
"""

STD_FAILURE_LOG = """\
[  100.000000] PM: Syncing filesystems ... done.
[  100.123456] PM: Creating hibernation image:
[  100.234567] Error -12 creating hibernation image
[  100.345678] PM: Image saving failed, cleaning up.
"""

PLAIN_TEXT = "This is not a kernel log at all."


def _mock_client(token: str) -> MagicMock:
    block = SimpleNamespace(text=token)
    resp = MagicMock()
    resp.content = [block]
    client = MagicMock()
    client.messages.create.return_value = resp
    return client


class TestValidateInput:
    def test_accepts_log_with_kernel_timestamps(self):
        agent = SupervisorAgent(client=_mock_client("clarify_needed"))
        assert agent.validate_input(KERNEL_PANIC_LOG) is True

    def test_rejects_plain_text(self):
        agent = SupervisorAgent(client=_mock_client("clarify_needed"))
        assert agent.validate_input(PLAIN_TEXT) is False

    def test_rejects_empty_string(self):
        agent = SupervisorAgent(client=_mock_client("clarify_needed"))
        assert agent.validate_input("") is False


class TestChunkLog:
    def test_short_log_returned_unchanged(self):
        agent = SupervisorAgent(client=_mock_client("clarify_needed"))
        assert agent.chunk_log(KERNEL_PANIC_LOG) == KERNEL_PANIC_LOG

    def test_large_log_without_panic_falls_back_to_last_5000_lines(self):
        agent = SupervisorAgent(chunk_threshold_mb=0, client=_mock_client("clarify_needed"))
        big_log = "\n".join(f"[  {i:.6f}] some log line {i}" for i in range(6000))
        result = agent.chunk_log(big_log)
        assert len(result.splitlines()) == 5000

    def test_large_log_with_panic_returns_event_horizon(self):
        agent = SupervisorAgent(chunk_threshold_mb=0, client=_mock_client("clarify_needed"))
        lines = [f"[  {i:.6f}] noise" for i in range(100)]
        # Insert panic at t=50
        lines[50] = "[  50.000000] Kernel panic - not syncing: Oops - BUG: unable to handle page fault"
        big_log = "\n".join(lines)
        result = agent.chunk_log(big_log)
        assert "Kernel panic" in result
        # Lines outside ±10s of t=50 should not appear
        assert "[  0.000000]" not in result


class TestRoute:
    def test_routes_kernel_panic_to_pathologist(self):
        client = _mock_client("kernel_pathologist")
        agent = SupervisorAgent(client=client)
        state: AgentState = {"messages": [], "current_log_chunk": KERNEL_PANIC_LOG, "diagnosis_report": None}
        assert agent.route(state) == "kernel_pathologist"

    def test_routes_std_failure_to_hardware_advisor(self):
        client = _mock_client("hardware_advisor")
        agent = SupervisorAgent(client=client)
        state: AgentState = {"messages": [], "current_log_chunk": STD_FAILURE_LOG, "diagnosis_report": None}
        assert agent.route(state) == "hardware_advisor"

    def test_routes_plain_text_to_clarify_without_calling_llm(self):
        client = _mock_client("kernel_pathologist")
        agent = SupervisorAgent(client=client)
        state: AgentState = {"messages": [], "current_log_chunk": PLAIN_TEXT, "diagnosis_report": None}
        result = agent.route(state)
        assert result == "clarify_needed"
        # LLM must NOT be called for invalid input
        client.messages.create.assert_not_called()

    def test_unknown_llm_response_falls_back_to_clarify(self):
        client = _mock_client("i_dont_know")
        agent = SupervisorAgent(client=client)
        state: AgentState = {"messages": [], "current_log_chunk": KERNEL_PANIC_LOG, "diagnosis_report": None}
        assert agent.route(state) == "clarify_needed"

    def test_route_calls_llm_with_log_content(self):
        client = _mock_client("hardware_advisor")
        agent = SupervisorAgent(client=client)
        state: AgentState = {"messages": [], "current_log_chunk": STD_FAILURE_LOG, "diagnosis_report": None}
        agent.route(state)
        client.messages.create.assert_called_once()
        call_kwargs = client.messages.create.call_args.kwargs
        assert STD_FAILURE_LOG[:2000] in call_kwargs["messages"][0]["content"]

    def test_routes_selinux_avc_to_android_init_without_llm(self):
        avc_log = (
            "[  128.521504] type=1400 audit(1773227155.624:8): avc: denied { syslog_read } "
            "for comm=\"dmesg\" scontext=u:r:shell:s0 tcontext=u:r:kernel:s0 "
            "tclass=system permissive=0\n"
        )
        client = _mock_client("kernel_pathologist")  # LLM would say wrong thing
        agent = SupervisorAgent(client=client)
        state: AgentState = {"messages": [], "current_log_chunk": avc_log, "diagnosis_report": None}
        result = agent.route(state)
        assert result == "android_init_advisor"
        # Short-circuit: LLM must NOT be called
        client.messages.create.assert_not_called()

    def test_routes_init_command_failure_to_android_init_without_llm(self):
        init_fail_log = (
            "[   13.385514] init: Command 'start zygote_secondary' "
            "action=boot (/system/etc/init/hw/init.rc:1062) took 0ms and failed: "
            "service zygote_secondary not found\n"
        )
        client = _mock_client("kernel_pathologist")
        agent = SupervisorAgent(client=client)
        state: AgentState = {"messages": [], "current_log_chunk": init_fail_log, "diagnosis_report": None}
        result = agent.route(state)
        assert result == "android_init_advisor"
        client.messages.create.assert_not_called()

    def test_routes_android_init_advisor_token_from_llm(self):
        client = _mock_client("android_init_advisor")
        agent = SupervisorAgent(client=client)
        state: AgentState = {"messages": [], "current_log_chunk": KERNEL_PANIC_LOG, "diagnosis_report": None}
        assert agent.route(state) == "android_init_advisor"
