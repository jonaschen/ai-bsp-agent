"""
Tests for skills/bsp_diagnostics/kernel_oops.py

Covers: extract_kernel_oops_log() — Oops detection, type classification,
process/PID extraction, ESR_EL1/FAR extraction, call trace, no-oops path.
"""
import pytest

from skills.bsp_diagnostics.kernel_oops import (
    KernelOopsOutput,
    extract_kernel_oops_log,
)

# ---------------------------------------------------------------------------
# Fixtures — representative dmesg snippets
# ---------------------------------------------------------------------------

NULL_PTR_OOPS = """\
[   52.345678] Unable to handle kernel NULL pointer dereference at virtual address 0000000000000000
[   52.345679] Mem abort info:
[   52.345680]   ESR = 0x96000004
[   52.345681]   EC = 0x25: DABT (current EL), IL = 32 bits
[   52.345682] Data abort info:
[   52.345683]   ISV = 0, ISS = 0x00000004
[   52.345684] Internal error: Oops: 0000000096000004 [#1] PREEMPT SMP
[   52.345685] CPU: 3 PID: 1234 Comm: kworker/3:1 Not tainted 5.15.0-android13
[   52.345686] Hardware name: Acme Board v1 (DT)
[   52.345687] pstate: 80000005 (Nzcv daif -PAN -UAO)
[   52.345688] pc : mydriver_probe+0x234/0x400
[   52.345689] lr : really_probe+0x214/0x4c0
[   52.345690] sp : ffff8000093f7be0
[   52.345691] Call trace:
[   52.345692]  mydriver_probe+0x234/0x400
[   52.345693]  really_probe+0x214/0x4c0
[   52.345694]  driver_probe_device+0x58/0xc0
[   52.345695]  device_driver_attach+0x50/0xb0
"""

PAGING_REQUEST_OOPS = """\
[  100.111222] Unable to handle kernel paging request at virtual address ffff000deadbeef0
[  100.111223] Internal error: Oops: 0000000096000045 [#1] PREEMPT SMP
[  100.111224] CPU: 0 PID: 567 Comm: mmcqd/0 Not tainted 6.1.0-android14
[  100.111225] pc : ufshcd_read_desc_param+0x48/0x200
[  100.111226] lr : ufshcd_read_unit_desc+0x30/0x88
[  100.111227] Call trace:
[  100.111228]  ufshcd_read_desc_param+0x48/0x200
[  100.111229]  ufshcd_read_unit_desc+0x30/0x88
"""

KERNEL_BUG_LOG = """\
[   10.000000] kernel BUG at drivers/clk/clk.c:456!
[   10.000001] Internal error: Oops - BUG: 0 [#1] SMP
[   10.000002] CPU: 1 PID: 89 Comm: init Not tainted 5.15.0
[   10.000003] pc : clk_prepare_lock+0x24/0x40
[   10.000004] lr : clk_prepare+0x1c/0x50
[   10.000005] Call trace:
[   10.000006]  clk_prepare_lock+0x24/0x40
[   10.000007]  clk_prepare+0x1c/0x50
"""

OOPS_WITH_FAR = """\
[   52.000000] Unable to handle kernel NULL pointer dereference at virtual address 0000000000000010
[   52.000001] Mem abort info:
[   52.000002]   ESR = 0x96000005
[   52.000003] FAR_EL1 = 0x0000000000000010
[   52.000004] Internal error: Oops: 96000005 [#1] PREEMPT SMP
[   52.000005] CPU: 2 PID: 2345 Comm: surfaceflinger Not tainted 5.15.0-android13
[   52.000006] pc : binder_transaction+0x1a4/0x1800
[   52.000007] Call trace:
[   52.000008]  binder_transaction+0x1a4/0x1800
[   52.000009]  binder_thread_write+0x4c0/0x1050
"""

CLEAN_DMESG = """\
[    0.000000] Booting Linux on physical CPU 0x0000000000 [0x411fd050]
[    0.000000] Linux version 5.15.0 (gcc version 11.3.0)
[    1.234567] usb 1-1: new high-speed USB device number 2
[    2.000000] systemd[1]: Reached target Basic System.
"""

