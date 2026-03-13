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
from skills.bsp_diagnostics.skill_improvement import (
    ValidateExtensionInput,
    SuggestPatternInput,
    validate_skill_extension,
    suggest_pattern_improvement,
)
from skills.bsp_diagnostics.android_init import (
    SELinuxDenialInput,
    AndroidInitRCInput,
    analyze_selinux_denial,
    check_android_init_rc,
)
from skills.bsp_diagnostics.subsystems import (
    ClockDepsInput,
    VFSMountInput,
    FirmwareLoadInput,
    EarlyOOMInput,
    check_clock_dependencies,
    diagnose_vfs_mount_failure,
    analyze_firmware_load_error,
    analyze_early_oom_killer,
)
from skills.bsp_diagnostics.workspace import (
    OopsSymbolsInput,
    DTSNodeInput,
    KernelConfigInput,
    GPIOPinctrlInput,
    resolve_oops_symbols,
    compare_device_tree_nodes,
    diff_kernel_configs,
    validate_gpio_pinctrl_conflict,
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
    {
        "name": "analyze_selinux_denial",
        "description": (
            "Detect and classify SELinux AVC denial events from dmesg or logcat output. "
            "Parses all 'avc: denied { permission }' lines and extracts: permission, "
            "process name (comm), source context (scontext), target context (tcontext), "
            "object class (tclass), and permissive flag. Deduplicates by unique "
            "(permission, scontext, tcontext, tclass) tuples. Reports enforcing vs. "
            "permissive-mode denials. Use when segment_boot_log returns 'android_init' "
            "stage or when AVC denial lines are present."
        ),
        "input_schema": _pydantic_to_input_schema(SELinuxDenialInput),
    },
    {
        "name": "check_android_init_rc",
        "description": (
            "Detect Android init.rc command failures and service crashes from dmesg. "
            "Parses 'init: Command ... took Xms and failed: reason' lines and "
            "'init: Service ... exited with status N' lines (non-zero only). "
            "Extracts the failed command, init.rc file path and line number, action "
            "trigger, and failure reason. Use when Android userspace fails to start "
            "or services crash during boot."
        ),
        "input_schema": _pydantic_to_input_schema(AndroidInitRCInput),
    },
    {
        "name": "check_clock_dependencies",
        "description": (
            "Detect kernel CCF (Common Clock Framework) probe-defer failures and "
            "clk_get errors from dmesg. Extracts the names of platform devices stuck "
            "in deferred probe (EPROBE_DEFER = -517) and the missing clock signals "
            "that caused the deferral. Use when a peripheral driver fails to probe "
            "at boot and 'deferred_probe_pending' or 'clk_get failed' appears in dmesg."
        ),
        "input_schema": _pydantic_to_input_schema(ClockDepsInput),
    },
    {
        "name": "diagnose_vfs_mount_failure",
        "description": (
            "Detect VFS root filesystem mount failures from dmesg. Parses "
            "'VFS: Cannot open root device' messages and extracts the block device "
            "name and errno. Also identifies filesystem-level errors (EXT4, FAT) "
            "that precede the VFS failure. Use when the device panics with "
            "'VFS: Unable to mount root fs' or the kernel cannot find the root partition."
        ),
        "input_schema": _pydantic_to_input_schema(VFSMountInput),
    },
    {
        "name": "analyze_firmware_load_error",
        "description": (
            "Detect firmware file load failures from dmesg. Parses "
            "'Direct firmware load for X failed' and 'request_firmware timed out' "
            "messages. Extracts the firmware file names and driver names that "
            "reported the failure. Use when a peripheral (WiFi, camera, modem) "
            "fails to initialise and dmesg shows firmware request errors."
        ),
        "input_schema": _pydantic_to_input_schema(FirmwareLoadInput),
    },
    {
        "name": "analyze_early_oom_killer",
        "description": (
            "Detect early OOM kill events from dmesg. Parses "
            "'Out of memory: Killed process N (name)' lines and extracts the "
            "victim process name, PID, oom_score_adj, and memory footprint. "
            "Use when a device crashes or becomes unstable early in boot and "
            "dmesg contains OOM killer messages."
        ),
        "input_schema": _pydantic_to_input_schema(EarlyOOMInput),
    },
    {
        "name": "resolve_oops_symbols",
        "description": (
            "Resolve hex call-trace addresses from a kernel oops to function name "
            "and source file:line using addr2line. Requires the vmlinux ELF file "
            "built with debug symbols (CONFIG_DEBUG_INFO=y) that matches the crashing "
            "kernel. Pass addresses from extract_kernel_oops_log call_trace output. "
            "Use in the source_analyst route when a vmlinux path is available."
        ),
        "input_schema": _pydantic_to_input_schema(OopsSymbolsInput),
    },
    {
        "name": "compare_device_tree_nodes",
        "description": (
            "Diff two DTS (Device Tree Source) node content strings and report "
            "added, removed, and modified properties. Pass the property block content "
            "of each node (not the full file). Use when a DTS regression is suspected "
            "— e.g., a driver that probed correctly before a DTS commit now fails."
        ),
        "input_schema": _pydantic_to_input_schema(DTSNodeInput),
    },
    {
        "name": "diff_kernel_configs",
        "description": (
            "Compare two kernel .config file contents and report CONFIG option "
            "differences: added (new in config_b), removed (dropped from config_b), "
            "and modified (value changed). Use when a kernel config change may have "
            "caused a regression — e.g., a driver or subsystem was disabled or "
            "changed from module to built-in."
        ),
        "input_schema": _pydantic_to_input_schema(KernelConfigInput),
    },
    {
        "name": "validate_gpio_pinctrl_conflict",
        "description": (
            "Detect duplicate GPIO pin assignments in a DTS file or fragment. "
            "Scans for 'gpios = <&controller pin ...>' patterns across all DTS nodes "
            "and reports any (controller, pin_number) pair assigned in more than one "
            "node or more than once within a single node. Use when GPIO or pinctrl "
            "conflicts are suspected as the cause of peripheral probe failures."
        ),
        "input_schema": _pydantic_to_input_schema(GPIOPinctrlInput),
    },
    {
        "name": "validate_skill_extension",
        "description": (
            "Dry-run a proposed regex pattern against a log snippet before committing it. "
            "Returns whether the pattern matches, how many lines match, and a preview of "
            "matched lines. Call this BEFORE suggest_pattern_improvement to confirm the "
            "pattern captures the intended lines."
        ),
        "input_schema": _pydantic_to_input_schema(ValidateExtensionInput),
    },
    {
        "name": "suggest_pattern_improvement",
        "description": (
            "Propose and persist a new detection pattern for an existing skill. "
            "Use this when a core skill returns failure_detected=False (or low confidence) "
            "on a real-hardware log that clearly contains a failure. "
            "Validates skill_name, category, regex syntax, and that the pattern matches "
            "the provided log_snippet before writing to ~/.bsp-diagnostics/skill_extensions.json. "
            "On the next run the skill will apply the new pattern automatically."
        ),
        "input_schema": _pydantic_to_input_schema(SuggestPatternInput),
    },
]

