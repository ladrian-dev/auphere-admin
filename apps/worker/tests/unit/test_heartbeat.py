"""WP-03: worker heartbeat contract — key shape, TTL, resilience, cleanup."""

from __future__ import annotations

import asyncio

import pytest
from fakeredis import aioredis as fakeaioredis

from nexus_worker import health

pytestmark = pytest.mark.asyncio


async def test_heartbeat_writes_key_with_ttl() -> None:
    redis = fakeaioredis.FakeRedis()
    stop = asyncio.Event()
    task = asyncio.create_task(
        health.run_heartbeat(redis, service="nexus-worker", stop=stop, interval_s=0.05)
    )
    await asyncio.sleep(0.02)

    keys = await redis.keys("nexus:health:nexus-worker:*")
    assert len(keys) == 1
    ttl = await redis.ttl(keys[0])
    assert 0 < ttl <= health.HEARTBEAT_TTL_S

    stop.set()
    await asyncio.wait_for(task, timeout=2.0)
    # Graceful shutdown removes the key so the service reads as gone at once.
    assert await redis.keys("nexus:health:nexus-worker:*") == []


async def test_heartbeat_survives_redis_failure() -> None:
    class _Boom:
        async def setex(self, *a, **k):
            raise ConnectionError("redis down")

        async def delete(self, *a, **k):
            raise ConnectionError("redis down")

    stop = asyncio.Event()
    task = asyncio.create_task(
        health.run_heartbeat(_Boom(), service="nexus-worker", stop=stop, interval_s=0.05)
    )
    await asyncio.sleep(0.12)  # let it fail a few beats
    stop.set()
    # Must exit cleanly despite every write failing.
    await asyncio.wait_for(task, timeout=2.0)
