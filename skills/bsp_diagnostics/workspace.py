"""
Workspace Diagnostic Skills — Phase 8.

Four skills that operate on workspace artifacts (vmlinux, DTS files, kernel
.config files) rather than raw log text. All file content is passed as strings
— no filesystem access inside the skill functions themselves.

  resolve_oops_symbols         — resolves hex call-trace addresses to function
                                  name + source file:line via addr2line.
  compare_device_tree_nodes    — diffs two DTS node content strings.
  diff_kernel_configs          — diffs two kernel .config content strings.
  validate_gpio_pinctrl_conflict — detects duplicate GPIO assignments in DTS.

Domain: Android BSP / Source Analyst
Reference: ARM addr2line, Device Tree Specification, Kconfig.
"""
from __future__ import annotations

import re
import subprocess
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class OopsSymbolsInput(BaseModel):
    vmlinux_path: str = Field(
        ...,
        description=(
            "Absolute path to the vmlinux ELF file built with debug info "
            "(-g, CONFIG_DEBUG_INFO=y). Must match the kernel that produced "
            "the oops call trace."
        ),
    )
    addresses: list[str] = Field(
        ...,
        description=(
            "List of hex addresses from the kernel oops call trace "
            "(e.g. ['0xffffff8008123456', '0xffffff8009abcdef']). "
            "Obtain these from extract_kernel_oops_log output."
        ),
    )


class OopsSymbolsOutput(BaseModel):
    resolved: list[dict] = Field(
        ...,
        description=(
            "List of resolved symbols. Each entry: "
            "address (str), function (str), file (str or None), line (int or None)."
        ),
    )
    unresolved: list[str] = Field(
        ..., description="Addresses addr2line could not resolve (returned '??')."
    )
    root_cause: str = Field(..., description="Summary of resolved symbols")
    recommended_action: str = Field(..., description="Next steps for the developer")
    confidence: float = Field(..., ge=0.0, le=1.0)


class DTSNodeInput(BaseModel):
    node_a: str = Field(
        ..., description="Content of the first DTS node (properties only, no outer braces required)."
    )
    node_b: str = Field(
        ..., description="Content of the second DTS node to compare against node_a."
    )
    node_name: Optional[str] = Field(
        None, description="Optional label for the node (used in root_cause output)."
    )


class DTSNodeOutput(BaseModel):
    differences_found: bool = Field(
        ..., description="True if the two DTS nodes have any property differences."
    )
    added: list[str] = Field(
        ..., description="Property names present in node_b but not node_a."
    )
    removed: list[str] = Field(
        ..., description="Property names present in node_a but not node_b."
    )
    modified: list[dict] = Field(
        ...,
        description=(
            "Properties present in both nodes with different values. "
            "Each entry: property (str), old_value (str), new_value (str)."
        ),
    )
    root_cause: str = Field(..., description="Summary of differences")
    recommended_action: str = Field(..., description="Next steps for the developer")
    confidence: float = Field(..., ge=0.0, le=1.0)


class KernelConfigInput(BaseModel):
    config_a: str = Field(
        ..., description="Content of the first kernel .config file."
    )
    config_b: str = Field(
        ..., description="Content of the second kernel .config file to compare against config_a."
    )


class KernelConfigOutput(BaseModel):
    differences_found: bool = Field(
        ..., description="True if the two .config files differ on any CONFIG option."
    )
    added: list[str] = Field(
        ..., description="CONFIG keys set in config_b but absent or 'not set' in config_a."
    )
    removed: list[str] = Field(
        ..., description="CONFIG keys set in config_a but absent or 'not set' in config_b."
    )
    modified: list[dict] = Field(
        ...,
        description=(
            "CONFIG keys present in both with different values. "
            "Each entry: key (str), old_value (str), new_value (str)."
        ),
    )
    root_cause: str = Field(..., description="Summary of configuration differences")
    recommended_action: str = Field(..., description="Next steps for the developer")
    confidence: float = Field(..., ge=0.0, le=1.0)


class GPIOPinctrlInput(BaseModel):
    dts_content: str = Field(
        ...,
        description=(
            "Full DTS (Device Tree Source) file or relevant fragment content "
            "as a string. Used to detect duplicate GPIO pin assignments across nodes."
        ),
    )


