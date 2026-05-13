"""``agendapro_public`` internal MCP tools (Block O / ADR-017).

Two tools live in this namespace, both internal (NOT LLM-facing):

- ``agendapro_public.check_availability`` — drives the public booking
  wizard up to the slot picker, returns the visible time slots for
  a given date + service.
- ``agendapro_public.create_appointment`` — completes the wizard
  (service → date → slot → customer details → submit) and returns
  the confirmation code AgendaPro shows.

Both are invoked exclusively via ``dispatch_internal`` from the
booking facade (``booking.*``) and the ``async_booking_cron``. The LLM
never sees them.

The Node side lives in ``apps/mcp/servers/agendapro_public_mcp/``.
"""

from nexus_mcp.servers.agendapro_public.tools import (
    AGENDAPRO_PUBLIC_TOOLS,
    build_agendapro_public_tools,
)
from nexus_mcp.servers.agendapro_public.transport import (
    build_default_pool_from_env,
    get_default_transport,
    set_default_transport,
)

__all__ = [
    "AGENDAPRO_PUBLIC_TOOLS",
    "build_agendapro_public_tools",
    "build_default_pool_from_env",
    "get_default_transport",
    "set_default_transport",
]
