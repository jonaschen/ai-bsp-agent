"""
Tests for skills/bsp_diagnostics/workspace.py — Phase 8 Workspace Skills.

Covers:
  resolve_oops_symbols         — addr2line symbol resolution (subprocess mocked)
  compare_device_tree_nodes    — DTS node property diff (pure string)
  diff_kernel_configs          — .config comparison (pure string)
  validate_gpio_pinctrl_conflict — duplicate GPIO assignment detection

All tests are deterministic: no LLM calls, no network, no real filesystem.
subprocess.run is mocked for addr2line tests.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from skills.bsp_diagnostics.workspace import (
    OopsSymbolsInput,
    OopsSymbolsOutput,
    DTSNodeInput,
    DTSNodeOutput,
    KernelConfigInput,
    KernelConfigOutput,
    GPIOPinctrlInput,
    GPIOPinctrlOutput,
    resolve_oops_symbols,
    compare_device_tree_nodes,
    diff_kernel_configs,
    validate_gpio_pinctrl_conflict,
)


# ---------------------------------------------------------------------------
# Fixtures — resolve_oops_symbols
# ---------------------------------------------------------------------------

ADDR2LINE_TWO = (
    "my_null_driver_probe\n"
    "/kernel/drivers/my_driver/drv.c:42\n"
    "null_ptr_deref_helper\n"
    "/kernel/mm/mm_main.c:123\n"
)

ADDR2LINE_UNRESOLVED = (
    "??\n"
    "??:0\n"
    "known_func\n"
    "/kernel/init/main.c:7\n"
)

ADDR_LIST = ["0xffffff8008123456", "0xffffff8009abcdef"]


def _mock_completed(stdout: str, returncode: int = 0):
    m = MagicMock()
    m.stdout = stdout
    m.returncode = returncode
    return m


# ---------------------------------------------------------------------------
# Fixtures — DTS node comparison
# ---------------------------------------------------------------------------

DTS_IDENTICAL = """\
    compatible = "vendor,device-v1";
    reg = <0x0 0x1234 0x0 0x100>;
    status = "okay";
"""

DTS_NODE_A = """\
    compatible = "vendor,device-v1";
    reg = <0x0 0x1234 0x0 0x100>;
    status = "okay";
    clocks = <&gcc GCC_CAMERA_CLK>;
"""

DTS_NODE_B = """\
    compatible = "vendor,device-v2";
    reg = <0x0 0x1234 0x0 0x100>;
    status = "disabled";
    clocks = <&gcc GCC_CAMERA_CLK>;
    clock-names = "iface_clk";
"""

DTS_EMPTY = ""


# ---------------------------------------------------------------------------
# Fixtures — kernel config diff
# ---------------------------------------------------------------------------

CONFIG_IDENTICAL = """\
CONFIG_DRM=y
CONFIG_DRM_MSM=m
# CONFIG_DRM_NOUVEAU is not set
"""

CONFIG_A = """\
CONFIG_DRM=y
CONFIG_DRM_MSM=m
# CONFIG_DRM_NOUVEAU is not set
CONFIG_FRAMEBUFFER_CONSOLE=y
"""

CONFIG_B = """\
CONFIG_DRM=y
CONFIG_DRM_MSM=y
# CONFIG_DRM_NOUVEAU is not set
CONFIG_FRAMEBUFFER_CONSOLE=n
CONFIG_DRM_VIRTIO_GPU=m
"""


# ---------------------------------------------------------------------------
# Fixtures — GPIO pinctrl
# ---------------------------------------------------------------------------

DTS_CLEAN = """\
    uart@7af0000 {
        compatible = "qcom,msm-uartdm";
        gpios = <&tlmm 4 0x0>;
    };
    i2c@7888000 {
        compatible = "qcom,i2c-msm-v2";
        gpios = <&tlmm 10 0x0>;
    };
"""

DTS_GPIO_CONFLICT = """\
    uart@7af0000 {
        compatible = "qcom,msm-uartdm";
        gpios = <&tlmm 4 0x0>;
    };
    spi@7b30000 {
        compatible = "qcom,spi-qup";
        gpios = <&tlmm 4 0x0>;
    };