class GPIOPinctrlOutput(BaseModel):
    conflict_detected: bool = Field(
        ..., description="True if any GPIO pin number is assigned in more than one DTS node."
    )
    conflicts: list[dict] = Field(
        ...,
        description=(
            "List of conflicts. Each entry: gpio_num (int), pin_controller (str), "
            "conflicting_nodes (list[str])."
        ),
    )
    root_cause: str = Field(..., description="Summary of GPIO conflicts found")
    recommended_action: str = Field(..., description="Next steps for the developer")
    confidence: float = Field(..., ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# DTS single-line property: "    clock-names = "iface_clk";"  or  "    status = "okay";"
# Property names can contain hyphens and digits: clock-names, pinctrl-0
_DTS_PROP_RE = re.compile(
    r'^\s*([\w][\w,.-]*)\s*=\s*(.*?)\s*;?\s*$'
)

# Kernel config: "CONFIG_X=y" / "CONFIG_X=m" / "CONFIG_X=n" / "CONFIG_X=0x..."
_CONFIG_SET_RE = re.compile(r'^(CONFIG_\w+)=(.+)$')
# "# CONFIG_X is not set"
_CONFIG_UNSET_RE = re.compile(r'^#\s+(CONFIG_\w+)\s+is not set$')

# GPIO assignment in DTS: "gpios = <&tlmm 4 0x0>;" or "cs-gpios = <&tlmm 20 0>;"
_GPIO_ASSIGN_RE = re.compile(
    r'[\w-]*gpios?\s*=\s*<&(\w+)\s+(\d+)',
    re.IGNORECASE,
)

# DTS node opening: "uart@7af0000 {" or "cam_flash_gpio: cam_flash {"
_DTS_NODE_OPEN_RE = re.compile(
    r'^\s*(?:[\w.-]+:\s+)?([\w@.-]+)\s*\{',
)
_DTS_NODE_CLOSE_RE = re.compile(r'^\s*\};')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_dts_props(content: str) -> dict[str, str]:
    """Extract {property_name: value_string} from DTS node content lines."""
    props: dict[str, str] = {}
    for line in content.splitlines():
        m = _DTS_PROP_RE.match(line)
        if m:
            key = m.group(1)
            val = m.group(2).strip().rstrip(";").strip()
            # Skip lines that look like node openings ({) or closings (})
            if "{" in val or val == "}" or not key:
                continue
            props[key] = val
    return props


def _parse_config(content: str) -> dict[str, str]:
    """Extract {CONFIG_KEY: value} from a .config file. Unset → 'not set'."""
    cfg: dict[str, str] = {}
    for line in content.splitlines():
        m = _CONFIG_SET_RE.match(line.strip())
        if m:
            cfg[m.group(1)] = m.group(2)
            continue
        m = _CONFIG_UNSET_RE.match(line.strip())
        if m:
            cfg[m.group(1)] = "not set"
    return cfg


# ---------------------------------------------------------------------------
# Skill functions
# ---------------------------------------------------------------------------

def resolve_oops_symbols(vmlinux_path: str, addresses: list[str]) -> OopsSymbolsOutput:
    """
    Resolve hex call-trace addresses to function name + source file:line.

    Calls `addr2line -e <vmlinux_path> -f -C <addr...>` as a subprocess.
    addr2line outputs two lines per address: function name, then file:line.
    Addresses that cannot be resolved produce '??' / '??:0'.

    Args:
        vmlinux_path: Path to vmlinux ELF with debug symbols.
        addresses: List of hex address strings from the oops call trace.

    Returns:
        OopsSymbolsOutput with resolved and unresolved address lists.
    """
    if not addresses:
        return OopsSymbolsOutput(
            resolved=[],
            unresolved=[],
            root_cause="No addresses provided.",
            recommended_action="Pass the call_trace addresses from extract_kernel_oops_log.",
            confidence=1.0,
        )

    result = subprocess.run(
        ["addr2line", "-e", vmlinux_path, "-f", "-C"] + addresses,
        capture_output=True,
        text=True,
    )

    lines = result.stdout.splitlines()
    resolved: list[dict] = []
    unresolved: list[str] = []

    # addr2line outputs pairs: [function_name, file:line] per address
    for i, addr in enumerate(addresses):
        func_line = lines[i * 2] if i * 2 < len(lines) else "??"
        loc_line = lines[i * 2 + 1] if i * 2 + 1 < len(lines) else "??:0"

        if func_line == "??" or func_line.startswith("??"):
            unresolved.append(addr)
            continue

        file_part: Optional[str] = None
        line_num: Optional[int] = None
        if ":" in loc_line:
            file_part, _, ln = loc_line.rpartition(":")
            try:
                line_num = int(ln)
                if line_num == 0:
                    line_num = None
            except ValueError:
                pass

        resolved.append({
            "address": addr,
            "function": func_line,
            "file": file_part if file_part and file_part != "??" else None,
            "line": line_num,
        })

    total = len(addresses)
    n_resolved = len(resolved)
    confidence = 0.90 if n_resolved == total else max(0.50, 0.90 * n_resolved / total)

    if n_resolved == 0:
        root_cause = (
            f"addr2line could not resolve any of the {total} address(es). "
            "The vmlinux may not have debug symbols, or addresses do not match "
            "this kernel build."
        )
        recommended_action = (
            "1. Verify vmlinux was built with CONFIG_DEBUG_INFO=y.\n"
            "2. Ensure vmlinux matches the kernel that produced the oops "
            "(same build — not just same version).\n"
            "3. Check that addr2line is installed: `which addr2line`."
        )
    else:
        funcs = ", ".join(s["function"] for s in resolved[:3])
        root_cause = (
            f"Resolved {n_resolved}/{total} address(es). "
            f"Top frame(s): {funcs}."
            + (f" {len(unresolved)} address(es) unresolved." if unresolved else "")
        )
        recommended_action = (
            "1. Examine the resolved function names alongside the call trace "
            "from extract_kernel_oops_log.\n"
            "2. Open the source file at the reported line number to inspect "
            "the failing code path.\n"
            "3. For unresolved addresses, check if they are in a kernel module "
            "(.ko) rather than vmlinux — pass the .ko path instead."
        )

    return OopsSymbolsOutput(
        resolved=resolved,
        unresolved=unresolved,
        root_cause=root_cause,
        recommended_action=recommended_action,
        confidence=confidence,
    )


def compare_device_tree_nodes(
    node_a: str,
    node_b: str,
    node_name: Optional[str] = None,
) -> DTSNodeOutput:
    """
    Diff two DTS node content strings and report property changes.

    Parses single-line `key = value;` properties from each node, then
    reports added, removed, and modified properties.

    Args:
        node_a: First DTS node content (baseline).
        node_b: Second DTS node content (modified).
        node_name: Optional label used in the root_cause string.

    Returns:
        DTSNodeOutput with added, removed, and modified property lists.
    """
    props_a = _parse_dts_props(node_a)
    props_b = _parse_dts_props(node_b)

    keys_a = set(props_a)
    keys_b = set(props_b)

    added = sorted(keys_b - keys_a)
    removed = sorted(keys_a - keys_b)
    modified: list[dict] = []

    for key in sorted(keys_a & keys_b):
        if props_a[key] != props_b[key]:
            modified.append({
                "property": key,
                "old_value": props_a[key],
                "new_value": props_b[key],
            })

    label = f"'{node_name}'" if node_name else "the node"
    differences_found = bool(added or removed or modified)

    if not differences_found:
        return DTSNodeOutput(
            differences_found=False,
            added=[],
            removed=[],
            modified=[],
            root_cause=f"No property differences found in {label}.",
            recommended_action="Nodes are identical — no DTS change required.",
            confidence=0.95,
        )

    parts: list[str] = []
    if modified:
        mods = ", ".join(f"'{m['property']}'" for m in modified[:3])
        parts.append(f"{len(modified)} modified property/ies ({mods})")
    if added:
        parts.append(f"{len(added)} added ({', '.join(added[:3])})")
    if removed:
        parts.append(f"{len(removed)} removed ({', '.join(removed[:3])})")

    root_cause = (
        f"DTS node {label} changed: " + "; ".join(parts) + ". "
        "Review property value changes carefully — incorrect DTS properties "
        "can cause probe failures, wrong hardware configuration, or boot issues."
    )
    recommended_action = (
        "1. For modified 'compatible': verify the driver supports the new string.\n"
        "2. For modified 'reg'/'ranges': ensure addresses match the SoC TRM.\n"
        "3. For modified 'status': 'disabled' prevents the driver from probing.\n"
        "4. For added/removed clock-names or pinctrl entries: update the driver "
        "or verify the DTS matches the driver's expected resource names.\n"
        "5. Build and boot-test on real hardware after any DTS change."
    )
    return DTSNodeOutput(
        differences_found=True,
        added=added,
        removed=removed,
        modified=modified,
        root_cause=root_cause,
        recommended_action=recommended_action,
        confidence=0.95,
    )


def diff_kernel_configs(config_a: str, config_b: str) -> KernelConfigOutput:
    """
    Compare two kernel .config file contents and report option changes.

    Parses CONFIG_X=value lines and '# CONFIG_X is not set' lines.
    Reports options added to config_b, removed from config_b, and
    options whose values changed between the two configs.

    Args:
        config_a: Content of the baseline .config.
        config_b: Content of the modified .config.

    Returns:
        KernelConfigOutput with added, removed, and modified option lists.
    """
    cfg_a = _parse_config(config_a)
    cfg_b = _parse_config(config_b)

    keys_a = {k for k, v in cfg_a.items() if v != "not set"}
    keys_b = {k for k, v in cfg_b.items() if v != "not set"}

    added = sorted(keys_b - keys_a)
    removed = sorted(keys_a - keys_b)
    modified: list[dict] = []

    for key in sorted(keys_a & keys_b):
        if cfg_a[key] != cfg_b[key]:
            modified.append({
                "key": key,
                "old_value": cfg_a[key],
                "new_value": cfg_b[key],
            })

    differences_found = bool(added or removed or modified)

    if not differences_found:
        return KernelConfigOutput(
            differences_found=False,
            added=[],
            removed=[],
            modified=[],
            root_cause="No CONFIG option differences found.",
            recommended_action="Configs are identical — no kernel rebuild required.",
            confidence=0.95,
        )

    parts: list[str] = []
    if modified:
        mods = ", ".join(m["key"] for m in modified[:3])
        parts.append(f"{len(modified)} modified ({mods})")
    if added:
        parts.append(f"{len(added)} added ({', '.join(added[:3])})")
    if removed:
        parts.append(f"{len(removed)} removed ({', '.join(removed[:3])})")

    root_cause = (
        "Kernel config differences detected: " + "; ".join(parts) + ". "
        "Config changes can alter driver behaviour, enable/disable subsystems, "
        "or affect kernel size and boot time."
    )
    recommended_action = (
        "1. For m→y changes: the option is now built-in (not a module) — "
        "verify no initrd dependency was broken.\n"
        "2. For y→n or y→not set: the feature is removed — check if any "
        "userspace component depends on it.\n"
        "3. For newly added options: review Kconfig help text for security "
        "or stability implications.\n"
        "4. Run 'make oldconfig' to propagate changes and resolve dependencies.\n"
        "5. Rebuild and boot-test; check dmesg for new module load errors."
    )
    return KernelConfigOutput(
        differences_found=True,
        added=added,
        removed=removed,
        modified=modified,
        root_cause=root_cause,
        recommended_action=recommended_action,
        confidence=0.95,
    )


def validate_gpio_pinctrl_conflict(dts_content: str) -> GPIOPinctrlOutput:
    """
    Detect duplicate GPIO pin assignments across DTS nodes.

    Scans for `*gpios = <&controller pin ...>` patterns, tracks which
    (controller, pin_number) pairs appear in which DTS nodes, and
    reports any pin used in more than one node.

    Args:
        dts_content: Full DTS file content as a string.

    Returns:
        GPIOPinctrlOutput with a list of conflicting GPIO assignments.
    """
    # Map (controller, pin_num) → list of node names
    pin_nodes: dict[tuple[str, int], list[str]] = {}
    current_node: Optional[str] = None

    for line in dts_content.splitlines():
        # Detect node opening — capture node name
        node_m = _DTS_NODE_OPEN_RE.match(line)
        if node_m:
            current_node = node_m.group(1)
            continue

        # Detect node closing
        if _DTS_NODE_CLOSE_RE.match(line):
            current_node = None
            continue

        # Detect GPIO assignment
        gpio_m = _GPIO_ASSIGN_RE.search(line)
        if gpio_m:
            controller = gpio_m.group(1)
            pin_num = int(gpio_m.group(2))
            key = (controller, pin_num)
            node_label = current_node or "<unknown>"
            if key not in pin_nodes:
                pin_nodes[key] = []
            pin_nodes[key].append(node_label)

    conflicts = []
    for (controller, pin_num), nodes in pin_nodes.items():
        if len(nodes) > 1:
            conflicts.append({
                "gpio_num": pin_num,
                "pin_controller": controller,
                "conflicting_nodes": nodes,
            })

    if not conflicts:
        return GPIOPinctrlOutput(
            conflict_detected=False,
            conflicts=[],
            root_cause="No GPIO pin assignment conflicts detected.",
            recommended_action="No action required.",
            confidence=0.90,
        )

    entries = [
        f"GPIO {c['gpio_num']} ({c['pin_controller']}) in {c['conflicting_nodes']}"
        for c in conflicts[:3]
    ]
    root_cause = (
        f"GPIO pin conflict(s) detected: {len(conflicts)} pin(s) assigned in "
        f"multiple DTS nodes. Conflicting assignments: {'; '.join(entries)}. "
        "Duplicate GPIO assignments cause hardware conflicts at runtime — only "
        "one driver can own a GPIO at a time."
    )
    recommended_action = (
        "1. Identify which node/driver should own each conflicted GPIO.\n"
        "2. Remove the duplicate assignment from the non-owning node.\n"
        "3. If sharing is intended, use a GPIO hog or a regulator/mux node "
        "instead of two direct assignments.\n"
        "4. Rebuild and verify with 'cat /sys/kernel/debug/gpio' at runtime "
        "to confirm no pin is claimed twice."
    )
    return GPIOPinctrlOutput(
        conflict_detected=True,
        conflicts=conflicts,
        root_cause=root_cause,
        recommended_action=recommended_action,
        confidence=0.90,
    )
