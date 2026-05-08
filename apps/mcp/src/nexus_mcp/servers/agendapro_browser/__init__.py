"""Adapter Python para el server subprocess agendapro_browser_mcp (Bloque E).

Las clases ``ToolBase`` que viven aquí son ``SubprocessTool``s — su
``run()`` serializa el payload y delega vía stdio JSON-RPC al server
Node (Stagehand v3 + Browserbase Contexts) que vive en
``apps/mcp/servers/agendapro_browser_mcp/``.

Se registran en el espacio interno del ``MCPRegistry``: el LLM nunca las
ve, solo las invoca el booking-server vía ``dispatch_internal`` cuando
detecta que el tenant tiene la integration AgendaPro activa.
"""

from nexus_mcp.servers.agendapro_browser.tools import (
    AGENDAPRO_INTERNAL_TOOL_NAMES,
    build_agendapro_tools,
)

__all__ = ["AGENDAPRO_INTERNAL_TOOL_NAMES", "build_agendapro_tools"]
