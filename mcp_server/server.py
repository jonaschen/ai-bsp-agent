#!/usr/bin/env python3
"""
BSP Diagnostics MCP Server
===========================
Exposes all 11 Android BSP diagnostic skills as MCP tools so they can be
used directly inside Claude CLI (`claude`) or Claude Code (VS Code extension).

Run modes
---------
  python -m mcp_server.server          # stdio (default, used by Claude Code)
  bsp-diagnostics-mcp                  # same, via installed entry-point

Registration (one-time setup)
------------------------------
  # After `pip install -e .` from the project root:
  claude mcp add bsp-diagnostics bsp-diagnostics-mcp

  # Without installing (run from project root):
  claude mcp add bsp-diagnostics -- python -m mcp_server.server

  # VS Code: add to ~/.claude/settings.json under "mcpServers":
  #   "bsp-diagnostics": { "command": "bsp-diagnostics-mcp" }
"""
import asyncio
import json
import sys
from pathlib import Path

# Ensure project root is on sys.path when run as a script or with -m.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from skills.registry import TOOL_DEFINITIONS, dispatch_tool

# ---------------------------------------------------------------------------
# Server instance
# ---------------------------------------------------------------------------
server = Server("bsp-diagnostics")


# ---------------------------------------------------------------------------
# Tool list
# ---------------------------------------------------------------------------
@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """Return all registered BSP diagnostic skills as MCP Tool objects."""
    return [
        Tool(
            name=td["name"],
            description=td["description"],
            inputSchema=td["input_schema"],
        )
        for td in TOOL_DEFINITIONS
    ]


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------
@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Execute a BSP diagnostic skill and return its JSON result."""
    try:
        result: dict = dispatch_tool(name, arguments)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    except ValueError as exc:
        # Unknown tool name — surface as a clean error message.
        return [TextContent(type="text", text=f"Error: {exc}")]
    except Exception as exc:
        return [TextContent(type="text", text=f"Tool '{name}' failed: {exc}")]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main_sync() -> None:
    """Synchronous wrapper used by the console-script entry point."""
    asyncio.run(main())


if __name__ == "__main__":
    main_sync()