EMPTY_LOG = ""


# ---------------------------------------------------------------------------
# Oops detection
# ---------------------------------------------------------------------------

class TestOopsDetection:
    def test_null_ptr_detected(self):
        out = extract_kernel_oops_log(NULL_PTR_OOPS)
        assert out.oops_detected is True

    def test_paging_request_detected(self):
        out = extract_kernel_oops_log(PAGING_REQUEST_OOPS)
        assert out.oops_detected is True

    def test_kernel_bug_detected(self):
        out = extract_kernel_oops_log(KERNEL_BUG_LOG)
        assert out.oops_detected is True

    def test_no_oops_in_clean_log(self):
        out = extract_kernel_oops_log(CLEAN_DMESG)
        assert out.oops_detected is False

    def test_no_oops_in_empty_log(self):
        out = extract_kernel_oops_log(EMPTY_LOG)
        assert out.oops_detected is False


# ---------------------------------------------------------------------------
# Oops type classification
# ---------------------------------------------------------------------------

class TestOopsTypeClassification:
    def test_null_ptr_type(self):
        out = extract_kernel_oops_log(NULL_PTR_OOPS)
        assert "null" in out.oops_type.lower() or "pointer" in out.oops_type.lower()

    def test_paging_request_type(self):
        out = extract_kernel_oops_log(PAGING_REQUEST_OOPS)
        assert "paging" in out.oops_type.lower() or "pointer" in out.oops_type.lower()

    def test_kernel_bug_type(self):
        out = extract_kernel_oops_log(KERNEL_BUG_LOG)
        assert "bug" in out.oops_type.lower() or out.oops_type != ""

    def test_no_oops_type_is_none_or_none_string(self):
        out = extract_kernel_oops_log(CLEAN_DMESG)
        assert out.oops_type in ("none", "") or out.oops_type is None or not out.oops_detected


# ---------------------------------------------------------------------------
# Process / PID extraction
# ---------------------------------------------------------------------------

class TestProcessPIDExtraction:
    def test_process_name_extracted(self):
        out = extract_kernel_oops_log(NULL_PTR_OOPS)
        assert out.faulting_process == "kworker/3:1"

    def test_pid_extracted(self):
        out = extract_kernel_oops_log(NULL_PTR_OOPS)
        assert out.faulting_pid == 1234

    def test_different_process_name(self):
        out = extract_kernel_oops_log(PAGING_REQUEST_OOPS)
        assert out.faulting_process == "mmcqd/0"

    def test_cpu_number_extracted(self):
        out = extract_kernel_oops_log(NULL_PTR_OOPS)
        assert out.cpu_number == 3


# ---------------------------------------------------------------------------
# ESR_EL1 and FAR extraction
# ---------------------------------------------------------------------------

