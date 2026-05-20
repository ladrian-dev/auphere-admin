"""qa.runs — per-turn run state for the streaming Playground (ADR-021, Fase 1).

Revision ID: 0028
Revises: 0027
Create Date: 2026-05-20

Adds ``qa.runs`` so the Playground can dispatch the agent graph
asynchronously (POST returns ``{run_id}`` quickly, frontend opens a
separate SSE stream against that run_id). Each row tracks one
operator → agent turn: status, timings, error, cost. The streaming
endpoint reads/writes here; cancel marks the row; resumability reads
the row to know whether the run still needs more events.

Schema:
  - id              UUID PK
  - thread_id       FK qa.threads(id) ON DELETE CASCADE
  - operator_id     TEXT (≤120, opaque Better Auth id — matches
                    qa.threads.operator_id per migration 0026)
  - status          TEXT CHECK IN ('running','completed','cancelled','error')
  - started_at      TIMESTAMPTZ default now()
  - ended_at        TIMESTAMPTZ
  - error           TEXT (status='error' carries the reason)
  - input_tokens    INT
  - output_tokens   INT
  - cost_usd        NUMERIC(10,6)
  - langfuse_trace_id  TEXT (for the Trace tab of the Inspector)

RLS by operator_id (same fail-closed pattern as migrations 0025/0026):
the policy compares operator_id to the GUC ``app.operator_id``, NULLIF
on empty string. nexus_app is granted CRUD.

Indexes:
  - (thread_id, started_at DESC)   — list runs of a thread, newest first
  - partial on status='running'     — find live runs cheaply for cleanup
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028"
down_revision: str | Sequence[str] | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "thread_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("qa.threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("operator_id", sa.String(length=120), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'running'"),
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("langfuse_trace_id", sa.String(length=120), nullable=True),
        sa.CheckConstraint(
            "status IN ('running','completed','cancelled','error')",
            name="ck_qa_runs_status",
        ),
        sa.CheckConstraint(
            "length(operator_id) <= 120 AND length(operator_id) > 0",
            name="ck_qa_runs_operator_bounded",
        ),
        schema="qa",
    )
    op.create_index(
        "ix_qa_runs_thread_started",
        "runs",
        ["thread_id", sa.text("started_at DESC")],
        schema="qa",
    )
    op.create_index(
        "ix_qa_runs_status_running",
        "runs",
        ["status"],
        schema="qa",
        postgresql_where=sa.text("status = 'running'"),
    )

    # RLS — same fail-closed pattern as qa.threads after 0026.
    op.execute("ALTER TABLE qa.runs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE qa.runs FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY qa_runs_operator_isolation ON qa.runs
        USING (
            operator_id = NULLIF(current_setting('app.operator_id', true), '')
        )
        WITH CHECK (
            operator_id = NULLIF(current_setting('app.operator_id', true), '')
        )
        """
    )

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON qa.runs TO nexus_app")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS qa_runs_operator_isolation ON qa.runs")
    op.execute("ALTER TABLE IF EXISTS qa.runs NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE IF EXISTS qa.runs DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_qa_runs_status_running", "runs", schema="qa")
    op.drop_index("ix_qa_runs_thread_started", "runs", schema="qa")
    op.drop_table("runs", schema="qa")