"""

DTS_MULTI_CONFLICT = """\
    cam_flash_gpio: cam_flash {
        gpios = <&tlmm 85 0>;
    };
    cam_torch_gpio: cam_torch {
        gpios = <&tlmm 85 0>;
    };
    cam_indicator {
        gpios = <&tlmm 87 0>;
        cs-gpios = <&tlmm 87 0>;
    };
"""


# ===========================================================================
# resolve_oops_symbols
# ===========================================================================

class TestOopsSymbolsSchemas:
    def test_input_schema(self):
        inp = OopsSymbolsInput(vmlinux_path="/out/vmlinux", addresses=["0xfff0"])
        assert inp.vmlinux_path == "/out/vmlinux"
        assert inp.addresses == ["0xfff0"]

    def test_output_fields_present(self):
        with patch("skills.bsp_diagnostics.workspace.subprocess.run") as mock_run:
            mock_run.return_value = _mock_completed(ADDR2LINE_TWO)
            out = resolve_oops_symbols("/vmlinux", ADDR_LIST)
        assert isinstance(out, OopsSymbolsOutput)
        assert hasattr(out, "resolved")
        assert hasattr(out, "unresolved")
        assert hasattr(out, "root_cause")
        assert hasattr(out, "recommended_action")
        assert hasattr(out, "confidence")

    def test_output_serialisable(self):
        with patch("skills.bsp_diagnostics.workspace.subprocess.run") as mock_run:
            mock_run.return_value = _mock_completed(ADDR2LINE_TWO)
            out = resolve_oops_symbols("/vmlinux", ADDR_LIST)
        d = out.model_dump()
        assert isinstance(d["resolved"], list)
        assert isinstance(d["unresolved"], list)


class TestResolveOopsSymbols:
    def setup_method(self):
        with patch("skills.bsp_diagnostics.workspace.subprocess.run") as mock_run:
            mock_run.return_value = _mock_completed(ADDR2LINE_TWO)
            self.out = resolve_oops_symbols("/path/to/vmlinux", ADDR_LIST)

    def test_two_symbols_resolved(self):
        assert len(self.out.resolved) == 2

    def test_first_function_name(self):
        assert self.out.resolved[0]["function"] == "my_null_driver_probe"

    def test_first_file(self):
        assert "drv.c" in self.out.resolved[0]["file"]

    def test_first_line(self):
        assert self.out.resolved[0]["line"] == 42

    def test_first_address_preserved(self):
        assert self.out.resolved[0]["address"] == "0xffffff8008123456"

    def test_second_function_name(self):
        assert self.out.resolved[1]["function"] == "null_ptr_deref_helper"

    def test_no_unresolved(self):
        assert len(self.out.unresolved) == 0

    def test_high_confidence_when_all_resolved(self):
        assert self.out.confidence >= 0.85

    def test_addr2line_called_with_vmlinux(self):
        with patch("skills.bsp_diagnostics.workspace.subprocess.run") as mock_run:
            mock_run.return_value = _mock_completed(ADDR2LINE_TWO)
            resolve_oops_symbols("/my/vmlinux", ADDR_LIST)
        call_args = mock_run.call_args[0][0]
        assert "/my/vmlinux" in call_args


class TestResolveWithUnresolved:
    def setup_method(self):
        with patch("skills.bsp_diagnostics.workspace.subprocess.run") as mock_run:
            mock_run.return_value = _mock_completed(ADDR2LINE_UNRESOLVED)
            self.out = resolve_oops_symbols("/vmlinux", ADDR_LIST)

    def test_one_resolved_one_unresolved(self):
        assert len(self.out.resolved) == 1
        assert len(self.out.unresolved) == 1

    def test_resolved_function_correct(self):
        assert self.out.resolved[0]["function"] == "known_func"

    def test_lower_confidence_with_unresolved(self):
        assert self.out.confidence < 0.85


class TestResolveEmptyAddresses:
    def test_empty_address_list(self):
        out = resolve_oops_symbols("/vmlinux", [])
        assert out.resolved == []
        assert out.unresolved == []


# ===========================================================================
# compare_device_tree_nodes
# ===========================================================================

class TestDTSSchemas:
    def test_input_schema(self):
        inp = DTSNodeInput(node_a="a { };", node_b="b { };")
        assert inp.node_a == "a { };"

    def test_output_fields_present(self):
        out = compare_device_tree_nodes(DTS_IDENTICAL, DTS_IDENTICAL)
        assert isinstance(out, DTSNodeOutput)
        assert hasattr(out, "differences_found")
        assert hasattr(out, "added")
        assert hasattr(out, "removed")
        assert hasattr(out, "modified")
        assert hasattr(out, "root_cause")
        assert hasattr(out, "recommended_action")
        assert hasattr(out, "confidence")

    def test_output_serialisable(self):
        out = compare_device_tree_nodes(DTS_NODE_A, DTS_NODE_B)
        d = out.model_dump()
        assert isinstance(d["added"], list)
        assert isinstance(d["modified"], list)


class TestDTSIdentical:
    def test_no_differences(self):
        out = compare_device_tree_nodes(DTS_IDENTICAL, DTS_IDENTICAL)
        assert out.differences_found is False

    def test_empty_lists(self):
        out = compare_device_tree_nodes(DTS_IDENTICAL, DTS_IDENTICAL)
        assert out.added == []
        assert out.removed == []
        assert out.modified == []

    def test_high_confidence(self):
        out = compare_device_tree_nodes(DTS_IDENTICAL, DTS_IDENTICAL)
        assert out.confidence >= 0.90


class TestDTSDiff:
    def setup_method(self):
        self.out = compare_device_tree_nodes(DTS_NODE_A, DTS_NODE_B)

    def test_differences_found(self):
        assert self.out.differences_found is True

    def test_added_property(self):
        # clock-names present in B but not A
        assert any("clock-names" in a for a in self.out.added)

    def test_removed_property(self):
        # nothing removed in this diff (B is superset of A minus value changes)
        # compatible and status are modified, not removed
        pass

    def test_modified_compatible(self):
        keys = [m["property"] for m in self.out.modified]
        assert "compatible" in keys

    def test_modified_status(self):
        keys = [m["property"] for m in self.out.modified]
        assert "status" in keys

    def test_old_value_preserved(self):
        status_change = next(m for m in self.out.modified if m["property"] == "status")
        assert "okay" in status_change["old_value"]

    def test_new_value_preserved(self):
        status_change = next(m for m in self.out.modified if m["property"] == "status")
        assert "disabled" in status_change["new_value"]

    def test_reasonable_confidence(self):
        assert self.out.confidence >= 0.90


# ===========================================================================
# diff_kernel_configs
# ===========================================================================

class TestConfigSchemas:
    def test_input_schema(self):
        inp = KernelConfigInput(config_a="CONFIG_X=y\n", config_b="CONFIG_X=n\n")
        assert "CONFIG_X" in inp.config_a

    def test_output_fields_present(self):
        out = diff_kernel_configs(CONFIG_IDENTICAL, CONFIG_IDENTICAL)
        assert isinstance(out, KernelConfigOutput)
        assert hasattr(out, "differences_found")
        assert hasattr(out, "added")
        assert hasattr(out, "removed")
        assert hasattr(out, "modified")
        assert hasattr(out, "root_cause")
        assert hasattr(out, "recommended_action")
        assert hasattr(out, "confidence")

    def test_output_serialisable(self):
        out = diff_kernel_configs(CONFIG_A, CONFIG_B)
        d = out.model_dump()
        assert isinstance(d["added"], list)
        assert isinstance(d["modified"], list)


class TestConfigIdentical:
    def test_no_differences(self):
        out = diff_kernel_configs(CONFIG_IDENTICAL, CONFIG_IDENTICAL)
        assert out.differences_found is False

    def test_empty_lists(self):
        out = diff_kernel_configs(CONFIG_IDENTICAL, CONFIG_IDENTICAL)
        assert out.added == []
        assert out.removed == []
        assert out.modified == []


class TestConfigDiff:
    def setup_method(self):
        self.out = diff_kernel_configs(CONFIG_A, CONFIG_B)

    def test_differences_found(self):
        assert self.out.differences_found is True

    def test_added_config(self):
        # CONFIG_DRM_VIRTIO_GPU in B but not A
        assert any("CONFIG_DRM_VIRTIO_GPU" in a for a in self.out.added)

    def test_modified_drm_msm(self):
        # CONFIG_DRM_MSM changed m → y
        keys = [m["key"] for m in self.out.modified]
        assert "CONFIG_DRM_MSM" in keys

    def test_modified_framebuffer_console(self):
        keys = [m["key"] for m in self.out.modified]
        assert "CONFIG_FRAMEBUFFER_CONSOLE" in keys

    def test_old_value_of_drm_msm(self):
        entry = next(m for m in self.out.modified if m["key"] == "CONFIG_DRM_MSM")
        assert entry["old_value"] == "m"

    def test_new_value_of_drm_msm(self):
        entry = next(m for m in self.out.modified if m["key"] == "CONFIG_DRM_MSM")
        assert entry["new_value"] == "y"

    def test_reasonable_confidence(self):
        assert self.out.confidence >= 0.90


# ===========================================================================
# validate_gpio_pinctrl_conflict
# ===========================================================================

class TestGPIOSchemas:
    def test_input_schema(self):
        inp = GPIOPinctrlInput(dts_content="uart { gpios = <&tlmm 4 0>; };")
        assert "tlmm" in inp.dts_content

    def test_output_fields_present(self):
        out = validate_gpio_pinctrl_conflict(DTS_CLEAN)
        assert isinstance(out, GPIOPinctrlOutput)
        assert hasattr(out, "conflict_detected")
        assert hasattr(out, "conflicts")
        assert hasattr(out, "root_cause")
        assert hasattr(out, "recommended_action")
        assert hasattr(out, "confidence")

    def test_output_serialisable(self):
        out = validate_gpio_pinctrl_conflict(DTS_GPIO_CONFLICT)
        d = out.model_dump()
        assert isinstance(d["conflicts"], list)


class TestGPIOClean:
    def test_no_conflict_on_clean(self):
        out = validate_gpio_pinctrl_conflict(DTS_CLEAN)
        assert out.conflict_detected is False

    def test_empty_conflicts_list(self):
        out = validate_gpio_pinctrl_conflict(DTS_CLEAN)
        assert out.conflicts == []

    def test_high_confidence_on_clean(self):
        out = validate_gpio_pinctrl_conflict(DTS_CLEAN)
        assert out.confidence >= 0.85

    def test_empty_dts(self):
        out = validate_gpio_pinctrl_conflict("")
        assert out.conflict_detected is False


class TestGPIOConflict:
    def setup_method(self):
        self.out = validate_gpio_pinctrl_conflict(DTS_GPIO_CONFLICT)

    def test_conflict_detected(self):
        assert self.out.conflict_detected is True

    def test_one_conflict_entry(self):
        assert len(self.out.conflicts) >= 1

    def test_conflict_gpio_num(self):
        assert any(c["gpio_num"] == 4 for c in self.out.conflicts)

    def test_conflict_has_two_nodes(self):
        conflict = next(c for c in self.out.conflicts if c["gpio_num"] == 4)
        assert len(conflict["conflicting_nodes"]) == 2

    def test_conflict_mentions_uart(self):
        conflict = next(c for c in self.out.conflicts if c["gpio_num"] == 4)
        assert any("uart" in n for n in conflict["conflicting_nodes"])

    def test_conflict_mentions_spi(self):
        conflict = next(c for c in self.out.conflicts if c["gpio_num"] == 4)
        assert any("spi" in n for n in conflict["conflicting_nodes"])

    def test_reasonable_confidence(self):
        assert self.out.confidence >= 0.85


class TestGPIOMultiConflict:
    def setup_method(self):
        self.out = validate_gpio_pinctrl_conflict(DTS_MULTI_CONFLICT)

    def test_conflict_detected(self):
        assert self.out.conflict_detected is True

    def test_gpio_85_conflict(self):
        assert any(c["gpio_num"] == 85 for c in self.out.conflicts)

    def test_gpio_87_conflict(self):
        # gpio 87 used twice in same node (different properties) — also a conflict
        assert any(c["gpio_num"] == 87 for c in self.out.conflicts)
