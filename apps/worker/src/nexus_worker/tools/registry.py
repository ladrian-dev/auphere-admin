"""Worker-side facade over the in-process ``nexus_mcp.MCPRegistry``.

Block C had per-tool stub callables here. Block D replaces the stubs with
real implementations living in ``nexus_mcp.servers.*`` and the dispatch
goes through ``MCPRegistry.dispatch`` which:

- Validates the name against the active tenant's whitelist.
- Validates the arguments against the tool's Pydantic input model.
- Runs the tool inside the active tenant's contextvar.
- Records ``tool.invoked`` / ``tool.error`` / ``tool.latency_ms`` counters.

The functions exposed here keep the same names and shapes the pipeline
imports — ``ToolError``, ``ToolNotInWhitelist``, ``get_handler``,
``list_tool_names`` — so call sites that haven't migrated to function
calling don't break. The tool_loop node uses ``get_registry`` directly.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from nexus_mcp import MCPRegistry, build_default_registry
from nexus_mcp.base import ToolError, ToolNotInWhitelist, ToolResult

__all__ = [
    "MCPRegistry",
    "ToolError",
    "ToolNotInWhitelist",
    "ToolResult",
    "get_registry",
    "list_tool_names",
    "reset_registry",
]


def get_registry() -> MCPRegistry:
    return build_default_registry()


def reset_registry() -> None:
    """Test helper — drop the cached default registry so the next call
    rebuilds. Useful when a test needs a registry with a different tool
    set; production code never calls this."""
    from nexus_mcp.registry import reset_default_registry

    reset_default_registry()


def list_tool_names() -> tuple[str, ...]:
    names: tuple[str, ...] = get_registry().names()
    return names


async def dispatch(
    name: str,
    args: dict[str, Any],
    *,
    whitelist: Iterable[str],
) -> ToolResult:
    """Convenience wrapper for callers that want the registry's dispatch
    semantics without building one. Re-exported here so the worker has a
    single import surface for the tools layer."""
    return await get_registry().dispatch(name, args, whitelist=whitelist)
