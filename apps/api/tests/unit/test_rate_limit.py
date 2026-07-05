"""Unit tests for the per-partner token bucket (ADR-028)."""

from __future__ import annotations

import fakeredis.aioredis
import pytest

from nexus_api.core import rate_limit


@pytest.fixture
def redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


async def test_allows_up_to_capacity_then_rejects(redis) -> None:
    results = [await rate_limit.allow(redis, key="rl:t1", per_minute=3) for _ in range(4)]
    assert results == [True, True, True, False]


async def test_buckets_are_independent(redis) -> None:
    assert await rate_limit.allow(redis, key="rl:a", per_minute=1)
    assert not await rate_limit.allow(redis, key="rl:a", per_minute=1)
    # Partner B's bucket is untouched by A's exhaustion.
    assert await rate_limit.allow(redis, key="rl:b", per_minute=1)


async def test_zero_limit_rejects_without_redis(redis) -> None:
    assert not await rate_limit.allow(redis, key="rl:z", per_minute=0)


async def test_fail_open_on_redis_error() -> None:
    class BrokenRedis:
        async def time(self):
            raise ConnectionError("redis down")

    # Availability of the partner API wins over rate limiting when Redis
    # is out — the event is logged for alerting.
    assert await rate_limit.allow(BrokenRedis(), key="rl:x", per_minute=1)


def test_bucket_key_shapes() -> None:
    assert rate_limit.mint_bucket_key("p1") == "rl:partner:p1:mint"
    assert rate_limit.embed_bucket_key("p1") == "rl:partner:p1:embed"
