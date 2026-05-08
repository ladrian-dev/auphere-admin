"""appointments table — booking-server backing storage

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-08

Block D introduces ``appointments`` as a relational table (not kg_nodes).
Decision recorded in architecture/mcp-registry.md: querying by
(tenant_id, starts_at), (tenant_id, customer_id, status) and
(tenant_id, barber_id, starts_at) needs proper indices, and a typed status
enum is more honest than a JSONB lookup.

When Block E (AgendaPro browser MCP) lands, this table becomes a local
shadow/cache: ``external_ref`` carries the AgendaPro id and the local row
provides denormalised fast reads + audit. The schema does not change.

Idempotency: ``UNIQUE (tenant_id, idempotency_key)`` guarantees that if
YCloud retries a webhook turn that triggered ``booking.create_appointment``
the second insert is rejected and the existing row returned.

RLS + FORCE + standard policy mirroring migration 0002.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE appointment_status AS ENUM "
        "('booked', 'confirmed', 'cancelled', 'no_show', 'completed')"
    )
    appointment_status = postgresql.ENUM(
        "booked",
        "confirmed",
        "cancelled",
        "no_show",
        "completed",
        name="appointment_status",
        create_type=False,
    )

    op.create_table(
        "appointments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        # Barber is a kg_nodes row (label='Barber'). Nullable: walk-ins or
        # "any barber" appointments.
        sa.Column(
            "barber_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("kg_nodes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("service_name", sa.String(120), nullable=False),
        sa.Column("service_duration_min", sa.Integer, nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        # Stored in minor units (cents) to avoid float drift in commission math.
        sa.Column("price_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="CLP"),
        sa.Column("status", appointment_status, nullable=False, server_default="booked"),
        sa.Column(
            "cancellation_fee_pct",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        # Required for booking.create_appointment; UNIQUE (tenant_id, key).
        sa.Column("idempotency_key", sa.String(120), nullable=True),
        # AgendaPro id once Block E lands; null until then.
        sa.Column("external_ref", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_appointments_tenant_idempotency"
        ),
    )
    op.create_index("ix_appointments_tenant_id", "appointments", ["tenant_id"])
    op.create_index(
        "ix_appointments_tenant_starts_at",
        "appointments",
        ["tenant_id", "starts_at"],
    )
    op.create_index(
        "ix_appointments_tenant_customer_status",
        "appointments",
        ["tenant_id", "customer_id", "status"],
    )
    op.create_index(
        "ix_appointments_tenant_barber_starts_at",
        "appointments",
        ["tenant_id", "barber_id", "starts_at"],
    )

    # RLS — same pattern as migration 0002.
    op.execute("ALTER TABLE appointments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE appointments FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY appointments_tenant_isolation ON appointments
        USING (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        WITH CHECK (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS appointments_tenant_isolation ON appointments")
    op.execute("ALTER TABLE appointments NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE appointments DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_appointments_tenant_barber_starts_at", table_name="appointments")
    op.drop_index("ix_appointments_tenant_customer_status", table_name="appointments")
    op.drop_index("ix_appointments_tenant_starts_at", table_name="appointments")
    op.drop_index("ix_appointments_tenant_id", table_name="appointments")
    op.drop_table("appointments")
    op.execute("DROP TYPE IF EXISTS appointment_status")
