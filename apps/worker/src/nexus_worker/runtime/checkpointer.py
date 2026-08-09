"""LangGraph checkpointer factory.

Block C uses Postgres as the single source of truth (decision A in the block-C
plan). Redis stays in front for the inbound stream, the tenant-resolution
cache, and the agent-config promote pub/sub — adding a Redis caching layer in
front of checkpoints can land in block H if the latency numbers warrant it.

The Postgres saver writes its own tables (``checkpoints``,
``checkpoint_blobs``, ``checkpoint_writes``, ``checkpoint_migrations``).

WP-14: those tables now carry a real ``tenant_id`` column, derived and
VALIDATED by a database trigger from the ``thread_id`` prefix (migration
0065) — a malformed thread_id is rejected by Postgres itself, whatever code
produced it. Because LangGraph owns the tables (``setup()`` creates them),
``postgres_checkpointer`` re-applies the idempotent hardening right after
``setup()``: a fresh database where LangGraph creates the tables AFTER the
migrations still ends up hardened. The ``isolation_enforcer`` middleware in
the API only inspects SQL against the business tables, so the LangGraph
plumbing does not trip it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver


def to_psycopg_uri(sqlalchemy_uri: str) -> str:
    """Convert ``postgresql+asyncpg://...`` to the bare ``postgresql://...`` form
    psycopg expects. Other schemes are passed through unchanged."""
    if sqlalchemy_uri.startswith("postgresql+asyncpg://"):
        return "postgresql://" + sqlalchemy_uri[len("postgresql+asyncpg://") :]
    if sqlalchemy_uri.startswith("postgres+asyncpg://"):
        return "postgres://" + sqlalchemy_uri[len("postgres+asyncpg://") :]
    return sqlalchemy_uri


@asynccontextmanager
async def postgres_checkpointer(
    db_uri: str,
) -> AsyncIterator[BaseCheckpointSaver[Any]]:
    """Open an ``AsyncPostgresSaver`` and ensure its tables exist.

    Use as the long-lived context manager around the worker's main loop:

        async with postgres_checkpointer(uri) as saver:
            await run_consumer(saver)
    """
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    psycopg_uri = to_psycopg_uri(db_uri)
    async with AsyncPostgresSaver.from_conn_string(psycopg_uri) as saver:
        await saver.setup()
        await _harden_checkpoint_tables()
        yield saver


async def _harden_checkpoint_tables() -> None:
    """WP-14: ensure tenant_id column + derive/validate trigger exist on the
    saver's tables (idempotent — see migration 0065). Tolerates a database
    where the migration has not run yet (function missing): the hardening
    then happens when migrations catch up."""
    import sqlalchemy as sa
    import structlog
    from nexus_api.db.base import get_sessionmaker

    log = structlog.get_logger(__name__)
    try:
        sm = get_sessionmaker()
        async with sm() as session:
            await session.execute(sa.text("SELECT harden_checkpoint_tables()"))
            await session.commit()
        log.info("checkpointer.hardened")
    except Exception as exc:
        log.warning(
            "checkpointer.harden_skipped",
            error=str(exc),
            hint="run alembic migrations (0065) — checkpoint tables are "
            "unprotected until then",
        )


@asynccontextmanager
async def memory_checkpointer() -> AsyncIterator[BaseCheckpointSaver[Any]]:
    """In-memory checkpointer for tests. Same ``thread_id`` semantics, no DB."""
    from langgraph.checkpoint.memory import MemorySaver

    yield MemorySaver()
