"""
Isolated pytest for the Skill Registry.
No LLM is invoked.
"""
import pytest
from skills.registry import TOOL_DEFINITIONS, dispatch_tool

DMESG_WITH_ERROR = "Error -12 creating hibernation image\n"
MEMINFO_HIGH_SUNRECLAIM = (
    "MemTotal:        2097152 kB\n"
    "SUnreclaim:       307200 kB\n"
    "SwapFree:        1500000 kB\n"
)


class TestToolDefinitions:
    def test_at_least_one_tool_registered(self):
        assert len(TOOL_DEFINITIONS) >= 1

    def test_each_tool_has_required_keys(self):
        for tool in TOOL_DEFINITIONS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool

    def test_input_schema_is_object_type(self):
        for tool in TOOL_DEFINITIONS:
            assert tool["input_schema"]["type"] == "object"

    def test_input_schema_has_properties_and_required(self):
        for tool in TOOL_DEFINITIONS:
            schema = tool["input_schema"]
            assert "properties" in schema
            assert "required" in schema

    def test_std_hibernation_tool_registered(self):
        names = [t["name"] for t in TOOL_DEFINITIONS]
        assert "analyze_std_hibernation_error" in names

    def test_std_hibernation_schema_requires_dmesg_and_meminfo(self):
        tool = next(t for t in TOOL_DEFINITIONS if t["name"] == "analyze_std_hibernation_error")
        required = tool["input_schema"]["required"]
        assert "dmesg_log" in required
        assert "meminfo_log" in required


class TestDispatchTool:
    def test_dispatch_hibernation_tool_returns_dict(self):
        result = dispatch_tool(
            "analyze_std_hibernation_error",
            {"dmesg_log": DMESG_WITH_ERROR, "meminfo_log": MEMINFO_HIGH_SUNRECLAIM},
        )
        assert isinstance(result, dict)

    def test_dispatch_hibernation_tool_returns_correct_keys(self):
        result = dispatch_tool(
            "analyze_std_hibernation_error",
            {"dmesg_log": DMESG_WITH_ERROR, "meminfo_log": MEMINFO_HIGH_SUNRECLAIM},
        )
        assert "error_detected" in result
        assert "root_cause" in result
        assert "recommended_action" in result
        assert "confidence" in result

    def test_dispatch_detects_hibernation_error(self):
        result = dispatch_tool(
            "analyze_std_hibernation_error",
            {"dmesg_log": DMESG_WITH_ERROR, "meminfo_log": MEMINFO_HIGH_SUNRECLAIM},
        )
        assert result["error_detected"] is True
        assert result["sunreclaim_exceeds_threshold"] is True

    def test_dispatch_unknown_tool_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown tool"):
            dispatch_tool("nonexistent_skill", {})

    def test_dispatch_error_message_lists_available_tools(self):
        with pytest.raises(ValueError) as exc_info:
            dispatch_tool("nonexistent_skill", {})
        assert "analyze_std_hibernation_error" in str(exc_info.value)
