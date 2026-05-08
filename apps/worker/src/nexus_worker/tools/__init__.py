"""Worker-side tool surface.

Block D replaces the in-process stubs with the ``nexus_mcp`` registry.
The names re-exported here are the public surface the pipeline imports.
"""

from nexus_worker.tools.registry import (
    MCPRegistry,
    ToolError,
    ToolNotInWhitelist,
    ToolResult,
    dispatch,
    get_registry,
    list_tool_names,
)

__all__ = [
    "MCPRegistry",
    "ToolError",
    "ToolNotInWhitelist",
    "ToolResult",
    "dispatch",
    "get_registry",
    "list_tool_names",
]
