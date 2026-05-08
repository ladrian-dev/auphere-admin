"""scheduled_jobs table + queue_entries table + messages.status column

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-08

Block D additions:

1. ``scheduled_jobs`` — durable record of any time-deferred action created by
   a tool (notification.schedule_reminder for now; extensible). Block H wires
   the dispatcher cron that drains pending rows where ``run_at <= now()``.

2. ``queue_entries`` — historical record of queue events. queue-server keeps
   live state in Redis (hot, latency-sensitive); this table records the
   join/check_in/leave events for analytics, ``commission.get_daily_report``
   and reload-from-cold (so a Redis flush doesn't wipe customer-visible
   queue history).

3. ``messages.status`` — outbound messages are not necessarily sent at write
   time. Default is ``sent`` so the existing checkpoint node behaviour is
   unchanged; ``notification.send_template`` and ``notification.send_text``
   write rows with status=``pending`` and Block F drains them via YCloud.

All three are tenant-scoped and wear the standard RLS policy.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── scheduled_jobs ─────────────────────────────────────────────────────
    op.execute("CREATE TYPE scheduled_job_kind AS ENUM ('reminder')")
    op.execute(
        "CREATE TYPE scheduled_job_status AS ENUM "
        "('pending', 'sent', 'cancelled', 'failed')"
    )
    sj_kind = postgresql.ENUM("reminder", name="scheduled_job_kind", create_type=False)
    sj_status = postgresql.ENUM(
        "pending", "sent", "cancelled", "failed", name="scheduled_job_status", create_type=False
    )

    op.create_table(
        "scheduled_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sj_kind, nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sj_status, nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text, nullable=True),
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
    )
    op.create_index("ix_scheduled_jobs_tenant_id", "scheduled_jobs", ["tenant_id"])
    op.create_index(
        "ix_scheduled_jobs_dispatch",
        "scheduled_jobs",
        ["status", "run_at"],
    )

    op.execute("ALTER TABLE scheduled_jobs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE scheduled_jobs FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY scheduled_jobs_tenant_isolation ON scheduled_jobs
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """
    )

    # ── queue_entries ──────────────────────────────────────────────────────
    op.execute(
        "CREATE TYPE queue_entry_status AS ENUM "
        "('waiting', 'checked_in', 'served', 'left')"
    )
    qe_status = postgresql.ENUM(
        "waiting",
        "checked_in",
        "served",
        "left",
        name="queue_entry_status",
        create_type=False,
    )

    op.create_table(
        "queue_entries",
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
        sa.Column("service_name", sa.String(120), nullable=False),
        sa.Column(
            "barber_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("kg_nodes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", qe_status, nullable=False, server_default="waiting"),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("served_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
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
    )
    op.create_index("ix_queue_entries_tenant_id", "queue_entries", ["tenant_id"])
    op.create_index(
        "ix_queue_entries_tenant_status_joined",
        "queue_entries",
        ["tenant_id", "status", "joined_at"],
    )

    op.execute("ALTER TABLE queue_entries ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE queue_entries FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY queue_entries_tenant_isolation ON queue_entries
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """
    )

    # ── messages.status ────────────────────────────────────────────────────
    op.execute("CREATE TYPE message_status AS ENUM ('pending', 'sent', 'failed')")
    msg_status = postgresql.ENUM(
        "pending", "sent", "failed", name="message_status", create_type=False
    )
    op.add_column(
        "messages",
        sa.Column("status", msg_status, nullable=False, server_default="sent"),
    )


def downgrade() -> None:
    op.drop_column("messages", "status")
    op.execute("DROP TYPE IF EXISTS message_status")

    op.execute("DROP POLICY IF EXISTS queue_entries_tenant_isolation ON queue_entries")
    op.execute("ALTER TABLE queue_entries NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE queue_entries DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_queue_entries_tenant_status_joined", table_name="queue_entries")
    op.drop_index("ix_queue_entries_tenant_id", table_name="queue_entries")
    op.drop_table("queue_entries")
    op.execute("DROP TYPE IF EXISTS queue_entry_status")

    op.execute("DROP POLICY IF EXISTS scheduled_jobs_tenant_isolation ON scheduled_jobs")
    op.execute("ALTER TABLE scheduled_jobs NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE scheduled_jobs DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_scheduled_jobs_dispatch", table_name="scheduled_jobs")
    op.drop_index("ix_scheduled_jobs_tenant_id", table_name="scheduled_jobs")
    op.drop_table("scheduled_jobs")
    op.execute("DROP TYPE IF EXISTS scheduled_job_status")
    op.execute("DROP TYPE IF EXISTS scheduled_job_kind")
