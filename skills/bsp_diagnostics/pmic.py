"""
PMIC Rail Voltage Diagnostic Skill.

Extracts Power Management IC (PMIC) rail voltage reports from dmesg and
logcat logs, identifies rails that are out of specification, and detects
over-current protection (OCP) events.

Domain: Android BSP / Hardware Advisor (Power Management)
Reference: Qualcomm PMIC drivers (qpnp-regulator, rpm-smd-regulator),
           MediaTek MT6360 regulator driver.
"""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PMICRailInfo(BaseModel):
    name: str = Field(..., description="Rail name (e.g. 'L5A', 'VDD_CPU_MV')")
    voltage_mv: Optional[int] = Field(None, description="Reported voltage in millivolts")
    status: str = Field(
        ...,
        description="One of: 'ok', 'ocp', 'undervoltage', 'disabled', 'unknown'",
    )
    raw_line: str = Field(..., description="Original log line containing this rail report")


class PMICVoltageInput(BaseModel):
    dmesg_log: str = Field(
        ...,
        description="Raw dmesg output from the device",
    )
    logcat_log: str = Field(
        "",
        description="Raw Android logcat output (optional; may contain PMIC vendor logs)",
    )


class PMICVoltageOutput(BaseModel):
    rails_found: list[PMICRailInfo] = Field(
        ..., description="List of PMIC rails identified in the logs"
    )
    ocp_detected: bool = Field(
        ..., description="True if any rail reported an over-current protection event"
    )
    undervoltage_rails: list[str] = Field(
        ..., description="Names of rails that reported undervoltage conditions"
    )
    fault_rail: Optional[str] = Field(
        None, description="Name of the rail most likely responsible for the failure"
    )
    root_cause: str = Field(..., description="Identified root cause or absence of failure")
    recommended_action: str = Field(..., description="Recommended remediation steps")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in the diagnosis")


# ---------------------------------------------------------------------------
# Detection patterns
# ---------------------------------------------------------------------------

# Qualcomm rpm-smd-regulator: "rpm-smd-regulator 627c0000.qcom,rpm-smd:qcom,rpm-smd-regulator-smd-5: L5: set_voltage (1800000 uV)"
_RPM_SMD_VOLTAGE_RE = re.compile(
    r"rpm[-_]smd[-_]regulator[^:]*:\s*([A-Z]\d+[A-Z]?|[A-Z]+\d+):\s*set_voltage\s*\((\d+)\s*uV\)",
    re.IGNORECASE,
)

# Qualcomm qpnp-regulator: "qpnp-regulator: L3: 1800000 uV"
_QPNP_VOLTAGE_RE = re.compile(
    r"qpnp[-_]regulator[^:]*:\s*([A-Z]\d+[A-Z]?|[A-Z]+\d+):\s*(\d+)\s*uV",
    re.IGNORECASE,
)

# Generic regulator framework: "regulator-dummy: Failed to get voltage"
# or "vdd-supply: 1800000 uV"
_GENERIC_VOLTAGE_RE = re.compile(
    r"(VDD_\w+|VREG_\w+|LDO\d+|BUCK\d+|[A-Z]\d+[A-Z]?)[\s:]+(\d+)\s*(?:mV|uV)",
    re.IGNORECASE,
)

# OCP (over-current protection) indicators
_OCP_RE = re.compile(
    r"over.?current|ocp\s*fault|ocp\s*detect|current\s*limit\s*reached|"
    r"short\s*circuit|oc_protection|PMIC.*OCP",
    re.IGNORECASE,
)

# Undervoltage indicators
_UNDERVOLTAGE_RE = re.compile(
    r"under.?voltage|uvlo\s*detect|low\s*voltage\s*detect|supply\s*is\s*(?:not\s*)?(?:ready|stable)|"
    r"voltage\s*not\s*ok|vreg\s*not\s*ready",
    re.IGNORECASE,
)

