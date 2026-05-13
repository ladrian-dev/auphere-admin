"""async booking jobs — ScheduledJobKind.ASYNC_BOOKING (Block O / ADR-017)

Revision ID: 0022
Revises: 0021
Create Date: 2026-05-13

Block O introduces the async booking model documented in ADR-017:

1. ``booking.create_appointment`` no longer attempts to talk to AgendaPro
   inline. When the tenant has ``agendapro_public_url`` set, the tool:
   - Inserts a local ``appointments`` row with ``status=BOOKED`` and
     ``external_ref=NULL`` (provisional).
   - Enqueues a ``scheduled_jobs`` row of kind ``async_booking`` carrying
     the parameters needed to drive the public-link wizard.
   - Returns ACK to the agent so the customer sees an immediate
     "te confirmo en 1-2 minutos" reply.

2. The new ``async_booking_cron`` worker drains those jobs:
   - Calls ``agendapro_public.create_appointment`` via dispatch_internal.
   - On success: updates the local ``appointments.external_ref`` and
     fires ``notification.send_template(booking_confirmation, ...)``.
   - On failure: marks the appointment ``status=ERROR`` and dispatches
     ``operator.consult_owner`` so the owner can resolve manually
     (ADR-018).

The migration adds the new enum value via ``ALTER TYPE`` and a partial
index on ``(kind, status, run_at)`` so the cron's
``SELECT ... FOR UPDATE SKIP LOCKED`` scan stays cheap.

Downgrade leaves the enum value (PG doesn't allow removing values from
an enum type).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0022"
down_revision: str | Sequence[str] | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add the new enum value. PG 12+ allows this inside a transaction
    # but the value CANNOT be referenced in the same transaction it was
    # added — the partial index that uses ``kind = 'async_booking'`` is
    # split out to migration 0023 so the enum is durably committed
    # before any DDL references it.
    op.execute("ALTER TYPE scheduled_job_kind ADD VALUE IF NOT EXISTS 'async_booking'")

    # 2. ``appointments.public_booking_status`` + CHECK constraint +
    # partial index. These don't reference the new enum value (only the
    # new string column we just added), so they're safe in this tx.
    op.add_column(
        "appointments",
        sa.Column("public_booking_status", sa.String(20), nullable=True),
    )
    op.create_check_constraint(
        "ck_appointments_public_booking_status",
        "appointments",
        "public_booking_status IS NULL OR public_booking_status IN ("
        "'pending', 'in_progress', 'confirmed', 'failed', 'manual_escalation')",
    )
    op.create_index(
        "ix_appointments_public_pending",
        "appointments",
        ["tenant_id", "created_at"],
        postgresql_where=sa.text(
            "public_booking_status IN ('pending', 'in_progress')"
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_appointments_public_pending", table_name="appointments")
    op.drop_constraint(
        "ck_appointments_public_booking_status", "appointments", type_="check"
    )
    op.drop_column("appointments", "public_booking_status")
    # Enum value is intentionally left in place — PG doesn't allow removing values.
