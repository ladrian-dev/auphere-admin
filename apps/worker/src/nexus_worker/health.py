"""Worker heartbeat (WP-03, plataforma v2 Fase 0).

Each worker entrypoint runs ``run_heartbeat`` as a background task. It writes
``nexus:health:{service}:{instance}`` with ``SETEX 60`` every 20 seconds; the
API's ``/health/workers`` reads those keys and reports any expected service
with no live heartbeat. A TTL of 3x the interval tolerates two missed beats
(GC pause, Redis blip) before the service reads as down.

The loop never raises — a heartbeat that kills its worker would invert the
purpose of the whole thing.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import socket

import structlog
from redis.asyncio import Redis

log = structlog.get_logger(__name__)

HEARTBEAT_KEY_PREFIX = "nexus:health:"
HEARTBEAT_TTL_S = 60
HEARTBEAT_INTERVAL_S = 20.0


def instance_name() -> str:
    """Stable per-process identity: hostname + pid covers both containers
    (unique hostname) and local dev (several processes, one hostname)."""
    return f"{socket.gethostname()}-{os.getpid()}"


async def run_heartbeat(
    redis: Redis,
    *,
    service: str,
    stop: asyncio.Event | None = None,
    interval_s: float = HEARTBEAT_INTERVAL_S,
) -> None:
    key = f"{HEARTBEAT_KEY_PREFIX}{service}:{instance_name()}"
    log.info("heartbeat.start", service=service, key=key)
    while stop is None or not stop.is_set():
        try:
            await redis.setex(key, HEARTBEAT_TTL_S, "1")
        except Exception as exc:
            log.warning("heartbeat.write_failed", service=service, error=str(exc))
        if stop is None:
            await asyncio.sleep(interval_s)
        else:
            # Wake immediately on stop instead of sleeping out the interval.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=interval_s)
    # Best-effort cleanup so a graceful shutdown reads as "gone" right away
    # instead of lingering for the TTL.
    with contextlib.suppress(Exception):  # pragma: no cover - cleanup only
        await redis.delete(key)
    log.info("heartbeat.stopped", service=service)
