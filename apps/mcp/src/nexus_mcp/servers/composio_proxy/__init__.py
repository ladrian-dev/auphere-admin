"""Runtime proxy for Composio-backed tools.

Closes the G1 gap from the 2026-05-13 audit: until this module landed,
tools synced from Composio appeared in ``tool_catalog`` and could be
whitelisted on a tenant's ``agent_config`` but the worker had no path
to execute them — the registry only knew static in-process servers.

Composio toolkits are per-tenant (the ``connection_id`` ties an
account to a single ``user_id = f"tenant_{slug}"``). We can't register
the proxies once at process start because each tenant has its own
connection. Instead the worker pipeline asks
:func:`build_composio_proxies_for_tenant` per turn (cheap — the
Composio adapter is in-memory, only the ``execute`` call hits the
network) and merges the resulting tools into the MCP registry view
for that turn.
"""

from nexus_mcp.servers.composio_proxy.proxy import (
    ComposioProxyTool,
    ComposioToolBlueprint,
    build_composio_proxies_for_tenant,
    load_blueprints_for_tenant,
)

__all__ = [
    "ComposioProxyTool",
    "ComposioToolBlueprint",
    "build_composio_proxies_for_tenant",
    "load_blueprints_for_tenant",
]
