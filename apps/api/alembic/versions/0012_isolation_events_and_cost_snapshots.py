"""isolation_events + daily_cost_snapshots + tenants.cost_alert_threshold — block H

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-09

Block H persists three new pieces of state:

1. ``tenants.cost_alert_threshold_usd_per_day`` (NUMERIC, default 40) —
   per-tenant daily cost ceiling. Pro tier defaults to $40/day per
   ADR-007 + clients/cultor-barber. Override per-tenant by UPDATE.

2. ``isolation_events`` — append-only ledger for every increment of an
   ``isolation.*`` counter. The ``/admin/tenants/:id/isolation/metrics``
   endpoint reads the last 24h here to power the dashboard. The 7
   guarantees from architecture/agent-isolation.md become an audit
   trail, not just an in-memory number. RLS+FORCE.

3. ``daily_cost_snapshots`` — one row per (tenant_id, day) populated
   by the cost rollup cron. Driver of the cost.daily_threshold_exceeded
   audit + WhatsApp alert to Lee. UNIQUE(tenant_id, day) so re-runs
   upsert. RLS+FORCE.

The tenants table stays global (no RLS), matching block B's split.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_RLS_POLICY_SQL = """
CREATE POLICY {table}_tenant_isolation ON {table}
USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
"""


def upgrade() -> None:
    # ── tenants: cost alert threshold ───────────────────────────────────────
    op.add_column(
        "tenants",
        sa.Column(
            "cost_alert_threshold_usd_per_day",
            sa.Numeric(10, 2),
            nullable=False,
            server_default="40.00",
        ),
    )

    # ── isolation_events ────────────────────────────────────────────────────
    op.create_table(
        "isolation_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metric", sa.String(80), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_isolation_events_tenant_metric_created",
        "isolation_events",
        ["tenant_id", "metric", "created_at"],
    )
    op.execute("ALTER TABLE isolation_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE isolation_events FORCE ROW LEVEL SECURITY")
    op.execute(_RLS_POLICY_SQL.format(table="isolation_events"))

    # ── daily_cost_snapshots ────────────────────────────────────────────────
    op.create_table(
        "daily_cost_snapshots",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("day", sa.Date, nullable=False),
        sa.Column(
            "cost_usd_total",
            sa.Numeric(12, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "message_count",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "threshold_exceeded_at",
            sa.DateTime(timezone=True),
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
        sa.UniqueConstraint("tenant_id", "day", name="uq_daily_cost_snapshots_tenant_day"),
    )
    op.create_index(
        "ix_daily_cost_snapshots_tenant_day",
        "daily_cost_snapshots",
        ["tenant_id", "day"],
    )
    op.execute("ALTER TABLE daily_cost_snapshots ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE daily_cost_snapshots FORCE ROW LEVEL SECURITY")
    op.execute(_RLS_POLICY_SQL.format(table="daily_cost_snapshots"))


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS daily_cost_snapshots_tenant_isolation "
        "ON daily_cost_snapshots"
    )
    op.execute("ALTER TABLE daily_cost_snapshots NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE daily_cost_snapshots DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_daily_cost_snapshots_tenant_day", table_name="daily_cost_snapshots")
    op.drop_table("daily_cost_snapshots")

    op.execute(
        "DROP POLICY IF EXISTS isolation_events_tenant_isolation ON isolation_events"
    )
    op.execute("ALTER TABLE isolation_events NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE isolation_events DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_isolation_events_tenant_metric_created", table_name="isolation_events")
    op.drop_table("isolation_events")

    op.drop_column("tenants", "cost_alert_threshold_usd_per_day")
