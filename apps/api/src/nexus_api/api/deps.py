"""Reusable FastAPI dependencies."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, Path, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core import redis_client
from nexus_api.core.logging_context import bind_tenant
from nexus_api.db.base import get_ro_sessionmaker, get_sessionmaker
from nexus_api.repositories import TenantRepository


async def get_db_session() -> AsyncIterator[AsyncSession]:
    factory = get_sessionmaker()
    async with factory() as session:
        yield session


def get_redis() -> Redis:
    # Dereference dynamically so test fixtures that
    # ``monkeypatch.setattr(redis_client, "get_redis", ...)`` take effect.
    # An ``import X as Y`` here would bind to the function object at import
    # time and bypass the monkey-patch (latent bug fixed in Block L).
    return redis_client.get_redis()


async def _tenant_scoped(
    tenant_id: uuid.UUID,
    session: AsyncSession,
) -> AsyncIterator[AsyncSession]:
    """Shared body of the tenant-scoped session dependencies.

    Flow:
      1. Open the transaction (autobegin).
      2. Resolve the tenant via the global TenantRepository (no RLS on tenants).
      3. If not found → 404.
      4. Apply `set_config('app.tenant_id', ..., true)` so subsequent queries
         hit RLS-protected tables under the right scope.
      5. Bind tenant_id to structlog context.
      6. Yield. The endpoint runs inside this transaction; on clean return
         we commit, on exception we roll back.
    """
    from nexus_api.core.tenant_context import (
        _current_tenant,
        apply_tenant_to_session,
    )

    token = _current_tenant.set(tenant_id)
    try:
        async with session.begin():
            tenant = await TenantRepository(session).get(tenant_id)
            if tenant is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"tenant {tenant_id} not found",
                )
            await apply_tenant_to_session(session, tenant_id)
            bind_tenant(tenant_id)
            yield session
    finally:
        _current_tenant.reset(token)


async def scoped_session_from_path(
    tenant_id: uuid.UUID = Path(..., description="Tenant UUID"),
    session: AsyncSession = Depends(get_db_session),
) -> AsyncIterator[AsyncSession]:
    """Tenant-scoped session against the primary (read-write)."""
    async for scoped in _tenant_scoped(tenant_id, session):
        yield scoped


async def get_ro_db_session() -> AsyncIterator[AsyncSession]:
    """WP-15: session against the read replica (falls back to primary when
    ``NEXUS_DATABASE_URL_RO`` is unset)."""
    factory = get_ro_sessionmaker()
    async with factory() as session:
        yield session


async def ro_scoped_session_from_path(
    tenant_id: uuid.UUID = Path(..., description="Tenant UUID"),
    session: AsyncSession = Depends(get_ro_db_session),
) -> AsyncIterator[AsyncSession]:
    """WP-15: tenant-scoped session against the read replica.

    Same RLS flow as :func:`scoped_session_from_path` — ``set_config`` is a
    session-local function and works on hot standbys. ONLY for endpoints
    that never write: an INSERT/UPDATE through this session fails on a real
    replica with ``cannot execute ... in a read-only transaction`` (which is
    exactly the guard we want — in dev/staging without replica the fallback
    engine hides it, the isolation suite covers the routing instead).
    """
    async for scoped in _tenant_scoped(tenant_id, session):
        yield scoped
