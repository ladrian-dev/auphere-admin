"""operator_notifications + messages.attempts/last_error — block F

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-09

Block F adds three things:

1. ``operator_notifications`` — ledger that prevents the operator alerter
   from re-notifying on the same ``audit_log`` row across ticks. One row
   per ``audit_log_id`` (UNIQUE). The alerter inserts with status='pending'
   BEFORE sending so a crash mid-call still leaves a dedup marker.

2. ``messages.attempts`` (int, default 0) — outbound dispatcher retry
   counter. Bumped on each failure; row is parked at 'failed' once it
   reaches MAX_ATTEMPTS.

3. ``messages.last_error`` (text, null) — last failure detail for
   ops triage (the panel renders it in the conversation view).

All tenant-scoped tables here remain RLS+FORCE.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE operator_notification_status AS ENUM "
        "('pending', 'sent', 'failed')"
    )
    on_status = postgresql.ENUM(
        "pending",
        "sent",
        "failed",
        name="operator_notification_status",
        create_type=False,
    )

    op.create_table(
        "operator_notifications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "audit_log_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("audit_log.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("template_name", sa.String(120), nullable=False),
        sa.Column("status", on_status, nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retried_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("audit_log_id", name="uq_operator_notifications_audit_log"),
    )
    op.create_index(
        "ix_operator_notifications_tenant_id",
        "operator_notifications",
        ["tenant_id"],
    )
    op.create_index(
        "ix_operator_notifications_status",
        "operator_notifications",
        ["status", "created_at"],
    )

    op.execute("ALTER TABLE operator_notifications ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE operator_notifications FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY operator_notifications_tenant_isolation ON operator_notifications
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """
    )

    # ── messages: outbound retry bookkeeping ─────────────────────────────────
    op.add_column(
        "messages",
        sa.Column(
            "attempts", sa.Integer, nullable=False, server_default="0"
        ),
    )
    op.add_column("messages", sa.Column("last_error", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "last_error")
    op.drop_column("messages", "attempts")

    op.execute(
        "DROP POLICY IF EXISTS operator_notifications_tenant_isolation "
        "ON operator_notifications"
    )
    op.execute("ALTER TABLE operator_notifications NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE operator_notifications DISABLE ROW LEVEL SECURITY")
    op.drop_index(
        "ix_operator_notifications_status", table_name="operator_notifications"
    )
    op.drop_index(
        "ix_operator_notifications_tenant_id", table_name="operator_notifications"
    )
    op.drop_table("operator_notifications")
    op.execute("DROP TYPE IF EXISTS operator_notification_status")
