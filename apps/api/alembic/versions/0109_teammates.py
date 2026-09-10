"""Spec 003 — el roster de teammates es del partner (Requisitos 1, 3.1).

``teammates`` es una tabla de **partner**: todos los miembros ven los mismos
(decisión 8), ningún otro partner ve ninguno, y ``nexus_app`` **no puede
borrar** (R2.6: se archiva). ``companion.threads`` y ``companion.runs`` ganan el
eje ``teammate_id``; la RLS por persona de 0090 no se toca — el hilo sigue
siendo de quien lo abrió, y el teammate es una columna más.

Revision ID: 0109_teammates
Revises: 0108_device_audit_vocab
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0109_teammates"
down_revision: str | Sequence[str] | None = "0108_device_audit_vocab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PARTNER = "NULLIF(current_setting('app.partner_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "teammates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "partner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("partners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("job", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("tool_names", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("permissions", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("local_exec", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 80", name="teammates_name_len"),
        sa.CheckConstraint("char_length(job) BETWEEN 1 AND 80", name="teammates_job_len"),
        sa.CheckConstraint("status IN ('active', 'archived')", name="teammates_status_check"),
        sa.CheckConstraint(
            "(status = 'archived') = (archived_at IS NOT NULL)", name="teammates_archived_consistent"
        ),
    )
    op.create_index("ix_teammates_partner_status", "teammates", ["partner_id", "status"])

    op.execute("ALTER TABLE teammates ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE teammates FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY teammates_partner ON teammates
        USING (partner_id = {_PARTNER})
        WITH CHECK (partner_id = {_PARTNER})
        """
    )
    # R2.6 — borrar no existe. La aplicación archiva; la base no deja borrar.
    op.execute("REVOKE DELETE ON teammates FROM nexus_app")

    op.add_column(
        "threads",
        sa.Column(
            "teammate_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teammates.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        schema="companion",
    )
    op.create_index(
        "ix_companion_threads_principal_teammate",
        "threads",
        ["principal_id", "teammate_id"],
        schema="companion",
    )
    op.add_column(
        "runs",
        sa.Column("teammate_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="companion",
    )
    op.create_index(
        "ix_companion_runs_teammate_started",
        "runs",
        ["teammate_id", "started_at"],
        schema="companion",
    )


def downgrade() -> None:
    op.drop_index("ix_companion_runs_teammate_started", table_name="runs", schema="companion")
    op.drop_column("runs", "teammate_id", schema="companion")
    op.drop_index("ix_companion_threads_principal_teammate", table_name="threads", schema="companion")
    op.drop_column("threads", "teammate_id", schema="companion")
    op.execute("DROP POLICY IF EXISTS teammates_partner ON teammates")
    op.drop_index("ix_teammates_partner_status", table_name="teammates")
    op.drop_table("teammates")
