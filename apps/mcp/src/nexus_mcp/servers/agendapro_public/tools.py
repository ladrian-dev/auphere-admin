"""Tool classes registered into the MCP registry as INTERNAL.

These never appear in ``tool_catalog`` (they're not LLM-facing) and the
LLM cannot reach them via ``MCPRegistry.dispatch`` — only the booking
facade and the async booking cron call them via ``dispatch_internal``
with the in-process caller token.
"""

from __future__ import annotations

from nexus_mcp.base import ToolBase
from nexus_mcp.servers.agendapro_public.schemas import (
    CheckAvailabilityPublicInput,
    CheckAvailabilityPublicOutput,
    CreateAppointmentPublicInput,
    CreateAppointmentPublicOutput,
)
from nexus_mcp.servers.agendapro_public.transport import get_default_transport
from nexus_mcp.subprocess_tool import make_subprocess_tool_class

# Both tools use the same transport indirection — the Node binary
# exposes them on the same stdio JSON-RPC channel. The transport is
# resolved at dispatch time so tests can inject a fake.

CheckAvailabilityPublic = make_subprocess_tool_class(
    name="agendapro_public.check_availability",
    description=(
        "Read the public AgendaPro booking link for a tenant and list available "
        "time slots on a given date. Internal — invoked by the booking facade "
        "to enrich a customer's intent before scheduling the async booking job."
    ),
    input_model=CheckAvailabilityPublicInput,
    output_model=CheckAvailabilityPublicOutput,
    transport_provider=get_default_transport,
    side_effects=("external_api",),
    timeout_s=45.0,
)


CreateAppointmentPublic = make_subprocess_tool_class(
    name="agendapro_public.create_appointment",
    description=(
        "Walk the public AgendaPro booking wizard end-to-end and return the "
        "confirmation code. Internal — invoked by the async booking cron, "
        "never directly by the agent."
    ),
    input_model=CreateAppointmentPublicInput,
    output_model=CreateAppointmentPublicOutput,
    transport_provider=get_default_transport,
    side_effects=("external_api", "mutates_db"),
    # 90s upper bound covers: session boot (~5s) + wizard navigation
    # (~25s p95) + retries inside Stagehand (~30s). Anything longer
    # is almost certainly stuck — the cron will mark it failed.
    timeout_s=90.0,
)


def build_agendapro_public_tools() -> list[ToolBase]:
    """Materialise instances. The MCP registry calls this at registry
    construction time (build_default_registry)."""
    return [CheckAvailabilityPublic(), CreateAppointmentPublic()]


AGENDAPRO_PUBLIC_TOOLS: tuple[type[ToolBase], ...] = (
    CheckAvailabilityPublic,
    CreateAppointmentPublic,
)
