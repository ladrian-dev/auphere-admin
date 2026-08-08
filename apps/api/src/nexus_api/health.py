"""Health endpoints (WP-03, plataforma v2 Fase 0).

``/health/live`` stays constant — it answers "is the process up", nothing
else, so a dependency outage never makes the orchestrator restart-loop the
API. ``/health/ready`` is the routing gate: it verifies Postgres and Redis
with a hard timeout and returns 503 naming the failed dependency, so a
deploy with broken wiring never receives traffic.

``/health/workers`` surfaces the worker heartbeats (each worker entrypoint
writes ``nexus:health:{service}:{instance}`` with a 60s TTL). A service with
zero live keys is reported as ``missing`` — that is what the "worker sin
latido" alert (WP-06) consumes.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from fastapi import APIRouter, Response, status
from sqlalchemy import text

log = structlog.get_logger(__name__)

router = APIRouter(tags=["health"])

# One timeout for every dependency probe. Readiness must answer fast — an
# orchestrator polling a hung probe is as blind as one polling a stub.
_PROBE_TIMEOUT_S = 2.0

# Worker services expected to report a heartbeat. Extended in WP-07 when the
# worker splits into runner/scheduler/egress (each entrypoint reports its own
# service name).
EXPECTED_WORKER_SERVICES = ("nexus-worker",)

HEARTBEAT_KEY_PREFIX = "nexus:health:"


async def _check_postgres() -> None:
    from nexus_api.db.base import get_engine

    async def _probe() -> None:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))

    await asyncio.wait_for(_probe(), timeout=_PROBE_TIMEOUT_S)


async def _check_redis() -> None:
    from nexus_api.core.redis_client import get_redis

    await asyncio.wait_for(get_redis().ping(), timeout=_PROBE_TIMEOUT_S)


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness(response: Response) -> dict[str, Any]:
    checks: dict[str, str] = {}
    healthy = True
    for name, probe in (("postgres", _check_postgres), ("redis", _check_redis)):
        try:
            await probe()
            checks[name] = "ok"
        except Exception as exc:
            healthy = False
            checks[name] = f"error: {type(exc).__name__}"
            log.warning("health.ready.dependency_failed", dependency=name, error=str(exc))
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable", "checks": checks}
    return {"status": "ready", "checks": checks}


@router.get("/health/workers")
async def workers(response: Response) -> dict[str, Any]:
    """Report worker heartbeats. 503 when any expected service has no live
    heartbeat key — same contract as ``/health/ready``: the status code is
    the alert signal, the body is the diagnosis."""
    from nexus_api.core.redis_client import get_redis

    redis = get_redis()
    services: dict[str, list[str]] = {name: [] for name in EXPECTED_WORKER_SERVICES}
    try:
        keys = [
            key
            async for key in redis.scan_iter(match=f"{HEARTBEAT_KEY_PREFIX}*", count=100)
        ]
    except Exception as exc:
        log.warning("health.workers.redis_failed", error=str(exc))
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable", "error": f"redis: {type(exc).__name__}"}

    for key in keys:
        key_str = key.decode() if isinstance(key, bytes) else key
        rest = key_str.removeprefix(HEARTBEAT_KEY_PREFIX)
        service, _, instance = rest.partition(":")
        services.setdefault(service, []).append(instance or "unknown")

    missing = [name for name, instances in services.items() if not instances]
    body: dict[str, Any] = {
        "status": "degraded" if missing else "ok",
        "services": services,
        "missing": missing,
    }
    if missing:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return body
