"""broadcasts + broadcast_recipients — tenant-scoped fan-out tracking

Revision ID: 0048
Revises: 0047
Create Date: 2026-07-05

ADR-028 — one row per ``POST /v1/embed/broadcasts`` call plus one per
recipient. The fan-out service expands a broadcast into N ``messages``
rows that the existing outbound dispatcher drains; these tables only
hold the grouping and the per-recipient acceptance verdict
(queued/rejected). Delivery state is read by JOINing
``broadcast_recipients.message_id → messages`` — never duplicated.

Both tables get RLS + FORCE with the exact policy shape of migration
0002, so the embed JWT surface (which runs under ``SET LOCAL
app.tenant_id`` + ``SET LOCAL ROLE nexus_app``) is structurally unable
to touch another tenant's broadcasts.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "0048_broadcasts"
down_revision: str | Sequence[str] | None = "0047_partners_platform"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCOPED_TABLES: tuple[str, ...] = ("broadcasts", "broadcast_recipients")


def upgrade() -> None:
    op.create_table(
        "broadcasts",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("partner_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "channel_id",
            UUID(as_uuid=True),
            sa.ForeignKey("channels.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("template_name", sa.String(120), nullable=False),
        sa.Column("template_language", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="accepted"),
        sa.Column("total", sa.Integer, nullable=False, server_default="0"),
        sa.Column("accepted_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rejected_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(80), nullable=True),
        sa.Column("jti", sa.String(40), nullable=True),
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
        sa.CheckConstraint("status IN ('accepted', 'completed')", name="ck_broadcasts_status"),
    )
    op.create_index(
        "uq_broadcasts_tenant_idempotency",
        "broadcasts",
        ["tenant_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_index("ix_broadcasts_tenant_created", "broadcasts", ["tenant_id", "created_at"])

    op.create_table(
        "broadcast_recipients",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "broadcast_id",
            UUID(as_uuid=True),
            sa.ForeignKey("broadcasts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("phone_e164", sa.String(20), nullable=False),
        sa.Column("params", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reject_reason", sa.String(80), nullable=True),
        sa.Column(
            "message_id",
            UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
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
        sa.CheckConstraint(
            "status IN ('queued', 'rejected')", name="ck_broadcast_recipients_status"
        ),
        sa.UniqueConstraint("broadcast_id", "phone_e164", name="uq_broadcast_recipients_phone"),
    )
    op.create_index(
        "ix_broadcast_recipients_tenant_broadcast",
        "broadcast_recipients",
        ["tenant_id", "broadcast_id"],
    )

    # RLS + FORCE, exact 0002 pattern: missing app.tenant_id → NULL
    # predicate → zero rows. Fails closed.
    for table in SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
            USING (
                tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            )
            WITH CHECK (
                tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            )
            """
        )

    op.execute("GRANT SELECT, INSERT, UPDATE ON broadcasts, broadcast_recipients TO nexus_app")


def downgrade() -> None:
    op.execute("REVOKE ALL ON broadcasts, broadcast_recipients FROM nexus_app")
    for table in SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
    op.drop_table("broadcast_recipients")
    op.drop_table("broadcasts")
