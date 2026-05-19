"""qa.* schema for the QA Playground (ADR-020, Phase 3)

Revision ID: 0025
Revises: 0024
Create Date: 2026-05-19

Introduces three tables under a dedicated ``qa`` schema:
  - ``qa.threads``            — one row per QA conversation an operator
                                holds with an agent. Scoped by operator
                                AND tenant.
  - ``qa.side_effect_audit``  — every tool dispatch attempt that the
                                ``dry_run`` middleware blocked. The QA
                                Playground never lets the agent reach out
                                to the real world; this table is the
                                evidence that the guarantee holds.
  - ``qa.audit_log``          — operator actions (created thread, opened
                                inspector, copied diff, …). Distinct from
                                the global ``audit_log`` because (a) it's
                                scoped by operator, not tenant, and (b)
                                it captures intent-of-the-operator events
                                that have no tenant_id correlate.

All three are RLS-protected by ``operator_id`` using the same fail-closed
pattern as migration 0002: policies read
``current_setting('app.operator_id', true)`` and the missing-value branch
yields an empty result set. The qa endpoints set both
``app.tenant_id`` (for the tenant-scoped tables the agent reads) and
``app.operator_id`` (for these qa.* tables).

The ``nexus_app`` role is created in 0004; we grant it CRUD on the new
schema explicitly so that role-switched sessions can actually touch the
tables. The connecting ``nexus`` user is a superuser and bypasses RLS;
QA requests always run under the role-switched nexus_app role.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025"
down_revision: str | Sequence[str] | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


QA_TABLES: tuple[str, ...] = (
    "threads",
    "side_effect_audit",
    "audit_log",
)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS qa")

    # ── qa.threads ─────────────────────────────────────────────────────────
    op.create_table(
        "threads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("operator_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        # External id is the thread_id assigned by the LangGraph Server.
        # NULL until the first run is dispatched.
        sa.Column("external_id", sa.String(length=120), nullable=True, unique=True),
        sa.Column("title", sa.String(length=200), nullable=False, server_default=sa.text("'Untitled'")),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("message_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        schema="qa",
    )
    op.create_index(
        "ix_qa_threads_operator_tenant",
        "threads",
        ["operator_id", "tenant_id"],
        schema="qa",
    )

    # ── qa.side_effect_audit ───────────────────────────────────────────────
    op.create_table(
        "side_effect_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("operator_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "thread_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("qa.threads.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("tool_name", sa.String(length=160), nullable=False),
        sa.Column("tool_args", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("synthetic_result", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("blocked_reason", sa.String(length=80), nullable=False, server_default=sa.text("'dry_run'")),
        sa.Column("run_id", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        schema="qa",
    )
    op.create_index(
        "ix_qa_side_effect_audit_thread_created",
        "side_effect_audit",
        ["thread_id", "created_at"],
        schema="qa",
    )

    # ── qa.audit_log ───────────────────────────────────────────────────────
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("operator_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("target_kind", sa.String(length=60), nullable=True),
        sa.Column("target_id", sa.String(length=120), nullable=True),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        schema="qa",
    )
    op.create_index(
        "ix_qa_audit_log_operator_created",
        "audit_log",
        ["operator_id", "created_at"],
        schema="qa",
    )

    # ── RLS by operator_id (fail-closed) ───────────────────────────────────
    for table in QA_TABLES:
        op.execute(f"ALTER TABLE qa.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE qa.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY qa_{table}_operator_isolation ON qa.{table}
            USING (
                operator_id = NULLIF(current_setting('app.operator_id', true), '')::uuid
            )
            WITH CHECK (
                operator_id = NULLIF(current_setting('app.operator_id', true), '')::uuid
            )
            """
        )

    # Grant CRUD on the new schema + tables to the application role. The
    # role is created in migration 0004; without these grants the
    # role-switched session sees the policy succeed but the GRANT denies
    # access, which manifests as a confusing 403 from PostgreSQL.
    op.execute("GRANT USAGE ON SCHEMA qa TO nexus_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA qa TO nexus_app")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA qa "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO nexus_app"
    )


def downgrade() -> None:
    for table in QA_TABLES:
        op.execute(f"DROP POLICY IF EXISTS qa_{table}_operator_isolation ON qa.{table}")
        op.execute(f"ALTER TABLE IF EXISTS qa.{table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE IF EXISTS qa.{table} DISABLE ROW LEVEL SECURITY")

    op.drop_table("audit_log", schema="qa")
    op.drop_table("side_effect_audit", schema="qa")
    op.drop_table("threads", schema="qa")
    op.execute("DROP SCHEMA IF EXISTS qa")
