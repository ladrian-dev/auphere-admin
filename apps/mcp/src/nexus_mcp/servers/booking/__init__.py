"""booking-server — facade over the local appointments table.

Every mutation persists in our DB; ``external_ref`` stays NULL. Spec 048
retired it: no new agent gets ``booking.*`` (they book with ``reservas.*``)
and it runs only for the versions that still name it, until the final
removal. The five LLM-facing tool names remain stable until then.
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
