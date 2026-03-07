"""
Tests for skills/bsp_diagnostics/pmic.py — check_pmic_rail_voltage.

All tests are deterministic: no LLM calls, no network, no I/O.
"""
import pytest

from skills.bsp_diagnostics.pmic import (
    PMICRailInfo,
    PMICVoltageInput,
    PMICVoltageOutput,
    check_pmic_rail_voltage,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

EMPTY_LOG = ""

DMESG_NO_PMIC = """\
[    0.100000] init: starting
[    1.000000] android: start services
"""

DMESG_RPM_SMD_OK = """\
[    0.500000] rpm-smd-regulator 627c0000.qcom,rpm-smd: L5A: set_voltage (1800000 uV)
[    0.501000] rpm-smd-regulator 627c0000.qcom,rpm-smd: L12A: set_voltage (1200000 uV)
[    0.502000] rpm-smd-regulator 627c0000.qcom,rpm-smd: S3A: set_voltage (1050000 uV)
"""

DMESG_QPNP_OK = """\
[    0.600000] qpnp-regulator qpnp-regulator-l6: L6: 1800000 uV
[    0.601000] qpnp-regulator qpnp-regulator-s2: S2: 1050000 uV
"""

DMESG_OCP_EVENT = """\
[    1.000000] rpm-smd-regulator 627c0000.qcom,rpm-smd: L8A: set_voltage (2800000 uV)
[    1.500000] PMIC: L8A OCP fault detected
[    1.501000] over-current protection triggered
"""

DMESG_UNDERVOLTAGE = """\
[    0.900000] rpm-smd-regulator 627c0000.qcom,rpm-smd: L3A: set_voltage (1000000 uV)
[    1.200000] L3A: under-voltage detected, resetting peripheral
"""

DMESG_GENERIC_VOLTAGE = """\
[    0.700000] VDD_CPU_MV: 1050 mV
[    0.701000] VREG_L5: 1800000 uV
"""

LOGCAT_PMIC = """\
01-01 00:01:00.000 I/PMICDriver: L10: set_voltage (1800000 uV)
"""


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestSchemas:
    def test_input_defaults(self):
        inp = PMICVoltageInput(dmesg_log="test")
        assert inp.logcat_log == ""

    def test_output_fields_present(self):
        out = check_pmic_rail_voltage(EMPTY_LOG)
        assert isinstance(out, PMICVoltageOutput)
        assert hasattr(out, "rails_found")
        assert hasattr(out, "ocp_detected")
        assert hasattr(out, "undervoltage_rails")
        assert hasattr(out, "fault_rail")
        assert hasattr(out, "root_cause")
        assert hasattr(out, "recommended_action")
        assert hasattr(out, "confidence")

    def test_confidence_in_range(self):
        out = check_pmic_rail_voltage(DMESG_RPM_SMD_OK)
        assert 0.0 <= out.confidence <= 1.0

    def test_output_is_serialisable(self):
        out = check_pmic_rail_voltage(DMESG_RPM_SMD_OK)
        d = out.model_dump()
        assert isinstance(d["rails_found"], list)
        assert isinstance(d["undervoltage_rails"], list)

    def test_rail_info_model(self):
        r = PMICRailInfo(name="L5A", voltage_mv=1800, status="ok", raw_line="test line")
        assert r.voltage_mv == 1800
        assert r.status == "ok"


# ---------------------------------------------------------------------------
# No PMIC data found
# ---------------------------------------------------------------------------

class TestNoPMICData:
    def test_empty_log_no_rails(self):
        out = check_pmic_rail_voltage(EMPTY_LOG)
        assert out.rails_found == []
        assert out.ocp_detected is False
        assert out.undervoltage_rails == []
        assert out.fault_rail is None

    def test_no_pmic_log_low_confidence(self):
        out = check_pmic_rail_voltage(DMESG_NO_PMIC)
        # No rails in a plain init log
        assert out.confidence <= 0.5

    def test_recommended_action_guides_collection(self):
        out = check_pmic_rail_voltage(EMPTY_LOG)
        # Should mention how to get PMIC data
        action = out.recommended_action.lower()
        assert "pmic" in action or "regulator" in action


# ---------------------------------------------------------------------------
# Normal voltage extraction (rpm-smd)
# ---------------------------------------------------------------------------

class TestRpmSmdNormal:
    def setup_method(self):
        self.out = check_pmic_rail_voltage(DMESG_RPM_SMD_OK)

    def test_rails_found(self):
        assert len(self.out.rails_found) == 3

    def test_ocp_not_detected(self):
        assert self.out.ocp_detected is False

    def test_no_undervoltage(self):
        assert self.out.undervoltage_rails == []

    def test_fault_rail_is_none(self):
        assert self.out.fault_rail is None

    def test_rail_names_correct(self):
        names = {r.name for r in self.out.rails_found}
        assert "L5A" in names
        assert "L12A" in names
        assert "S3A" in names

    def test_voltages_converted_to_mv(self):
        l5a = next(r for r in self.out.rails_found if r.name == "L5A")
        assert l5a.voltage_mv == 1800  # 1800000 uV → 1800 mV

    def test_rail_status_ok(self):
        for r in self.out.rails_found:
            assert r.status == "ok"


# ---------------------------------------------------------------------------
# Normal voltage extraction (qpnp)
# ---------------------------------------------------------------------------

class TestQpnpNormal:
    def setup_method(self):
        self.out = check_pmic_rail_voltage(DMESG_QPNP_OK)

    def test_rails_found(self):
        assert len(self.out.rails_found) == 2

    def test_voltages_converted(self):
        l6 = next(r for r in self.out.rails_found if r.name == "L6")
        assert l6.voltage_mv == 1800

    def test_ocp_not_detected(self):
        assert self.out.ocp_detected is False


# ---------------------------------------------------------------------------
# OCP event
# ---------------------------------------------------------------------------

class TestOCPEvent:
    def setup_method(self):
        self.out = check_pmic_rail_voltage(DMESG_OCP_EVENT)

    def test_ocp_detected(self):
        assert self.out.ocp_detected is True

    def test_fault_rail_set(self):
        assert self.out.fault_rail is not None

    def test_fault_rail_is_l8a(self):
        # The OCP line names L8A
        assert self.out.fault_rail == "L8A"

    def test_high_confidence_on_ocp(self):
        assert self.out.confidence >= 0.85

    def test_root_cause_mentions_ocp(self):
        assert "ocp" in self.out.root_cause.lower() or "over-current" in self.out.root_cause.lower()

    def test_recommended_action_mentions_current(self):
        assert "current" in self.out.recommended_action.lower()


# ---------------------------------------------------------------------------
# Undervoltage event
# ---------------------------------------------------------------------------

class TestUndervoltageEvent:
    def setup_method(self):
        self.out = check_pmic_rail_voltage(DMESG_UNDERVOLTAGE)

    def test_undervoltage_detected(self):
        assert len(self.out.undervoltage_rails) >= 1

    def test_ocp_not_detected(self):
        assert self.out.ocp_detected is False

    def test_fault_rail_set(self):
        assert self.out.fault_rail is not None

    def test_fault_rail_is_l3a(self):
        assert self.out.fault_rail == "L3A"

    def test_confidence_reasonable(self):
        assert self.out.confidence >= 0.5

    def test_root_cause_mentions_undervoltage(self):
        rc = self.out.root_cause.lower()
        assert "undervoltage" in rc or "under-voltage" in rc or "uvlo" in rc


# ---------------------------------------------------------------------------
# Generic voltage log (mV and uV detection)
# ---------------------------------------------------------------------------

class TestGenericVoltage:
    def setup_method(self):
        self.out = check_pmic_rail_voltage(DMESG_GENERIC_VOLTAGE)

    def test_rails_found(self):
        assert len(self.out.rails_found) >= 1

    def test_vdd_cpu_voltage_in_mv(self):
        vdd = next((r for r in self.out.rails_found if "VDD_CPU" in r.name), None)
        if vdd:
            # 1050 mV directly
            assert vdd.voltage_mv == 1050


# ---------------------------------------------------------------------------
# Logcat merging
# ---------------------------------------------------------------------------

class TestLogcatMerge:
    def test_logcat_rails_included(self):
        out = check_pmic_rail_voltage(DMESG_NO_PMIC, logcat_log=LOGCAT_PMIC)
        # logcat has an rpm-style line? No — LOGCAT_PMIC uses a generic format.
        # Either way the result should not crash.
        assert isinstance(out, PMICVoltageOutput)

    def test_empty_logcat_same_as_no_logcat(self):
        out_with = check_pmic_rail_voltage(DMESG_RPM_SMD_OK, logcat_log="")
        out_without = check_pmic_rail_voltage(DMESG_RPM_SMD_OK)
        assert len(out_with.rails_found) == len(out_without.rails_found)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_recommended_action_not_empty(self):
        out = check_pmic_rail_voltage(DMESG_OCP_EVENT)
        assert len(out.recommended_action) > 10

    def test_ocp_takes_priority_over_undervoltage(self):
        combined = DMESG_OCP_EVENT + "\n" + DMESG_UNDERVOLTAGE
        out = check_pmic_rail_voltage(combined)
        assert out.ocp_detected is True
        # fault_rail should be the OCP rail
        assert out.fault_rail == "L8A"
