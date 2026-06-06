"""Redis client provider. Lazily instantiated, override-friendly for tests."""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from redis.asyncio import Redis

from nexus_api.config import get_settings

# Must exceed the longest XREADGROUP ``block`` any stream consumer uses
# (currently 5s in the inbound + owner-fanout consumers). A socket read
# timeout SHORTER than the BLOCK makes every blocking read raise
# "Timeout reading from host:port" — which is exactly what broke the Railway
# worker: its REDIS_URL injected a short ``socket_timeout`` via querystring,
# and in redis-py ``from_url`` the querystring always wins over kwargs. We
# strip that param from the URL and set a generous timeout here instead.
# Keep this comfortably above any consumer's block value.
_SOCKET_TIMEOUT_SECONDS = 30.0
_SOCKET_CONNECT_TIMEOUT_SECONDS = 10.0
_HEALTH_CHECK_INTERVAL_SECONDS = 30


def _sanitize_redis_url(url: str) -> str:
    """Drop a ``socket_timeout`` querystring param so our kwarg value (which
    must exceed the consumers' BLOCK) is the one that takes effect. In
    redis-py ``from_url`` the querystring always wins over kwargs, so a short
    ``socket_timeout`` baked into a managed ``REDIS_URL`` (e.g. Railway) would
    otherwise make every blocking stream read time out."""
    parts = urlsplit(url)
    if not parts.query:
        return url
    kept = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k != "socket_timeout"
    ]
    return urlunsplit(parts._replace(query=urlencode(kept)))


@lru_cache(maxsize=1)
def get_redis() -> Redis:
    settings = get_settings()
    return Redis.from_url(
        _sanitize_redis_url(settings.redis_url),
        decode_responses=True,
        socket_timeout=_SOCKET_TIMEOUT_SECONDS,
        socket_connect_timeout=_SOCKET_CONNECT_TIMEOUT_SECONDS,
        socket_keepalive=True,
        health_check_interval=_HEALTH_CHECK_INTERVAL_SECONDS,
    )


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