# Maps supervisor routing decisions to the set of tool names for that domain.
# The Brain uses this to offer only relevant tools to Claude per diagnostic session.
_UNIVERSAL_TOOLS: set[str] = {
    "segment_boot_log",
    "validate_skill_extension",
    "suggest_pattern_improvement",
}

ROUTE_TOOLS: dict[str, set[str]] = {
    "hardware_advisor": _UNIVERSAL_TOOLS | {
        "analyze_std_hibernation_error",
        "check_vendor_boot_ufs_driver",
        "check_pmic_rail_voltage",
        "analyze_early_oom_killer",
    },
    "kernel_pathologist": _UNIVERSAL_TOOLS | {
        "extract_kernel_oops_log",
        "decode_esr_el1",
        "decode_aarch64_exception",
        "check_cache_coherency_panic",
        "analyze_watchdog_timeout",
        "check_clock_dependencies",
        "diagnose_vfs_mount_failure",
        "analyze_firmware_load_error",
    },
    "early_boot_advisor": _UNIVERSAL_TOOLS | {
        "parse_early_boot_uart_log",
        "analyze_lk_panic",
    },
    "android_init_advisor": _UNIVERSAL_TOOLS | {
        "analyze_selinux_denial",
        "check_android_init_rc",
    },
    "source_analyst": _UNIVERSAL_TOOLS | {
        "resolve_oops_symbols",
        "compare_device_tree_nodes",
        "diff_kernel_configs",
        "validate_gpio_pinctrl_conflict",
        # cross-route synergy: oops symbols builds on kernel oops extraction
        "extract_kernel_oops_log",
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
    "check_clock_dependencies": lambda inp: check_clock_dependencies(
        dmesg_log=inp["dmesg_log"],
    ).model_dump(),
    "diagnose_vfs_mount_failure": lambda inp: diagnose_vfs_mount_failure(
        dmesg_log=inp["dmesg_log"],
    ).model_dump(),
    "analyze_firmware_load_error": lambda inp: analyze_firmware_load_error(
        dmesg_log=inp["dmesg_log"],
    ).model_dump(),
    "analyze_early_oom_killer": lambda inp: analyze_early_oom_killer(
        dmesg_log=inp["dmesg_log"],
    ).model_dump(),
    "analyze_selinux_denial": lambda inp: analyze_selinux_denial(
        logcat_log=inp["logcat_log"],
    ).model_dump(),
    "check_android_init_rc": lambda inp: check_android_init_rc(
        dmesg_log=inp["dmesg_log"],
    ).model_dump(),
    "resolve_oops_symbols": lambda inp: resolve_oops_symbols(
        vmlinux_path=inp["vmlinux_path"],
        addresses=inp["addresses"],
    ).model_dump(),
    "compare_device_tree_nodes": lambda inp: compare_device_tree_nodes(
        node_a=inp["node_a"],
        node_b=inp["node_b"],
        node_name=inp.get("node_name"),
    ).model_dump(),
    "diff_kernel_configs": lambda inp: diff_kernel_configs(
        config_a=inp["config_a"],
        config_b=inp["config_b"],
    ).model_dump(),
    "validate_gpio_pinctrl_conflict": lambda inp: validate_gpio_pinctrl_conflict(
        dts_content=inp["dts_content"],
    ).model_dump(),
    "validate_skill_extension": lambda inp: validate_skill_extension(
        ValidateExtensionInput(**inp)
    ).model_dump(),
    "suggest_pattern_improvement": lambda inp: suggest_pattern_improvement(
        SuggestPatternInput(**inp)
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
