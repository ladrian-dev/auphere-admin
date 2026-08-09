"""ensure_month_partition() — reusable partition maintenance (WP-13).

One SQL function creates a month's partition for any RANGE(created_at/
occurred_at)-partitioned parent, idempotently. The scheduler's
``partition-maintenance-cron`` calls it for the current and next month on
every tick, so a partition can never be missing when a month rolls over
(the DEFAULT partition catches stragglers even if the cron were down).
``usage_records`` (WP-16) reuses the same function.

Revision ID: 0064_partition_helpers
Revises: 0063_messages_partitioned
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0064_partition_helpers"
down_revision: str | Sequence[str] | None = "0063_messages_partitioned"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION ensure_month_partition(parent text, month date)
        RETURNS text AS $$
        DECLARE
            start_d date := date_trunc('month', month)::date;
            end_d   date := (date_trunc('month', month) + interval '1 month')::date;
            part_name text := format(
                '%s_y%sm%s', parent, to_char(start_d, 'YYYY'), to_char(start_d, 'MM')
            );
        BEGIN
            IF NOT EXISTS (
                SELECT FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relname = part_name AND n.nspname = 'public'
            ) THEN
                EXECUTE format(
                    'CREATE TABLE %I PARTITION OF %I FOR VALUES FROM (%L) TO (%L)',
                    part_name, parent, start_d, end_d
                );
            END IF;
            RETURN part_name;
        END;
        $$ LANGUAGE plpgsql;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS ensure_month_partition(text, date)")
