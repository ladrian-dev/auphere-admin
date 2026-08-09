"""tenant_id on the LangGraph checkpoint tables (WP-14, plataforma v2).

Removes the last convention-only isolation boundary: conversational state
was scoped purely by the ``thread_id`` STRING format. With workflows and
MCP widening the write surface, the state tables get a real ``tenant_id``
column, derived and VALIDATED by a BEFORE trigger — a thread_id whose
prefix is not ``tenant:<uuid>:`` is rejected at the database, no matter
what code produced it. ``AsyncPostgresSaver`` needs no SQL changes.

Shape note: LangGraph owns these tables — ``saver.setup()`` creates them at
worker boot (repo pattern set by migration 0029). Everything here lives in
``harden_checkpoint_tables()``, an idempotent function that skips missing
tables; this migration calls it (covers databases where the tables exist)
and the worker's checkpointer calls it again right after ``setup()``
(covers fresh databases where LangGraph creates the tables later).

RLS on these tables (plan's next step) deliberately ships SEPARATELY once
the ``TenantScopedPostgresSaver`` wrapper is proven: enabling FORCE RLS
without the wrapper would blank every read from the saver. The trigger is
the defense that does not depend on LangGraph internals, so it goes first.

Revision ID: 0065_checkpoint_tenant_id
Revises: 0064_partition_helpers
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0065_checkpoint_tenant_id"
down_revision: str | Sequence[str] | None = "0064_partition_helpers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_THREAD_PATTERN = (
    "^tenant:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}:"
)


def upgrade() -> None:
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION checkpoint_derive_tenant() RETURNS trigger AS $$
        BEGIN
            IF NEW.thread_id IS NULL
               OR NEW.thread_id !~ '{_THREAD_PATTERN}' THEN
                RAISE EXCEPTION
                    'checkpoint thread_id must start with tenant:<uuid>: (got %)',
                    NEW.thread_id;
            END IF;
            NEW.tenant_id := substring(NEW.thread_id from 8 for 36)::uuid;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION harden_checkpoint_tables() RETURNS void AS $$
        DECLARE
            t text;
        BEGIN
            FOREACH t IN ARRAY
                ARRAY['checkpoints', 'checkpoint_blobs', 'checkpoint_writes']
            LOOP
                IF to_regclass('public.' || t) IS NULL THEN
                    CONTINUE;  -- LangGraph has not created this table yet
                END IF;
                EXECUTE format(
                    'ALTER TABLE %I ADD COLUMN IF NOT EXISTS tenant_id uuid', t
                );
                EXECUTE format(
                    'UPDATE %I SET tenant_id = substring(thread_id from 8 for 36)::uuid '
                    'WHERE tenant_id IS NULL AND thread_id ~ %L',
                    t, '{_THREAD_PATTERN}'
                );
                EXECUTE format(
                    'CREATE INDEX IF NOT EXISTS ix_%s_tenant_thread '
                    'ON %I (tenant_id, thread_id)',
                    t, t
                );
                EXECUTE format('DROP TRIGGER IF EXISTS trg_%s_tenant ON %I', t, t);
                EXECUTE format(
                    'CREATE TRIGGER trg_%s_tenant BEFORE INSERT OR UPDATE ON %I '
                    'FOR EACH ROW EXECUTE FUNCTION checkpoint_derive_tenant()',
                    t, t
                );
            END LOOP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute("SELECT harden_checkpoint_tables()")


def downgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE
            t text;
        BEGIN
            FOREACH t IN ARRAY
                ARRAY['checkpoints', 'checkpoint_blobs', 'checkpoint_writes']
            LOOP
                IF to_regclass('public.' || t) IS NULL THEN
                    CONTINUE;
                END IF;
                EXECUTE format('DROP TRIGGER IF EXISTS trg_%s_tenant ON %I', t, t);
                EXECUTE format('DROP INDEX IF EXISTS ix_%s_tenant_thread', t);
                EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS tenant_id', t);
            END LOOP;
        END;
        $$;
        """
    )
    op.execute("DROP FUNCTION IF EXISTS harden_checkpoint_tables()")
    op.execute("DROP FUNCTION IF EXISTS checkpoint_derive_tenant()")
