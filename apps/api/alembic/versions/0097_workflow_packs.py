"""Fase 4 packs — workflow_packs / runs / crons / send receipts.

FORCE RLS by ``app.partner_id``. Body never carries partner_id.
CASCADE on partner and on partner_tenants (client).

Revision ID: 0097_workflow_packs
Revises: 0096_partner_knowledge_documents
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0097_workflow_packs"
down_revision: str | Sequence[str] | None = "0096_partner_knowledge_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PARTNER = "(NULLIF(current_setting('app.partner_id', true), ''))::uuid"
_TABLES = (
    "workflow_packs",
    "workflow_runs",
    "workflow_crons",
    "workflow_send_receipts",
)


def _rls(table: str) -> None:
    policy = f"{table}_partner_isolation"
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {policy} ON {table}
        USING (partner_id = {_PARTNER})
        WITH CHECK (partner_id = {_PARTNER})
        """
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO nexus_app")


def upgrade() -> None:
    op.create_table(
        "workflow_packs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_ref", sa.String(255), nullable=False),
        sa.Column("yaml", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
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
        sa.ForeignKeyConstraint(
            ["partner_id"],
            ["partners.id"],
            ondelete="CASCADE",
            name="fk_workflow_packs_partner",
        ),
        sa.ForeignKeyConstraint(
            ["partner_id", "client_ref"],
            ["partner_tenants.partner_id", "partner_tenants.external_client_ref"],
            ondelete="CASCADE",
            name="fk_workflow_packs_client",
        ),
        sa.UniqueConstraint("partner_id", "client_ref", name="uq_workflow_packs_partner_client"),
        sa.CheckConstraint("version >= 1", name="ck_workflow_packs_version"),
    )
    op.create_index("ix_workflow_packs_partner_id", "workflow_packs", ["partner_id"])

    op.create_table(
        "workflow_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pack_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thread_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
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
        sa.ForeignKeyConstraint(
            ["partner_id"],
            ["partners.id"],
            ondelete="CASCADE",
            name="fk_workflow_runs_partner",
        ),
        sa.ForeignKeyConstraint(
            ["pack_id"],
            ["workflow_packs.id"],
            ondelete="CASCADE",
            name="fk_workflow_runs_pack",
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','error','success','timeout','interrupted')",
            name="ck_workflow_runs_status",
        ),
    )
    op.create_index("ix_workflow_runs_partner_id", "workflow_runs", ["partner_id"])
    op.create_index("ix_workflow_runs_pack_id", "workflow_runs", ["pack_id"])

    op.create_table(
        "workflow_crons",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pack_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("hour", sa.Integer(), nullable=False),
        sa.Column("minute", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["partner_id"],
            ["partners.id"],
            ondelete="CASCADE",
            name="fk_workflow_crons_partner",
        ),
        sa.ForeignKeyConstraint(
            ["pack_id"],
            ["workflow_packs.id"],
            ondelete="CASCADE",
            name="fk_workflow_crons_pack",
        ),
        sa.UniqueConstraint("pack_id", name="uq_workflow_crons_pack"),
    )
    op.create_index("ix_workflow_crons_partner_id", "workflow_crons", ["partner_id"])
    op.create_index("ix_workflow_crons_due", "workflow_crons", ["enabled", "run_at_utc"])

    op.create_table(
        "workflow_send_receipts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thread_id", sa.String(128), nullable=False),
        sa.Column("step_id", sa.String(32), nullable=False),
        sa.Column("run_id", sa.String(128), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["partner_id"],
            ["partners.id"],
            ondelete="CASCADE",
            name="fk_workflow_send_receipts_partner",
        ),
        sa.UniqueConstraint(
            "thread_id",
            "step_id",
            "run_id",
            name="uq_workflow_send_receipts_key",
        ),
    )
    op.create_index(
        "ix_workflow_send_receipts_partner_id",
        "workflow_send_receipts",
        ["partner_id"],
    )

    for table in _TABLES:
        _rls(table)


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_partner_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_workflow_send_receipts_partner_id", table_name="workflow_send_receipts")
    op.drop_table("workflow_send_receipts")
    op.drop_index("ix_workflow_crons_due", table_name="workflow_crons")
    op.drop_index("ix_workflow_crons_partner_id", table_name="workflow_crons")
    op.drop_table("workflow_crons")
    op.drop_index("ix_workflow_runs_pack_id", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_partner_id", table_name="workflow_runs")
    op.drop_table("workflow_runs")
    op.drop_index("ix_workflow_packs_partner_id", table_name="workflow_packs")
    op.drop_table("workflow_packs")