# Regulator disabled indicators
_DISABLED_RE = re.compile(
    r"(VDD_\w+|VREG_\w+|LDO\d+|BUCK\d+|[A-Z]\d+[A-Z]?)[^:]*:\s*"
    r"(?:disabled|turning off|power down)",
    re.IGNORECASE,
)

# Named rails in OCP lines, e.g. "L5A OCP fault"
_RAIL_IN_OCP_RE = re.compile(
    r"([A-Z]\d+[A-Z]?|VDD_\w+|VREG_\w+)\s*(?:OCP|over.?current)",
    re.IGNORECASE,
)

# Named rails in undervoltage lines — allow optional `:` separator, e.g.
# "L3A: under-voltage detected" or "L3A under-voltage".
_RAIL_IN_UVLO_RE = re.compile(
    r"([A-Z]\d+[A-Z]?|VDD_\w+|VREG_\w+)\s*:?\s*(?:under.?voltage|UVLO|low\s*voltage)",
    re.IGNORECASE,
)


def _uv_to_mv(uv: int) -> int:
    """Convert microvolts to millivolts."""
    return uv // 1000


def _parse_rails(log: str) -> list[PMICRailInfo]:
    """Extract rail info from a single log string."""
    found: dict[str, PMICRailInfo] = {}

    for line in log.splitlines():
        # rpm-smd pattern
        m = _RPM_SMD_VOLTAGE_RE.search(line)
        if m:
            name = m.group(1).upper()
            voltage_mv = _uv_to_mv(int(m.group(2)))
            found[name] = PMICRailInfo(
                name=name, voltage_mv=voltage_mv, status="ok", raw_line=line.strip()
            )
            continue

        # qpnp pattern
        m = _QPNP_VOLTAGE_RE.search(line)
        if m:
            name = m.group(1).upper()
            voltage_mv = _uv_to_mv(int(m.group(2)))
            found[name] = PMICRailInfo(
                name=name, voltage_mv=voltage_mv, status="ok", raw_line=line.strip()
            )
            continue

        # OCP event — extract rail name if present
        if _OCP_RE.search(line):
            rm = _RAIL_IN_OCP_RE.search(line)
            name = rm.group(1).upper() if rm else "UNKNOWN_OCP"
            existing = found.get(name)
            found[name] = PMICRailInfo(
                name=name,
                voltage_mv=existing.voltage_mv if existing else None,
                status="ocp",
                raw_line=line.strip(),
            )
            continue

        # Undervoltage event
        if _UNDERVOLTAGE_RE.search(line):
            rm = _RAIL_IN_UVLO_RE.search(line)
            name = rm.group(1).upper() if rm else "UNKNOWN_UVLO"
            existing = found.get(name)
            found[name] = PMICRailInfo(
                name=name,
                voltage_mv=existing.voltage_mv if existing else None,
                status="undervoltage",
                raw_line=line.strip(),
            )
            continue

        # Generic voltage match (only if not already found via OCP/UVLO)
        m = _GENERIC_VOLTAGE_RE.search(line)
        if m:
            name = m.group(1).upper()
            raw_val = int(m.group(2))
            # Heuristic: values > 10_000 are likely uV, else mV
            voltage_mv = _uv_to_mv(raw_val) if raw_val > 10_000 else raw_val
            if name not in found:
                found[name] = PMICRailInfo(
                    name=name, voltage_mv=voltage_mv, status="ok", raw_line=line.strip()
                )

    return list(found.values())


