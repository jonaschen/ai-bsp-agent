"""
Skill Registry — Anthropic-compatible tool definitions and dispatcher.

All skills in `skills/bsp_diagnostics/` are registered here.
The Brain calls `TOOL_DEFINITIONS` when constructing the Anthropic messages API
request, and calls `dispatch_tool()` to execute a skill after Claude selects one.

`ROUTE_TOOLS` maps supervisor routes to the set of tool names relevant to each domain.
"""
from typing import Any

from skills.bsp_diagnostics.aarch64_exceptions import (
    AArch64ExceptionInput,
    CacheCoherencyInput,
    ESRELInput,
    check_cache_coherency_panic,
    decode_aarch64_exception,
    decode_esr_el1,
)
from skills.bsp_diagnostics.kernel_oops import (
    KernelOopsInput,
    extract_kernel_oops_log,
)
from skills.bsp_diagnostics.early_boot import (
    EarlyBootUARTInput,
    LKPanicInput,
    analyze_lk_panic,
    parse_early_boot_uart_log,
)
from skills.bsp_diagnostics.log_segmenter import (
    BootLogSegmenterInput,
    segment_boot_log,
)
from skills.bsp_diagnostics.pmic import (
    PMICVoltageInput,
    check_pmic_rail_voltage,
)
from skills.bsp_diagnostics.std_hibernation import (
    STDHibernationInput,
    analyze_std_hibernation_error,
)
from skills.bsp_diagnostics.vendor_boot import (
    VendorBootUFSInput,
    check_vendor_boot_ufs_driver,
)
from skills.bsp_diagnostics.watchdog import (
    WatchdogInput,
    analyze_watchdog_timeout,
)


def _pydantic_to_input_schema(model_cls) -> dict:
    """Convert a Pydantic model to an Anthropic tool input_schema dict."""
    schema = model_cls.model_json_schema()
    return {
        "type": "object",
        "properties": schema.get("properties", {}),
        "required": schema.get("required", []),
    }


TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "segment_boot_log",
        "description": (
            "Universal triage entry point (AGENTS.md §3.1). Identify the failing boot "
            "stage boundary from a raw log — pre-kernel UART output (TF-A/LK/U-Boot), "
            "kernel dmesg, or Android init/logcat. Returns the detected stage "
            "('early_boot', 'kernel_init', 'android_init', or 'unknown'), a recommended "
            "supervisor route, the first error line, and a confidence score. "
            "ALWAYS invoke this tool first before any domain-specific skill."
        ),
        "input_schema": _pydantic_to_input_schema(BootLogSegmenterInput),
    },
    {
        "name": "parse_early_boot_uart_log",
        "description": (
            "Detect and classify failures in TF-A / BootROM / BootROM UART output. "
            "Identifies the bootloader stage (BL1, BL2, BL31, U-Boot) where the failure "
            "occurred and classifies the error as: auth_failure (Secure Boot signature "
            "mismatch), image_load_failure (missing FIP/partition), ddr_init_failure "
            "(LPDDR training error), pmic_failure (rail not ready), or generic_error. "
            "Use when segment_boot_log returns detected_stage='early_boot'."
        ),
        "input_schema": _pydantic_to_input_schema(EarlyBootUARTInput),
    },
    {
        "name": "analyze_lk_panic",
        "description": (
            "Parse LK (Little Kernel) and U-Boot panic / assert messages. "
            "Extracts the assert source file and line number, the failing function, "
            "register dump (r0-r15 / x0-x30 / sp / elr), and classifies the panic as: "
            "assert, ddr_failure, image_load, pmic_failure, or generic. "
            "Use for Qualcomm LK or U-Boot stage failures identified by segment_boot_log."
        ),
        "input_schema": _pydantic_to_input_schema(LKPanicInput),
    },
    {
        "name": "analyze_std_hibernation_error",
        "description": (
            "Analyze Android STD (Suspend-to-Disk) hibernation image creation failures. "
            "Parses dmesg for 'Error -12 creating hibernation image' and evaluates "
            "SUnreclaim and SwapFree from /proc/meminfo to identify the root cause. "
            "Use when the user reports hibernation failures or power management issues "
            "during suspend/resume cycles on wearable or embedded Android devices."
        ),
        "input_schema": _pydantic_to_input_schema(STDHibernationInput),
    },
    {
        "name": "extract_kernel_oops_log",
        "description": (
            "Parse a kernel Oops or BUG report from a dmesg log. "
            "Detects 'Unable to handle kernel NULL pointer dereference', "
            "'Unable to handle kernel paging request', 'kernel BUG at', and "
            "'Internal error: Oops' messages. Extracts faulting process name, PID, "
            "CPU number, ESR_EL1 hex (pass to decode_esr_el1 or decode_aarch64_exception), "
            "FAR_EL1, pc/lr symbols, and call trace (up to 32 entries). "
            "Use as the first step whenever a kernel Oops is suspected."
        ),
        "input_schema": _pydantic_to_input_schema(KernelOopsInput),
    },
    {
        "name": "decode_aarch64_exception",
        "description": (
            "Decode an AArch64 ESR_EL1 + FAR_EL1 register pair together. "
            "Extends decode_esr_el1 with Fault Address Register interpretation: "
            "infers exception level (EL0 from lower EL / EL1 from current EL) from EC bits, "
            "classifies FAR as kernel-space (bit 63 set) or user-space, and provides a "
            "human-readable fault_address_summary. "
            "Use when the kernel Oops log contains both ESR_EL1 and FAR_EL1 values."
        ),
        "input_schema": _pydantic_to_input_schema(AArch64ExceptionInput),
    },
    {
        "name": "decode_esr_el1",
        "description": (
            "Decode an AArch64 ESR_EL1 (Exception Syndrome Register) hex value. "
            "Extracts Exception Class (EC), Instruction Length (IL), and Instruction "
            "Specific Syndrome (ISS) fields. Classifies the exception as a Data Abort, "
            "Instruction Abort, or SError Interrupt and provides fault status details. "
            "Use when a kernel panic log contains an ESR_EL1 register value."
        ),
        "input_schema": _pydantic_to_input_schema(ESRELInput),
    },
    {
        "name": "check_cache_coherency_panic",
        "description": (
            "Detect AArch64 cache coherency (Point of Coherency / PoC) failure indicators "
            "in a kernel panic or dmesg log. Scans for SError interrupts, ARM64-specific "
            "SError messages, cache maintenance traces, and ESR_EL1 values with EC=0x2F. "
            "Use when a kernel panic occurs shortly after CPU resume or system boot, "
            "especially on multi-core devices."
        ),
        "input_schema": _pydantic_to_input_schema(CacheCoherencyInput),
    },
    {
        "name": "check_vendor_boot_ufs_driver",
        "description": (
            "Detect UFS (Universal Flash Storage) driver load failures during the "
            "STD (Suspend-to-Disk) restore phase. Scans dmesg for ufshcd / ufs_qcom "
            "error messages and classifies the failure phase as probe, link_startup, "
            "or resume. Use when the device fails to complete STD restore and the "
            "symptom is a missing block device or an I/O error on the UFS storage."
        ),
        "input_schema": _pydantic_to_input_schema(VendorBootUFSInput),
    },
    {
        "name": "analyze_watchdog_timeout",
        "description": (
            "Parse soft lockup and hard lockup (NMI watchdog) events from a kernel "
            "dmesg log. Extracts CPU number, PID, process name, stuck duration, and "
            "call trace from the first lockup event found. Also detects RCU stall "
            "events. Use when dmesg contains 'BUG: soft lockup', 'BUG: hard lockup', "
            "or 'rcu_sched detected stall' messages."
        ),
        "input_schema": _pydantic_to_input_schema(WatchdogInput),
    },
    {
        "name": "check_pmic_rail_voltage",
        "description": (
            "Extract PMIC (Power Management IC) rail voltages from dmesg and logcat "
            "logs. Identifies rails with over-current protection (OCP) events or "
            "undervoltage conditions that may explain system instability, peripheral "
            "resets, or unexpected reboots. Supports Qualcomm rpm-smd-regulator, "
            "qpnp-regulator, and generic regulator framework log formats."
        ),
        "input_schema": _pydantic_to_input_schema(PMICVoltageInput),
    },
]

