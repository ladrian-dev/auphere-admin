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

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver

# WP-14b — tenant activo para la operación en curso del saver. ContextVar
# (no atributo de instancia): el saver es un singleton compartido por los
# turnos concurrentes del runner (WP-09) y cada task de asyncio lleva el
# suyo.
_scoped_tenant: ContextVar[str | None] = ContextVar("checkpoint_scoped_tenant", default=None)

_THREAD_TENANT_RE = re.compile(
    r"^tenant:([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}):"
)


def to_psycopg_uri(sqlalchemy_uri: str) -> str:
    """Convert ``postgresql+asyncpg://...`` to the bare ``postgresql://...`` form
    psycopg expects. Other schemes are passed through unchanged."""
    if sqlalchemy_uri.startswith("postgresql+asyncpg://"):
        return "postgresql://" + sqlalchemy_uri[len("postgresql+asyncpg://") :]
    if sqlalchemy_uri.startswith("postgres+asyncpg://"):
        return "postgres://" + sqlalchemy_uri[len("postgres+asyncpg://") :]
    return sqlalchemy_uri


def tenant_from_thread_config(config: Any) -> str:
    """Extract the tenant uuid from ``config.configurable.thread_id``.

    Raises ``ValueError`` on a thread_id without the ``tenant:<uuid>:``
    prefix — the same contract migration 0065 enforces at the database
    level, applied here BEFORE any SQL runs.
    """
    thread_id = ((config or {}).get("configurable") or {}).get("thread_id") or ""
    match = _THREAD_TENANT_RE.match(thread_id)
    if match is None:
        raise ValueError(
            f"thread_id sin prefijo tenant:<uuid>: — {thread_id!r}. "
            "El TenantScopedPostgresSaver no opera sin tenant."
        )
    return match.group(1)


def build_tenant_scoped_saver_class() -> type:
    """WP-14b — subclass of ``AsyncPostgresSaver`` that activates RLS.

    Built lazily inside a function so importing this module never drags
    langgraph in (same lazy-import convention as the rest of the file).

    How it works: every read/write in the saver funnels through
    ``_cursor()`` (verified against langgraph's source — ``aget_tuple``,
    ``alist``, ``aput``, ``aput_writes``, ``adelete_thread`` all use it,
    serialized by ``self.lock``). The public methods stamp the tenant
    (derived from the thread_id prefix) into a ContextVar; ``_cursor``
    then wraps the operation with:

        set_config('app.tenant_id', <tenant>, false) + SET ROLE nexus_app
        ... operación ...
        RESET ROLE + set_config('app.tenant_id', '', false)

    Session-level ``set_config`` (not SET LOCAL) porque la conexión del
    saver es autocommit y las rutas con pipeline no garantizan una
    transacción envolvente; el lock del saver hace imposible que dos
    operaciones intercalen sus statements, y el finally SIEMPRE limpia.
    ``setup()`` y el hardening corren sin tenant (como owner) — la tabla
    de migraciones del saver no tiene RLS.
    """
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    class TenantScopedPostgresSaver(AsyncPostgresSaver):  # type: ignore[misc]
        @asynccontextmanager
        async def _cursor(self, *, pipeline: bool = False):  # type: ignore[override]
            tenant = _scoped_tenant.get()
            async with super()._cursor(pipeline=pipeline) as cur:
                if tenant is None:
                    yield cur
                    return
                await cur.execute("SELECT set_config('app.tenant_id', %s, false)", (tenant,))
                await cur.execute("SET ROLE nexus_app")
                try:
                    yield cur
                finally:
                    await cur.execute("RESET ROLE")
                    await cur.execute("SELECT set_config('app.tenant_id', '', false)")

        async def aget_tuple(self, config):  # type: ignore[override]
            token = _scoped_tenant.set(tenant_from_thread_config(config))
            try:
                return await super().aget_tuple(config)
            finally:
                _scoped_tenant.reset(token)

        async def alist(self, config, *, filter=None, before=None, limit=None):  # type: ignore[override]
            token = _scoped_tenant.set(tenant_from_thread_config(config))
            try:
                async for item in super().alist(config, filter=filter, before=before, limit=limit):
                    yield item
            finally:
                _scoped_tenant.reset(token)

        async def aput(self, config, checkpoint, metadata, new_versions):  # type: ignore[override]
            token = _scoped_tenant.set(tenant_from_thread_config(config))
            try:
                return await super().aput(config, checkpoint, metadata, new_versions)
            finally:
                _scoped_tenant.reset(token)

        async def aput_writes(self, config, writes, task_id, task_path=""):  # type: ignore[override]
            token = _scoped_tenant.set(tenant_from_thread_config(config))
            try:
                return await super().aput_writes(config, writes, task_id, task_path)
            finally:
                _scoped_tenant.reset(token)

        async def adelete_thread(self, thread_id):  # type: ignore[override]
            token = _scoped_tenant.set(
                tenant_from_thread_config({"configurable": {"thread_id": thread_id}})
            )
            try:
                return await super().adelete_thread(thread_id)
            finally:
                _scoped_tenant.reset(token)

    return TenantScopedPostgresSaver


@asynccontextmanager
async def postgres_checkpointer(
    db_uri: str,
) -> AsyncIterator[BaseCheckpointSaver[Any]]:
    """Open a tenant-scoped ``AsyncPostgresSaver`` and ensure its tables exist.

    Use as the long-lived context manager around the worker's main loop:

        async with postgres_checkpointer(uri) as saver:
            await run_consumer(saver)
    """
    from psycopg import AsyncConnection
    from psycopg.rows import dict_row

    psycopg_uri = to_psycopg_uri(db_uri)
    # WP-15: conexión construida a mano en vez de ``from_conn_string``,
    # que clava ``prepare_threshold=0`` (prepara todo statement desde la
    # primera ejecución). ``prepare_threshold=None`` desactiva los prepared
    # statements del lado servidor: obligatorio si la URI atraviesa un
    # pooler en modo transaction, e inofensivo en conexión directa (el
    # saver mantiene UNA conexión larga por réplica del runner — el ahorro
    # de un prepared statement aquí es ruido).
    saver_cls = build_tenant_scoped_saver_class()
    async with await AsyncConnection.connect(
        psycopg_uri,
        autocommit=True,
        prepare_threshold=None,
        row_factory=dict_row,
    ) as conn:
        saver = saver_cls(conn=conn)
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
            hint="run alembic migrations (0065) — checkpoint tables are unprotected until then",
        )


@asynccontextmanager
async def memory_checkpointer() -> AsyncIterator[BaseCheckpointSaver[Any]]:
    """In-memory checkpointer for tests. Same ``thread_id`` semantics, no DB."""
    from langgraph.checkpoint.memory import MemorySaver

    yield MemorySaver()
