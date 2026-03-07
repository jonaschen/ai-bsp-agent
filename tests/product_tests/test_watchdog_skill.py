"""
Tests for skills/bsp_diagnostics/watchdog.py — analyze_watchdog_timeout.

All tests are deterministic: no LLM calls, no network, no I/O.
"""
import pytest

from skills.bsp_diagnostics.watchdog import (
    WatchdogInput,
    WatchdogOutput,
    analyze_watchdog_timeout,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

CLEAN_LOG = """\
[    0.100000] init: starting
[    1.000000] android: start services
[    2.000000] Boot completed
"""

SOFT_LOCKUP_LOG = """\
[  120.000000] watchdog: BUG: soft lockup - CPU#3 stuck for 23s! [kworker/u8:4:1234]
[  120.001000] Modules linked in: wifi_drv
[  120.002000] CPU: 3 PID: 1234 Comm: kworker/u8:4 Not tainted
[  120.003000] Call trace:
[  120.004000]  __schedule+0x3c4/0x8c0
[  120.005000]  schedule+0x7c/0xe0
[  120.006000]  schedule_timeout+0x128/0x180
[  120.007000]  wait_for_completion+0xb8/0x130
[  120.008000]  my_driver_suspend+0x48/0x90 [my_drv]
"""

HARD_LOCKUP_LOG = """\
[  200.000000] watchdog: BUG: hard lockup on CPU 2
[  200.001000] CPU: 2 PID: 5678 Comm: kworker/2:0 Not tainted
[  200.002000] Call trace:
[  200.003000]  _raw_spin_lock_irq+0x24/0x40
[  200.004000]  some_driver_irq_handler+0x6c/0x1a0 [some_drv]
"""

HARD_LOCKUP_NMI_LOG = """\
[  300.000000] NMI watchdog: BUG: hard LOCKUP on cpu 0
[  300.001000] CPU: 0 PID: 42 Comm: swapper/0 Not tainted
[  300.002000] Call trace:
[  300.003000]  smc_firmware_call+0x10/0x40
"""

RCU_STALL_LOG = """\
[  400.000000] INFO: rcu_sched detected stall
[  400.001000] rcu_sched self-detected stall on CPU 1
[  400.002000] CPU: 1 PID: 9999 Comm: rcu_sched Not tainted
[  400.003000] Call trace:
[  400.004000]  rcu_gp_kthread+0x234/0x400
"""

SOFT_LOCKUP_NO_CALL_TRACE_LOG = """\
[   50.000000] watchdog: BUG: soft lockup - CPU#1 stuck for 10s! [suspend_thread:500]
"""


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestSchemas:
    def test_input_schema(self):
        inp = WatchdogInput(dmesg_log="test")
        assert inp.dmesg_log == "test"

    def test_output_fields_present(self):
        out = analyze_watchdog_timeout(CLEAN_LOG)
        assert isinstance(out, WatchdogOutput)
        assert hasattr(out, "lockup_detected")
        assert hasattr(out, "lockup_type")
        assert hasattr(out, "cpu")
        assert hasattr(out, "pid")
        assert hasattr(out, "process_name")
        assert hasattr(out, "stuck_duration_s")
        assert hasattr(out, "call_trace")
        assert hasattr(out, "root_cause")
        assert hasattr(out, "recommended_action")
        assert hasattr(out, "confidence")

    def test_confidence_in_range(self):
        out = analyze_watchdog_timeout(SOFT_LOCKUP_LOG)
        assert 0.0 <= out.confidence <= 1.0

    def test_output_is_serialisable(self):
        out = analyze_watchdog_timeout(SOFT_LOCKUP_LOG)
        d = out.model_dump()
        assert isinstance(d["call_trace"], list)


# ---------------------------------------------------------------------------
# No-lockup path
# ---------------------------------------------------------------------------

class TestNoLockup:
    def test_not_detected_on_clean_log(self):
        out = analyze_watchdog_timeout(CLEAN_LOG)
        assert out.lockup_detected is False

    def test_type_is_none_on_clean_log(self):
        out = analyze_watchdog_timeout(CLEAN_LOG)
        assert out.lockup_type is None

    def test_call_trace_empty_on_clean_log(self):
        out = analyze_watchdog_timeout(CLEAN_LOG)
        assert out.call_trace == []

    def test_high_confidence_on_clean_log(self):
        out = analyze_watchdog_timeout(CLEAN_LOG)
        assert out.confidence >= 0.8

    def test_empty_log_returns_no_lockup(self):
        out = analyze_watchdog_timeout("")
        assert out.lockup_detected is False


# ---------------------------------------------------------------------------
# Soft lockup
# ---------------------------------------------------------------------------

class TestSoftLockup:
    def setup_method(self):
        self.out = analyze_watchdog_timeout(SOFT_LOCKUP_LOG)

    def test_lockup_detected(self):
        assert self.out.lockup_detected is True

    def test_lockup_type_is_soft(self):
        assert self.out.lockup_type == "soft_lockup"

    def test_cpu_extracted(self):
        assert self.out.cpu == 3

    def test_pid_extracted(self):
        assert self.out.pid == 1234

    def test_process_name_extracted(self):
        assert self.out.process_name == "kworker/u8:4"

    def test_stuck_duration_extracted(self):
        assert self.out.stuck_duration_s == pytest.approx(23.0)

    def test_call_trace_not_empty(self):
        assert len(self.out.call_trace) >= 1

    def test_call_trace_contains_schedule(self):
        assert any("schedule" in frame for frame in self.out.call_trace)

    def test_high_confidence_with_call_trace(self):
        assert self.out.confidence >= 0.85

    def test_root_cause_mentions_soft_lockup(self):
        assert "soft lockup" in self.out.root_cause.lower() or "lockup" in self.out.root_cause.lower()


# ---------------------------------------------------------------------------
# Hard lockup
# ---------------------------------------------------------------------------

class TestHardLockup:
    def setup_method(self):
        self.out = analyze_watchdog_timeout(HARD_LOCKUP_LOG)

    def test_lockup_detected(self):
        assert self.out.lockup_detected is True

    def test_lockup_type_is_hard(self):
        assert self.out.lockup_type == "hard_lockup"

    def test_cpu_extracted(self):
        assert self.out.cpu == 2

    def test_call_trace_not_empty(self):
        assert len(self.out.call_trace) >= 1

    def test_reasonable_confidence(self):
        assert self.out.confidence >= 0.5

    def test_root_cause_mentions_hard_lockup(self):
        assert "hard lockup" in self.out.root_cause.lower() or "nmi" in self.out.root_cause.lower()


# ---------------------------------------------------------------------------
# Hard lockup — NMI watchdog variant
# ---------------------------------------------------------------------------

class TestNMIHardLockup:
    def setup_method(self):
        self.out = analyze_watchdog_timeout(HARD_LOCKUP_NMI_LOG)

    def test_lockup_detected(self):
        assert self.out.lockup_detected is True

    def test_lockup_type_is_hard(self):
        assert self.out.lockup_type == "hard_lockup"

    def test_cpu_extracted(self):
        assert self.out.cpu == 0

    def test_call_trace_not_empty(self):
        assert len(self.out.call_trace) >= 1


# ---------------------------------------------------------------------------
# RCU stall (treated as soft lockup class)
# ---------------------------------------------------------------------------

class TestRCUStall:
    def setup_method(self):
        self.out = analyze_watchdog_timeout(RCU_STALL_LOG)

    def test_lockup_detected(self):
        assert self.out.lockup_detected is True

    def test_lockup_type_is_soft(self):
        assert self.out.lockup_type == "soft_lockup"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_no_call_trace_lower_confidence(self):
        out = analyze_watchdog_timeout(SOFT_LOCKUP_NO_CALL_TRACE_LOG)
        assert out.lockup_detected is True
        # No call trace → lower confidence than with trace
        assert out.confidence < 0.85

    def test_call_trace_capped_at_30(self):
        trace_lines = "\n".join(
            f"[  120.{i:06d}]  func_{i}+0x10/0x20" for i in range(50)
        )
        log = (
            "[  120.000000] watchdog: BUG: soft lockup - CPU#0 stuck for 22s! [kthread:100]\n"
            "[  120.000001] Call trace:\n"
            + trace_lines
        )
        out = analyze_watchdog_timeout(log)
        assert len(out.call_trace) <= 30

    def test_recommended_action_not_empty(self):
        out = analyze_watchdog_timeout(SOFT_LOCKUP_LOG)
        assert len(out.recommended_action) > 10

    def test_stuck_duration_none_for_hard_lockup(self):
        # Hard lockup messages don't include duration
        out = analyze_watchdog_timeout(HARD_LOCKUP_LOG)
        assert out.stuck_duration_s is None
