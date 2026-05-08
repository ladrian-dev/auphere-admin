"""Transports for MCP servers.

Bloque D corre los 6 servers in-process. Bloque E introduce el primer
subprocess (AgendaPro browser MCP, Node + Stagehand). El transporte stdio
JSON-RPC vive aquí; el adapter ``SubprocessTool`` lo usa para que el
``MCPRegistry.dispatch`` no se entere de la diferencia.
"""

from nexus_mcp.transports.pool import SubprocessPool
from nexus_mcp.transports.stdio import (
    StdioMCPClient,
    StdioMCPClientFactory,
    StdioTransportError,
)

__all__ = [
    "StdioMCPClient",
    "StdioMCPClientFactory",
    "StdioTransportError",
    "SubprocessPool",
]
