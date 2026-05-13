"""booking-server — facade over the local appointments table.

Local-only Phase 1: every mutation persists in our DB; ``external_ref``
stays NULL. The new public-link AgendaPro MCP (future session) will
plug into ``CheckAvailability`` + ``CreateAppointment`` only — the
other three intents (modify / cancel / get_appointments) are escalated
to the owner via the backchannel (ADR-018). The five LLM-facing tool
names remain stable.
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
