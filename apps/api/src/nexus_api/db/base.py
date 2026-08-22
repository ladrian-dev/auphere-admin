"""SQLAlchemy 2.0 async engine, session factory, and declarative base.

The engine is built lazily so that tests can override `NEXUS_DATABASE_URL` before the
first import. Configuration goes through `nexus_api.config.get_settings()` which is
LRU-cached but re-readable in tests via `get_settings.cache_clear()`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from nexus_api.config import get_settings


class Base(DeclarativeBase):
    """Project-wide declarative base. All ORM models inherit from this."""


def _pooling_connect_args() -> dict[str, Any]:
    """WP-15: asyncpg args required behind a transaction-mode pooler.

    PgBouncer in transaction mode multiplexes one server connection across
    many client transactions, so server-side prepared statements leak
    between clients: a statement prepared on one client's turn may not
    exist (or belong to someone else) on the next. Two changes fix it:

    - ``statement_cache_size=0`` — asyncpg never re-uses prepared
      statements across calls.
    - ``prepared_statement_name_func`` — the *implicit* statements asyncpg
      still creates for each execute get a unique name, so two clients
      sharing a server connection can never collide on ``__asyncpg_stmt_N``.
    """
    from uuid import uuid4

    return {
        "statement_cache_size": 0,
        "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4().hex}__",
    }


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    settings = get_settings()
    # WP-09: pool sizing is env-driven — the concurrent runner's sizing rule
    # is ``réplicas x (pool_size + max_overflow) < max_connections x 0.7``,
    # which can't hold with hardcoded numbers once replicas scale.
    # WP-15: with ``db_transaction_pooling`` the ceiling that matters becomes
    # the pooler's, and the connect_args disable prepared-statement re-use.
    return create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
        pool_recycle=280,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        connect_args=_pooling_connect_args() if settings.db_transaction_pooling else {},
    )


@lru_cache(maxsize=1)
def get_ro_engine() -> AsyncEngine:
    """WP-15: engine against the read replica (``NEXUS_DATABASE_URL_RO``).

    Falls back to the primary URL when unset, so code routed to the RO
    engine keeps working in dev/tests and in environments without replica
    (staging runs a single Aurora instance).
    """
    settings = get_settings()
    url = settings.database_url_ro or settings.database_url
    return create_async_engine(
        url,
        echo=False,
        pool_pre_ping=True,
        pool_recycle=280,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        connect_args=_pooling_connect_args() if settings.db_transaction_pooling else {},
    )


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_engine(),
        expire_on_commit=False,
        class_=AsyncSession,
    )


@lru_cache(maxsize=1)
def get_ro_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_ro_engine(),
        expire_on_commit=False,
        class_=AsyncSession,
    )


def reset_engine_cache() -> None:
    """Test helper. Drops cached engines + sessionmakers so a new DATABASE_URL is read."""
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    get_ro_engine.cache_clear()
    get_ro_sessionmaker.cache_clear()


async def dispose_engine() -> None:
    """Cleanly close the engines on shutdown. Robust to test monkey-patching."""
    for cached in (get_engine, get_ro_engine):
        info = getattr(cached, "cache_info", None)
        if info is None or info().currsize == 0:
            continue
        await cached().dispose()


async def yield_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yield an unscoped session.

    Most admin endpoints should use `tenant_scoped_session` instead. This dependency is
    only for endpoints that legitimately operate across tenants (e.g. the global
    `tool_catalog` listing) or that resolve the tenant themselves before scoping.
    """
    factory = get_sessionmaker()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()


def kwargs_for_jsonb(default: Any) -> dict[str, Any]:
    """Helper used by some models to set a JSONB default."""
    return {"default": default, "server_default": None}
