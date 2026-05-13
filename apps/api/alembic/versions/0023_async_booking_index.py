"""async booking — partial index that references the new enum value

Revision ID: 0023
Revises: 0022
Create Date: 2026-05-13

Migration 0022 added ``'async_booking'`` to ``scheduled_job_kind`` but
could NOT use the value in the same transaction (Postgres enum rule:
"new enum values must be committed before they can be used"). The
partial index lives here, on its own migration, so by the time it runs
the enum value is durably committed.

The index is what keeps the async_booking cron's
``SELECT ... FOR UPDATE SKIP LOCKED`` cheap as the ``scheduled_jobs``
table grows.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0023"
down_revision: str | Sequence[str] | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_scheduled_jobs_async_booking_pending",
        "scheduled_jobs",
        ["run_at"],
        postgresql_where=sa.text(
            "kind = 'async_booking' AND status = 'pending'"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scheduled_jobs_async_booking_pending", table_name="scheduled_jobs"
    )