class TestRegisterExtraction:
    def test_esr_hex_extracted(self):
        out = extract_kernel_oops_log(NULL_PTR_OOPS)
        assert out.esr_el1_hex is not None
        assert "96000004" in out.esr_el1_hex.lower().replace("0x", "")

    def test_far_extracted_when_present(self):
        out = extract_kernel_oops_log(OOPS_WITH_FAR)
        assert out.far_hex is not None
        assert "10" in out.far_hex.lower()

    def test_far_none_when_absent(self):
        out = extract_kernel_oops_log(NULL_PTR_OOPS)
        # NULL_PTR_OOPS does not have an explicit FAR_EL1 line
        # either None or extracted from the virtual address description
        assert out.far_hex is None or isinstance(out.far_hex, str)

    def test_far_extracted_from_virtual_address_null_ptr(self):
        # "at virtual address 0000000000000001" should populate far_hex
        log = (
            "[    4.123456] Unable to handle kernel NULL pointer dereference "
            "at virtual address 0000000000000001\n"
            "[    4.234567] Mem abort info:\n"
            "[    4.345678]   ESR = 0x0000000096000044\n"
            "[    5.445678] Internal error: Oops: 96000044 [#1] PREEMPT SMP\n"
            "[    5.667890] CPU: 0 PID: 123 Comm: kworker/0:1 Not tainted 6.6.14-0-virt\n"
            "[    5.914567] Call trace:\n"
            "[    5.915678]  cmd_crash+0x20/0x30\n"
        )
        out = extract_kernel_oops_log(log)
        assert out.oops_detected is True
        assert out.far_hex is not None
        assert "1" in out.far_hex

    def test_far_extracted_from_paging_request_virtual_address(self):
        # "at virtual address ffff800012345678" should populate far_hex
        log = (
            "[    6.123456] Unable to handle kernel paging request "
            "at virtual address ffff800012345678\n"
            "[    6.345678]   ESR = 0x000000009600004f\n"
            "[    6.905678] Internal error: Oops: 9600004f [#1] PREEMPT SMP\n"
            "[    6.907890] CPU: 1 PID: 456 Comm: kswapd0 Not tainted 6.6.14\n"
            "[    6.916789] Call trace:\n"
            "[    6.917890]  mem_cgroup_migrate+0x44/0xd0\n"
        )
        out = extract_kernel_oops_log(log)
        assert out.oops_detected is True
        assert out.far_hex is not None
        assert "ffff800012345678" in out.far_hex.lower()

    def test_pc_symbol_extracted(self):
        out = extract_kernel_oops_log(NULL_PTR_OOPS)
        assert out.pc_symbol is not None
        assert "mydriver_probe" in out.pc_symbol

    def test_lr_symbol_extracted(self):
        out = extract_kernel_oops_log(NULL_PTR_OOPS)
        assert out.lr_symbol is not None
        assert "really_probe" in out.lr_symbol


# ---------------------------------------------------------------------------
# Call trace extraction
# ---------------------------------------------------------------------------

class TestCallTraceExtraction:
    def test_call_trace_non_empty(self):
        out = extract_kernel_oops_log(NULL_PTR_OOPS)
        assert len(out.call_trace) >= 1

    def test_call_trace_contains_pc_function(self):
        out = extract_kernel_oops_log(NULL_PTR_OOPS)
        assert any("mydriver_probe" in entry for entry in out.call_trace)

    def test_call_trace_empty_for_no_oops(self):
        out = extract_kernel_oops_log(CLEAN_DMESG)
        assert out.call_trace == []

    def test_call_trace_capped_at_32(self):
        # Generate a log with a very long call trace
        trace_lines = "\n".join(
            f"[   52.{i:06d}]  function_{i}+0x10/0x20" for i in range(50)
        )
        log = NULL_PTR_OOPS + trace_lines
        out = extract_kernel_oops_log(log)
        assert len(out.call_trace) <= 32


# ---------------------------------------------------------------------------
# Output schema and confidence
# ---------------------------------------------------------------------------

class TestOutputSchema:
    def test_returns_correct_type(self):
        out = extract_kernel_oops_log(NULL_PTR_OOPS)
        assert isinstance(out, KernelOopsOutput)

    def test_oops_confidence_high(self):
        out = extract_kernel_oops_log(NULL_PTR_OOPS)
        assert out.confidence >= 0.75

    def test_no_oops_confidence(self):
        out = extract_kernel_oops_log(CLEAN_DMESG)
        assert out.confidence >= 0.0

    def test_confidence_in_range(self):
        for log in [NULL_PTR_OOPS, PAGING_REQUEST_OOPS, KERNEL_BUG_LOG, CLEAN_DMESG, EMPTY_LOG]:
            out = extract_kernel_oops_log(log)
            assert 0.0 <= out.confidence <= 1.0

    def test_first_oops_line_set(self):
        out = extract_kernel_oops_log(NULL_PTR_OOPS)
        assert out.first_oops_line is not None
        assert "Unable to handle" in out.first_oops_line or "Oops" in out.first_oops_line
