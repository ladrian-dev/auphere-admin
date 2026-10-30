"""Nexus MCP — in-process tool servers backing the catalog.

Bloque E agregó un espacio interno de tools accesible vía
``dispatch_internal``; hoy está vacío (spec 048 retiró su único inquilino, el
conector de agenda por navegador, junto con el transporte por subprocesos).
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
    reset_default_registry,
)

__all__ = [
    "InputModel",
    "InternalCallerTokenInvalid",
    "MCPRegistry",
    "OutputModel",
    "ToolBase",
    "ToolDef",
    "ToolError",
    "ToolNotInWhitelist",
    "ToolResult",
    "build_default_registry",
    "get_internal_caller_token",
    "reset_default_registry",
]
