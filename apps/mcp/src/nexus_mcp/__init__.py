"""Nexus MCP — in-process tool servers backing the catalog.

Bloque E agrega un transporte alterno (subprocess stdio) y un espacio
interno de tools (``agendapro.*``) accesible vía ``dispatch_internal``.
La firma pública ``MCPRegistry.dispatch(name, args, *, whitelist)`` no
cambia.
"""

from nexus_mcp.base import (
    InputModel,
    OutputModel,
    ToolBase,
    ToolDef,
    ToolError,
    ToolNotInWhitelist,
    ToolResult,
)
from nexus_mcp.registry import (
    InternalCallerTokenInvalid,
    MCPRegistry,
    build_default_registry,
    get_internal_caller_token,
)
from nexus_mcp.subprocess_tool import (
    SubprocessTransport,
    make_subprocess_tool_class,
)

__all__ = [
    "InputModel",
    "InternalCallerTokenInvalid",
    "MCPRegistry",
    "OutputModel",
    "SubprocessTransport",
    "ToolBase",
    "ToolDef",
    "ToolError",
    "ToolNotInWhitelist",
    "ToolResult",
    "build_default_registry",
    "get_internal_caller_token",
    "make_subprocess_tool_class",
]
