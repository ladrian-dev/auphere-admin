"""Tenant resolver — (provider, identifier) → tenant_id, with Redis cache.

Spec: architecture/channel-adapters.md "Resolución de tenant en el webhook".

Implementation:
- Cache hit: return UUID immediately.
- Cache miss: call Postgres function `resolve_channel_tenant(provider, identifier)`
  defined in migration 0002. The function is SECURITY DEFINER + `SET row_security
  = off`, so it can read `channels` across tenants without weakening RLS for the
  rest of the application.
- Not found: raise `TenantNotFound`. The webhook entry-point translates this to
  HTTP 200 + structured log + `channel.unresolved_event` metric (fail-closed:
  no tenant, no processing).
"""

from __future__ import annotations

import uuid

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.config import get_settings
from nexus_api.core.errors import TenantNotFound


def _cache_key(provider: str, identifier: str) -> str:
    return f"nexus:tenant_resolve:{provider}:{identifier}"


async def resolve_tenant(
    session: AsyncSession,
    redis: Redis,
    provider: str,
    identifier: str,
) -> uuid.UUID:
    settings = get_settings()
    redis_key = _cache_key(provider, identifier)

    cached = await redis.get(redis_key)
    if cached:
        try:
            return uuid.UUID(cached)
        except ValueError:
            await redis.delete(redis_key)

    result = await session.execute(
        text("SELECT resolve_channel_tenant(:p, :i)"),
        {"p": provider, "i": identifier},
    )
    tenant_id = result.scalar_one_or_none()
    if tenant_id is None:
        raise TenantNotFound(f"No active channel for provider={provider} identifier={identifier}")
    if isinstance(tenant_id, str):
        tenant_id = uuid.UUID(tenant_id)

    await redis.setex(redis_key, settings.tenant_cache_ttl, str(tenant_id))
    return tenant_id


async def invalidate_tenant_cache(redis: Redis, provider: str, identifier: str) -> None:
    await redis.delete(_cache_key(provider, identifier))
