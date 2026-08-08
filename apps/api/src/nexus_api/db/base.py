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


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    settings = get_settings()
    # WP-09: pool sizing is env-driven — the concurrent runner's sizing rule
    # is ``réplicas x (pool_size + max_overflow) < max_connections x 0.7``,
    # which can't hold with hardcoded numbers once replicas scale.
    return create_async_engine(
        settings.database_url,
        echo=False,
        # ``pool_pre_ping`` replaces a dead connection at checkout. But the
        # managed Postgres / proxy in front of it silently drops connections
        # that have been open a while, and a connection can die mid-use
        # (observed: "the connection is closed" / "SSL error: unexpected eof").
        # ``pool_recycle`` proactively discards connections older than this so
        # we never hand out one the proxy already killed. 280s stays under the
        # common ~300s idle cutoff. Transient errors that still slip through
        # are retried at the consumer boundary (see streams/consumer.py).
        pool_pre_ping=True,
        pool_recycle=280,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
    )


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_engine(),
        expire_on_commit=False,
        class_=AsyncSession,
    )


def reset_engine_cache() -> None:
    """Test helper. Drops cached engine + sessionmaker so a new DATABASE_URL is read."""
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


async def dispose_engine() -> None:
    """Cleanly close the engine on shutdown. Robust to test monkey-patching."""
    info = getattr(get_engine, "cache_info", None)
    if info is None:
        return
    if info().currsize == 0:
        return
    engine = get_engine()
    await engine.dispose()


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
