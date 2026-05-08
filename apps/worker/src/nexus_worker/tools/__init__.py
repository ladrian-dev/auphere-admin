"""In-process deterministic stubs for the 21 tools in the barbershop catalog.

Block D replaces these stubs with real MCP servers (booking against AgendaPro,
queue against Redis, etc.). The signatures stay the same so the pipeline does
not change when the real servers come online.
"""

from nexus_worker.tools.registry import (
    ToolError,
    ToolHandler,
    ToolNotInWhitelist,
    ToolResult,
    get_handler,
    list_tool_names,
)

__all__ = [
    "ToolError",
    "ToolHandler",
    "ToolNotInWhitelist",
    "ToolResult",
    "get_handler",
    "list_tool_names",
]