def check_pmic_rail_voltage(dmesg_log: str, logcat_log: str = "") -> PMICVoltageOutput:
    """
    Extract and evaluate PMIC rail voltages from dmesg and logcat logs.

    Identifies rails that are out of specification, detects OCP events,
    and flags undervoltage conditions that may explain system instability
    or sensor/peripheral failures.

    Args:
        dmesg_log: Raw dmesg content.
        logcat_log: Raw Android logcat content (optional).

    Returns:
        PMICVoltageOutput with detected rail statuses and recommended action.
    """
    rails = _parse_rails(dmesg_log)
    if logcat_log:
        logcat_rails = _parse_rails(logcat_log)
        # Merge: logcat overrides dmesg for the same rail name
        rail_map = {r.name: r for r in rails}
        for r in logcat_rails:
            rail_map[r.name] = r
        rails = list(rail_map.values())

    ocp_rails = [r for r in rails if r.status == "ocp"]
    uvlo_rails = [r for r in rails if r.status == "undervoltage"]
    ocp_detected = bool(ocp_rails)
    undervoltage_rail_names = [r.name for r in uvlo_rails]

    # Identify the fault rail (first OCP > first undervoltage > None)
    fault_rail: Optional[str] = None
    if ocp_rails:
        fault_rail = ocp_rails[0].name
    elif uvlo_rails:
        fault_rail = uvlo_rails[0].name

    if not rails:
        return PMICVoltageOutput(
            rails_found=[],
            ocp_detected=False,
            undervoltage_rails=[],
            fault_rail=None,
            root_cause="No PMIC rail voltage data found in the logs.",
            recommended_action=(
                "Enable PMIC debug logs: 'adb shell setprop log.tag.PMIC VERBOSE'. "
                "For Qualcomm platforms, check 'adb shell cat /sys/kernel/debug/regulator/*/state'. "
                "For MediaTek, check 'adb shell cat /proc/pmic/dump_pmic_reg'."
            ),
            confidence=0.2,
        )

    if ocp_detected:
        ocp_names = ", ".join(r.name for r in ocp_rails)
        root_cause = (
            f"Over-current protection (OCP) triggered on rail(s): {ocp_names}. "
            "OCP events indicate that the load on the rail exceeded the PMIC's "
            "current limit, typically caused by a short circuit, a peripheral "
            "drawing excessive current, or an incorrect load switch configuration."
        )
        recommended_action = (
            f"1. Measure actual current on {fault_rail} with a bench power supply in current-limit mode.\n"
            "2. Disconnect peripherals powered by the faulting rail one at a time to isolate the load.\n"
            "3. Check the PMIC OCP threshold register (e.g., via 'dump_pmic_reg') against the datasheet.\n"
            "4. Verify that inrush current limiting (soft-start) is enabled on the faulting regulator.\n"
            "5. Review vendor dev_pm_ops callbacks for missing regulator disable calls before suspend."
        )
        confidence = 0.88
    elif uvlo_rails:
        uvlo_names = ", ".join(undervoltage_rail_names)
        root_cause = (
            f"Undervoltage condition detected on rail(s): {uvlo_names}. "
            "The rail voltage dropped below the UVLO (Under-Voltage Lock-Out) threshold. "
            "This can cause peripheral resets, data corruption, or system instability."
        )
        recommended_action = (
            f"1. Measure the {fault_rail} rail voltage during the failure window.\n"
            "2. Check for IR drop: high-resistance connections, damaged PCB traces, or cold solder joints.\n"
            "3. Verify that PMIC output voltage setpoints are correctly programmed in the device tree.\n"
            "4. Check for battery aging or high ESR that reduces peak current delivery.\n"
            "5. Inspect regulator sequencing: confirm the rail is stable before its consumer is enabled."
        )
        confidence = 0.78
    else:
        rail_names = ", ".join(r.name for r in rails[:10])
        root_cause = (
            f"PMIC rail data found for {len(rails)} rail(s) ({rail_names}{', ...' if len(rails) > 10 else ''}). "
            "No OCP or undervoltage events detected. Rails appear to be within normal operating range."
        )
        recommended_action = (
            "Cross-reference reported voltages against the device hardware design guide. "
            "If instability persists, capture PMIC registers at the exact moment of failure "
            "using a crash notifier or a logic analyser on the PMIC I2C/SPI bus."
        )
        confidence = 0.60

    return PMICVoltageOutput(
        rails_found=rails,
        ocp_detected=ocp_detected,
        undervoltage_rails=undervoltage_rail_names,
        fault_rail=fault_rail,
        root_cause=root_cause,
        recommended_action=recommended_action,
        confidence=confidence,
    )