# Maps supervisor routing decisions to the set of tool names for that domain.
# The Brain uses this to offer only relevant tools to Claude per diagnostic session.
_UNIVERSAL_TOOLS: set[str] = {"segment_boot_log"}

ROUTE_TOOLS: dict[str, set[str]] = {
    "hardware_advisor": _UNIVERSAL_TOOLS | {
        "analyze_std_hibernation_error",
        "check_vendor_boot_ufs_driver",
        "check_pmic_rail_voltage",
    },
    "kernel_pathologist": _UNIVERSAL_TOOLS | {
        "extract_kernel_oops_log",
        "decode_esr_el1",
        "decode_aarch64_exception",
        "check_cache_coherency_panic",
        "analyze_watchdog_timeout",
    },
    "early_boot_advisor": _UNIVERSAL_TOOLS | {
        "parse_early_boot_uart_log",
        "analyze_lk_panic",
    },
}

_DISPATCH_TABLE: dict[str, Any] = {
    "extract_kernel_oops_log": lambda inp: extract_kernel_oops_log(
        dmesg_log=inp["dmesg_log"],
    ).model_dump(),
    "decode_aarch64_exception": lambda inp: decode_aarch64_exception(
        esr_val=inp["esr_val"],
        far_val=inp["far_val"],
    ).model_dump(),
    "segment_boot_log": lambda inp: segment_boot_log(
        raw_log=inp["raw_log"],
    ).model_dump(),
    "parse_early_boot_uart_log": lambda inp: parse_early_boot_uart_log(
        raw_uart_log=inp["raw_uart_log"],
    ).model_dump(),
    "analyze_lk_panic": lambda inp: analyze_lk_panic(
        uart_log_snippet=inp["uart_log_snippet"],
    ).model_dump(),
    "analyze_std_hibernation_error": lambda inp: analyze_std_hibernation_error(
        dmesg_log=inp["dmesg_log"],
        meminfo_log=inp["meminfo_log"],
    ).model_dump(),
    "decode_esr_el1": lambda inp: decode_esr_el1(
        hex_value=inp["hex_value"],
    ).model_dump(),
    "check_cache_coherency_panic": lambda inp: check_cache_coherency_panic(
        panic_log=inp["panic_log"],
    ).model_dump(),
    "check_vendor_boot_ufs_driver": lambda inp: check_vendor_boot_ufs_driver(
        dmesg_log=inp["dmesg_log"],
    ).model_dump(),
    "analyze_watchdog_timeout": lambda inp: analyze_watchdog_timeout(
        dmesg_log=inp["dmesg_log"],
    ).model_dump(),
    "check_pmic_rail_voltage": lambda inp: check_pmic_rail_voltage(
        dmesg_log=inp["dmesg_log"],
        logcat_log=inp.get("logcat_log", ""),
    ).model_dump(),
}


def dispatch_tool(tool_name: str, tool_input: dict) -> dict:
    """
    Execute a registered skill by name and return its serialised dict output.

    Args:
        tool_name: The name of the skill (must match a key in TOOL_DEFINITIONS).
        tool_input: Raw input dict from the Anthropic tool_use block.

    Returns:
        A plain dict (JSON-serialisable) with the skill's output.

    Raises:
        ValueError: If tool_name is not registered.
    """
    if tool_name not in _DISPATCH_TABLE:
        available = list(_DISPATCH_TABLE)
        raise ValueError(f"Unknown tool: {tool_name!r}. Available: {available}")
    return _DISPATCH_TABLE[tool_name](tool_input)
