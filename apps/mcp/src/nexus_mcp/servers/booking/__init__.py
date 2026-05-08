"""booking-server — facade over the local appointments table.

Block D persists appointments locally. Block E will introduce
``agendapro_browser_mcp``; ``booking.create_appointment`` will then delegate
to AgendaPro for tenants on AgendaPro and keep the local row as a shadow
cache. The five LLM-facing tool names remain stable.
"""

from nexus_mcp.servers.booking.tools import (
    BOOKING_TOOLS,
    CancelAppointment,
    CheckAvailability,
    CreateAppointment,
    GetAppointments,
    ModifyAppointment,
)

__all__ = [
    "BOOKING_TOOLS",
    "CancelAppointment",
    "CheckAvailability",
    "CreateAppointment",
    "GetAppointments",
    "ModifyAppointment",
]
