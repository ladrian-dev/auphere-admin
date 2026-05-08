"""seed tool_catalog with the barbershop_v1 capabilities

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-08

Idempotent: uses ON CONFLICT (name) DO NOTHING. Adding new tools is a normal
PR with a new migration; deprecating uses an UPDATE in a later migration.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (name, description, mcp_server, side_effects, capability_tags)
TOOLS: list[tuple[str, str, str, list[str], list[str]]] = [
    # booking
    (
        "booking.check_availability",
        "Check available time slots for a service and barber.",
        "booking-server",
        ["external_api"],
        ["booking", "barbershop"],
    ),
    (
        "booking.create_appointment",
        "Create a new appointment. Requires idempotency key.",
        "booking-server",
        ["external_api", "mutates_db"],
        ["booking", "barbershop"],
    ),
    (
        "booking.modify_appointment",
        "Modify an existing appointment owned by the tenant.",
        "booking-server",
        ["external_api", "mutates_db"],
        ["booking", "barbershop"],
    ),
    (
        "booking.cancel_appointment",
        "Cancel an appointment; applies cancellation fee per policy.",
        "booking-server",
        ["external_api", "mutates_db"],
        ["booking", "barbershop"],
    ),
    (
        "booking.get_appointments",
        "Read current appointments for a customer.",
        "booking-server",
        ["external_api"],
        ["booking", "barbershop"],
    ),
    # queue
    (
        "queue.join_queue",
        "Add a customer to the walk-in queue.",
        "queue-server",
        ["mutates_db"],
        ["queue", "barbershop"],
    ),
    (
        "queue.get_position",
        "Return position of a customer in the queue.",
        "queue-server",
        [],
        ["queue", "barbershop"],
    ),
    (
        "queue.get_estimated_wait",
        "Estimate wait time for a customer.",
        "queue-server",
        [],
        ["queue", "barbershop"],
    ),
    (
        "queue.check_in",
        "Mark customer arrived; notifies barber.",
        "queue-server",
        ["mutates_db", "sends_message"],
        ["queue", "barbershop"],
    ),
    (
        "queue.remove_from_queue",
        "Remove customer from the queue.",
        "queue-server",
        ["mutates_db"],
        ["queue", "barbershop"],
    ),
    # client
    (
        "client.get_preferences",
        "Read customer preferences from KG.",
        "client-server",
        [],
        ["client"],
    ),
    (
        "client.update_preferences",
        "Persist customer preferences to KG.",
        "client-server",
        ["mutates_db"],
        ["client"],
    ),
    (
        "client.get_history",
        "Last N appointments for the customer.",
        "client-server",
        [],
        ["client"],
    ),
    # notification
    (
        "notification.send_template",
        "Send a Meta-approved WhatsApp template.",
        "notification-server",
        ["sends_message"],
        ["notification"],
    ),
    (
        "notification.send_text",
        "Send free-form text within 24h customer window.",
        "notification-server",
        ["sends_message"],
        ["notification"],
    ),
    (
        "notification.schedule_reminder",
        "Schedule a reminder via Dramatiq cron.",
        "notification-server",
        ["mutates_db"],
        ["notification"],
    ),
    (
        "notification.cancel_scheduled",
        "Cancel a scheduled reminder.",
        "notification-server",
        ["mutates_db"],
        ["notification"],
    ),
    # commission
    (
        "commission.calculate_commission",
        "Compute commission for a transaction.",
        "commission-server",
        [],
        ["commission", "barbershop"],
    ),
    (
        "commission.get_barber_earnings",
        "Aggregate earnings of a barber.",
        "commission-server",
        [],
        ["commission", "barbershop"],
    ),
    (
        "commission.get_daily_report",
        "Daily commission report.",
        "commission-server",
        [],
        ["commission", "barbershop"],
    ),
    # escalate
    (
        "escalate.escalate_to_human",
        "Hand off the conversation to an operator.",
        "escalate-server",
        ["sends_message"],
        ["escalate"],
    ),
]


def upgrade() -> None:
    for name, desc, server, side_effects, tags in TOOLS:
        op.execute(
            f"""
            INSERT INTO tool_catalog
                (name, description, mcp_server, side_effects, capability_tags,
                 input_schema, output_schema, cost_estimate, status)
            VALUES (
                {_q(name)}, {_q(desc)}, {_q(server)},
                ARRAY[{",".join(_q(s) for s in side_effects)}]::varchar(40)[],
                ARRAY[{",".join(_q(t) for t in tags)}]::varchar(40)[],
                '{json.dumps({})}'::jsonb,
                '{json.dumps({})}'::jsonb,
                '{json.dumps({})}'::jsonb,
                'active'
            )
            ON CONFLICT (name) DO NOTHING
            """
        )


def downgrade() -> None:
    names = ",".join(_q(t[0]) for t in TOOLS)
    op.execute(f"DELETE FROM tool_catalog WHERE name IN ({names})")


def _q(s: str) -> str:
    """SQL string literal with single-quote escaping."""
    return "'" + s.replace("'", "''") + "'"
