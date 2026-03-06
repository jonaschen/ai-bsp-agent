"""
Skill Registry — Anthropic-compatible tool definitions and dispatcher.

All skills in `skills/bsp_diagnostics/` are registered here.
The Brain calls `TOOL_DEFINITIONS` when constructing the Anthropic messages API
request, and calls `dispatch_tool()` to execute a skill after Claude selects one.
"""
from typing import Any

from skills.bsp_diagnostics.std_hibernation import (
    STDHibernationInput,
    analyze_std_hibernation_error,
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
        "name": "analyze_std_hibernation_error",
        "description": (
            "Analyze Android STD (Suspend-to-Disk) hibernation image creation failures. "
            "Parses dmesg for 'Error -12 creating hibernation image' and evaluates "
            "SUnreclaim and SwapFree from /proc/meminfo to identify the root cause. "
            "Use this tool when the user reports hibernation failures or power management "
            "issues during suspend/resume cycles on wearable or embedded Android devices."
        ),
        "input_schema": _pydantic_to_input_schema(STDHibernationInput),
    },
]

_DISPATCH_TABLE: dict[str, Any] = {
    "analyze_std_hibernation_error": lambda inp: analyze_std_hibernation_error(
        dmesg_log=inp["dmesg_log"],
        meminfo_log=inp["meminfo_log"],
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
