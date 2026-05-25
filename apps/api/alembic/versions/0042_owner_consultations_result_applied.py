"""owner_consultations.result_applied_at + sweep index

Revision ID: 0042
Revises: 0041
Create Date: 2026-05-25

Phase 2 backchannel — Redis ``nexus:owner_fanout`` stream durability.

Phase 1 enqueued every owner answer onto the Redis stream and relied
on AOF/RDB for durability. If an entry is lost (worker crash mid-ack,
Redis restart with stale AOF, consumer-group rebalance edge cases) the
underlying ``owner_consultations`` row is already
``status='answered'`` so the data isn't lost — but the downstream
fanout (which re-invokes the agent pipeline with the owner's reply
in scope) never runs, and the customer never sees the agent's
follow-up.

This migration adds the bookkeeping the sweep cron uses to detect
"answered but never applied" rows:

- ``result_applied_at`` (DateTime, nullable) — set by the fanout
  consumer once the pipeline run completed successfully. Rows where
  this is NULL past a small window are candidates for re-enqueue.
- Partial index on ``(status, owner_response_at)`` WHERE
  ``result_applied_at IS NULL`` — keeps the sweep scan cheap as the
  log grows.

Existing rows stay NULL — the sweep treats them as legacy candidates
but its time-window filter excludes anything where ``owner_response_at``
is far in the past, so we don't replay year-old consultations.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0042"
down_revision: str | Sequence[str] | None = "0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "owner_consultations",
        sa.Column(
            "result_applied_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_owner_consultations_sweep",
        "owner_consultations",
        ["status", "owner_response_at"],
        postgresql_where=sa.text("result_applied_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_owner_consultations_sweep", table_name="owner_consultations")
    op.drop_column("owner_consultations", "result_applied_at")
