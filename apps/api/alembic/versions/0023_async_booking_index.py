"""async booking — composite index on scheduled_jobs cron query

Revision ID: 0023
Revises: 0022
Create Date: 2026-05-13

Originally this was a partial index ``WHERE kind = 'async_booking'``
but Postgres rejects referencing a new enum value in the same DDL
transaction it was added — and Alembic wraps the whole upgrade chain
in a single tx (``env.py`` calls ``context.begin_transaction()``).

The async booking cron's hot query is:

    SELECT ... FROM scheduled_jobs
    WHERE kind = $1 AND status = $2 AND run_at <= $3
    ORDER BY run_at ASC
    LIMIT 5 FOR UPDATE SKIP LOCKED

A composite (kind, status, run_at) index covers that exactly, no
partial filter needed. Marginally larger on disk than the partial,
but predicate-free → no enum reference → works in a single tx with
the ALTER TYPE that introduced the new value. Net win: simpler +
serves both async_booking and any future kind the cron pattern uses.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0023"
down_revision: str | Sequence[str] | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_scheduled_jobs_kind_status_run_at",
        "scheduled_jobs",
        ["kind", "status", "run_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scheduled_jobs_kind_status_run_at", table_name="scheduled_jobs"
    )
