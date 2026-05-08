"""Subscriber that invalidates the AgentLoader cache when a tenant promotes a
new ``agent_config`` version.

The promote endpoint emits ``PUBLISH nexus:agent_config:promote <tenant_id>``
after the DB commit. This task listens on that channel and calls
``AgentLoader.invalidate``. Garantía 5 leans on this — without invalidation,
a promoted prompt would not reach the running worker until restart, which is
the explicit non-goal of the no-redeploy story.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid

import structlog
from redis.asyncio import Redis

from nexus_worker.runtime.agent_loader import AgentLoader

log = structlog.get_logger(__name__)


PROMOTE_CHANNEL = "nexus:agent_config:promote"


async def run_promote_subscriber(
    redis: Redis,
    loader: AgentLoader,
    *,
    channel: str = PROMOTE_CHANNEL,
    stop: asyncio.Event | None = None,
) -> None:
    """Subscribe and invalidate until ``stop`` is set (or task is cancelled).

    Each message body is the affected ``tenant_id`` as a UUID string. Anything
    else is logged and ignored — the cache will eventually be refreshed on
    the next miss anyway, so a malformed message is at worst a stale read,
    not a correctness break.
    """
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)
    try:
        while stop is None or not stop.is_set():
            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0),
                    timeout=1.5,
                )
            except TimeoutError:
                continue
            if message is None:
                continue
            data = message.get("data")
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            if not isinstance(data, str):
                log.warning("promote_subscriber.unexpected_payload", payload=str(data))
                continue
            try:
                tenant_id = uuid.UUID(data.strip())
            except ValueError:
                log.warning("promote_subscriber.invalid_uuid", payload=data)
                continue
            await loader.invalidate(tenant_id)
    finally:
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(channel)
        with contextlib.suppress(Exception):
            await pubsub.aclose()  # type: ignore[no-untyped-call]


async def publish_promote(
    redis: Redis, tenant_id: uuid.UUID, *, channel: str = PROMOTE_CHANNEL
) -> None:
    await redis.publish(channel, str(tenant_id))
