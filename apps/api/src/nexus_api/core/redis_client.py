"""Redis client provider. Lazily instantiated, override-friendly for tests."""

from __future__ import annotations

from functools import lru_cache

from redis.asyncio import Redis

from nexus_api.config import get_settings


@lru_cache(maxsize=1)
def get_redis() -> Redis:
    settings = get_settings()
    return Redis.from_url(settings.redis_url, decode_responses=True)


def reset_redis_cache() -> None:
    cache_clear = getattr(get_redis, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()


async def close_redis() -> None:
    """Close the cached Redis client. Safe to call when tests have monkey-patched
    `get_redis` with a non-LRU function."""
    info = getattr(get_redis, "cache_info", None)
    if info is None:
        return
    if info().currsize == 0:
        return
    await get_redis().aclose()
