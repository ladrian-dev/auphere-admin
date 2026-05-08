"""Tool registry — name → callable that returns a deterministic payload.

Each handler:
- Pulls ``tenant_id`` from ``require_current_tenant()``. Never accepts it as
  an argument from the LLM (architecture/tool-catalog.md "Tenant-scoped en
  runtime").
- Returns a serialisable dict the pipeline can persist into ``Message.tool_calls``.

Handlers in block C are stubs. They exist so the runtime tests can drive a
realistic dispatch loop without standing up MCP servers (those land in block D).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from nexus_api.core.tenant_context import require_current_tenant


class ToolError(Exception):
    """Raised by a handler when execution fails for a tenant-internal reason."""


class ToolNotInWhitelist(ToolError):
    """Raised by ``call_with_whitelist`` when the requested tool is missing
    from the active ``agent_config.tools`` for this tenant. The metric
    ``isolation.tool_whitelist_violation`` is incremented BEFORE the exception
    propagates so callers do not need to remember to record it."""


ToolResult = dict[str, Any]
ToolHandler = Callable[[dict[str, Any]], ToolResult]


@dataclass(frozen=True)
class _Stub:
    name: str
    payload: dict[str, Any]

    def __call__(self, args: dict[str, Any]) -> ToolResult:
        # Tenant binding must be present — even though the stub does not query
        # the DB, asserting this here mirrors the production tools and catches
        # accidental tool calls outside a tenant-scoped run.
        tenant_id = require_current_tenant()
        return {
            "tool": self.name,
            "tenant_id": str(tenant_id),
            "args": dict(args),
            "result": dict(self.payload),
            "stub": True,
            "executed_at": datetime.now(UTC).isoformat(),
        }


# ── Catalog of stub responses ──────────────────────────────────────────────────
# The shape of ``result`` is intentionally minimal — block D wires the real
# MCP servers and the LLM's downstream prompt is the only consumer. Each stub
# carries enough to make a smoke test assert intent + tool dispatch.

_STUBS: dict[str, dict[str, Any]] = {
    # Booking
    "booking.check_availability": {"available": True, "slots": ["10:00", "14:00", "17:00"]},
    "booking.create_appointment": {"appointment_id": "stub-appt-1", "status": "confirmed"},
    "booking.modify_appointment": {"status": "modified"},
    "booking.cancel_appointment": {"status": "cancelled", "fee_pct": 0},
    "booking.get_appointments": {"appointments": []},
    # Queue
    "queue.join_queue": {"position": 3, "wait_minutes": 25},
    "queue.get_position": {"position": 3, "wait_minutes": 25},
    "queue.get_estimated_wait": {"wait_minutes": 25},
    "queue.check_in": {"status": "checked_in"},
    "queue.remove_from_queue": {"status": "removed"},
    # Client
    "client.get_preferences": {"preferred_barber": None, "favourite_service": None},
    "client.update_preferences": {"status": "updated"},
    "client.get_history": {"appointments": []},
    # Notification
    "notification.send_template": {"status": "queued"},
    "notification.send_text": {"status": "queued"},
    "notification.schedule_reminder": {"reminder_id": "stub-rem-1"},
    "notification.cancel_scheduled": {"status": "cancelled"},
    # Commission
    "commission.calculate_commission": {"amount": 0, "currency": "CLP"},
    "commission.get_barber_earnings": {"total": 0, "currency": "CLP"},
    "commission.get_daily_report": {"appointments": 0, "earnings": 0},
    # Escalate
    "escalate.escalate_to_human": {"status": "operator_notified"},
}


_HANDLERS: dict[str, ToolHandler] = {
    name: _Stub(name=name, payload=p) for name, p in _STUBS.items()
}


def get_handler(name: str) -> ToolHandler:
    handler = _HANDLERS.get(name)
    if handler is None:
        raise ToolError(f"tool {name!r} is not registered")
    return handler


def list_tool_names() -> Iterable[str]:
    return tuple(_HANDLERS)
