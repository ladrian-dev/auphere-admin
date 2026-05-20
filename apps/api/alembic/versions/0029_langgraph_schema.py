"""``langgraph`` schema for AsyncPostgresSaver checkpointing (ADR-021, Fase 1).

Revision ID: 0029
Revises: 0028
Create Date: 2026-05-20

The QA Playground runtime invokes the agent graph in-process and uses
``langgraph.checkpoint.postgres.aio.AsyncPostgresSaver`` to persist
LangGraph checkpoints across server restarts. The saver creates its
own tables (``checkpoints``, ``checkpoint_writes``, ``checkpoint_blobs``,
``checkpoint_migrations``) at first ``setup()`` call.

We don't want those tables in ``public`` (mixes with our domain schema
and makes the schema list confusing). We can't put them under ``qa.*``
either — the LangGraph saver assumes the default search path. The
cleanest split is a dedicated ``langgraph`` schema that the saver
treats as its own.

What this migration does:
  - Create the ``langgraph`` schema if it doesn't exist.
  - Grant USAGE + full CRUD to ``nexus_app`` (the role our request
    sessions switch to). The saver runs OUTSIDE the RLS-scoped tx (it
    opens its own asyncpg connection), so the GRANT is what matters,
    not RLS.
  - Set the default privileges so any table the saver creates inside
    this schema gets the same grants automatically.

What this migration does NOT do:
  - Create the saver's tables. ``AsyncPostgresSaver.setup()`` is the
    canonical way to create them and Alembic shouldn't fight that.
    The nexus-api startup hook (see ``main.py`` lifespan) calls
    ``setup()`` exactly once per process; idempotent.
  - Enable RLS on the saver tables. The saver runs under the
    application's superuser connection (it needs DDL during setup),
    and the checkpoint data is keyed by ``thread_id`` which is itself
    the qa.threads.id — RLS at the saver level would conflict with the
    saver's transactional contract. Isolation is enforced upstream by
    qa.threads/qa.runs RLS: an operator can never reach a thread_id
    that isn't theirs, so they can never request a checkpoint that
    isn't theirs either.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0029"
down_revision: str | Sequence[str] | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS langgraph")
    op.execute("GRANT USAGE, CREATE ON SCHEMA langgraph TO nexus_app")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES "
        "IN SCHEMA langgraph TO nexus_app"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA langgraph "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO nexus_app"
    )


def downgrade() -> None:
    # Drop the schema with CASCADE so the saver's tables (created by
    # setup() at runtime) come down with it. Safe because in dev/test
    # we tear down everything together; in prod the migration is
    # forward-only by policy anyway.
    op.execute("DROP SCHEMA IF EXISTS langgraph CASCADE")
