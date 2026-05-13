"""eval suite v1 — datasets + cases + runs + run_results + eval_required flag

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-13

Block P. Decision: ADR-015. Four new RLS-scoped tables plus a boolean
flag on ``tenants``:

- ``eval_datasets`` — operator-curated regression suite, one (or a
  few) per tenant. Versioned by integer so the operator can iterate
  without losing history.
- ``eval_cases`` — one row per (user_message + history + assertions).
- ``eval_runs`` — execution of a dataset against a specific
  agent_config version. Status machine: pending → running →
  passed|failed|error.
- ``eval_run_results`` — per-case outcome inside a run with the
  transcript JSON and the assertion breakdown.

All four tables have RLS + FORCE, mirroring the pattern from 0013.

The ``tenants.eval_required`` flag (default ``false``) opts the
tenant into the promotion gate: when true, ``promote_agent_config``
refuses to flip a version active without a passing recent run
(see services/agent_config.py — implemented in the same PR).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_RLS_POLICY_SQL = """
CREATE POLICY {table}_tenant_isolation ON {table}
USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
"""


def upgrade() -> None:
    # ── eval_datasets ───────────────────────────────────────────────────────
    op.create_table(
        "eval_datasets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        # Pass threshold (0.0..1.0). Run is "passed" if pass_rate >= this.
        sa.Column(
            "pass_threshold",
            sa.Numeric(4, 3),
            nullable=False,
            server_default="0.950",
        ),
        sa.Column(
            "archived_at",
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
        sa.UniqueConstraint(
            "tenant_id", "name", "version", name="uq_eval_datasets_tenant_name_version"
        ),
        sa.CheckConstraint(
            "pass_threshold >= 0 AND pass_threshold <= 1",
            name="ck_eval_datasets_pass_threshold",
        ),
    )
    op.create_index("ix_eval_datasets_tenant", "eval_datasets", ["tenant_id"])
    op.execute("ALTER TABLE eval_datasets ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE eval_datasets FORCE ROW LEVEL SECURITY")
    op.execute(_RLS_POLICY_SQL.format(table="eval_datasets"))

    # ── eval_cases ──────────────────────────────────────────────────────────
    op.create_table(
        "eval_cases",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "dataset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eval_datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("user_message", sa.Text(), nullable=False),
        sa.Column(
            "history",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "assertions",
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("dataset_id", "idx", name="uq_eval_cases_dataset_idx"),
    )
    op.create_index("ix_eval_cases_tenant", "eval_cases", ["tenant_id"])
    op.create_index("ix_eval_cases_dataset", "eval_cases", ["dataset_id"])
    op.execute("ALTER TABLE eval_cases ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE eval_cases FORCE ROW LEVEL SECURITY")
    op.execute(_RLS_POLICY_SQL.format(table="eval_cases"))

    # ── eval_runs ───────────────────────────────────────────────────────────
    op.create_table(
        "eval_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "dataset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eval_datasets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        # We snapshot the dataset version at run-time so subsequent edits
        # don't muddy the historical comparison.
        sa.Column("dataset_version", sa.Integer(), nullable=False),
        sa.Column("agent_config_version", sa.Integer(), nullable=False),
        sa.Column("agent_config_status", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("case_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pass_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fail_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "pass_rate",
            sa.Numeric(4, 3),
            nullable=False,
            server_default="0.000",
        ),
        sa.Column("actor", sa.String(255), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
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
            "status IN ('pending', 'running', 'passed', 'failed', 'error')",
            name="ck_eval_runs_status",
        ),
        sa.CheckConstraint(
            "pass_rate >= 0 AND pass_rate <= 1",
            name="ck_eval_runs_pass_rate",
        ),
    )
    op.create_index("ix_eval_runs_tenant", "eval_runs", ["tenant_id"])
    op.create_index(
        "ix_eval_runs_tenant_version",
        "eval_runs",
        ["tenant_id", "agent_config_version"],
    )
    op.create_index("ix_eval_runs_dataset", "eval_runs", ["dataset_id"])
    op.execute("ALTER TABLE eval_runs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE eval_runs FORCE ROW LEVEL SECURITY")
    op.execute(_RLS_POLICY_SQL.format(table="eval_runs"))

    # ── eval_run_results ────────────────────────────────────────────────────
    op.create_table(
        "eval_run_results",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eval_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eval_cases.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        # Case snapshot so deleting / editing the case doesn't invalidate
        # historical run reports.
        sa.Column("case_idx", sa.Integer(), nullable=False),
        sa.Column("case_name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "transcript",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "assertion_results",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('pass', 'fail', 'error')",
            name="ck_eval_run_results_status",
        ),
        sa.UniqueConstraint("run_id", "case_id", name="uq_eval_run_results_run_case"),
    )
    op.create_index(
        "ix_eval_run_results_tenant", "eval_run_results", ["tenant_id"]
    )
    op.create_index("ix_eval_run_results_run", "eval_run_results", ["run_id"])
    op.execute("ALTER TABLE eval_run_results ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE eval_run_results FORCE ROW LEVEL SECURITY")
    op.execute(_RLS_POLICY_SQL.format(table="eval_run_results"))

    # ── tenants.eval_required ───────────────────────────────────────────────
    op.add_column(
        "tenants",
        sa.Column(
            "eval_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("tenants", "eval_required")

    op.execute("ALTER TABLE eval_run_results NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE eval_run_results DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS eval_run_results_tenant_isolation ON eval_run_results")
    op.drop_index("ix_eval_run_results_run", table_name="eval_run_results")
    op.drop_index("ix_eval_run_results_tenant", table_name="eval_run_results")
    op.drop_table("eval_run_results")

    op.execute("ALTER TABLE eval_runs NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE eval_runs DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS eval_runs_tenant_isolation ON eval_runs")
    op.drop_index("ix_eval_runs_dataset", table_name="eval_runs")
    op.drop_index("ix_eval_runs_tenant_version", table_name="eval_runs")
    op.drop_index("ix_eval_runs_tenant", table_name="eval_runs")
    op.drop_table("eval_runs")

    op.execute("ALTER TABLE eval_cases NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE eval_cases DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS eval_cases_tenant_isolation ON eval_cases")
    op.drop_index("ix_eval_cases_dataset", table_name="eval_cases")
    op.drop_index("ix_eval_cases_tenant", table_name="eval_cases")
    op.drop_table("eval_cases")

    op.execute("ALTER TABLE eval_datasets NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE eval_datasets DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS eval_datasets_tenant_isolation ON eval_datasets")
    op.drop_index("ix_eval_datasets_tenant", table_name="eval_datasets")
    op.drop_table("eval_datasets")
