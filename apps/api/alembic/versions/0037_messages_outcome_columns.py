"""messages.outcome_* columns — surface the grade_outcome verdict per turn

Revision ID: 0037
Revises: 0036
Create Date: 2026-05-24

The outcome grader (Fase C, ADR-023) runs after every handler and
produces a per-turn verdict: ``pass`` / ``fail`` / ``skipped`` / ``error``,
how many retries were spent on the rewrite loop, and the last feedback
string from the rubric. The verdict travels through ``AgentState`` and
the pipeline acts on it (rewrite, then ship), but nothing currently
persists it next to the outbound row — so the operator panel can't show
"this turn passed the grader on retry 2 / feedback: lacked tool result".

This migration adds three nullable columns on ``messages``:

- ``outcome_overall`` (varchar[20]) — verdict literal.
- ``outcome_retries`` (integer)    — count of rewrites before the
  verdict landed; 0 on first-try pass.
- ``outcome_feedback`` (text)      — last feedback from the rubric
  when the verdict was non-pass; empty / NULL otherwise.

All three are nullable + have no default: existing rows (Vedhome,
Barber Supply, pilots) stay NULL and the UI shows no badge for them —
back-compat. The checkpoint node sets them on every NEW outbound row.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0037"
down_revision: str | Sequence[str] | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("outcome_overall", sa.String(20), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("outcome_retries", sa.Integer(), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("outcome_feedback", sa.Text(), nullable=True),
    )
    # No index — the operator panel reads by conversation_id which is
    # already indexed; aggregate "fail rate per tenant" reports go
    # through Langfuse, not Postgres.


def downgrade() -> None:
    op.drop_column("messages", "outcome_feedback")
    op.drop_column("messages", "outcome_retries")
    op.drop_column("messages", "outcome_overall")
