"""WP-03 (plataforma v2, Fase 0): readiness must fail loudly, not lie.

Before this WP ``/health/ready`` returned a constant — a deploy with broken
Postgres/Redis wiring received traffic and failed on the first real request.
These tests pin the new contract: 503 with the failing dependency named in
the body, 200 with per-dependency ``ok`` otherwise, and ``/health/workers``
reporting services whose heartbeat is missing.
"""

from __future__ import annotations

import pytest

from nexus_api import health as health_mod


@pytest.mark.asyncio
async def test_ready_ok_with_live_dependencies(client, fake_redis) -> None:
    r = await client.get("/health/ready")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ready"
    assert body["checks"] == {"postgres": "ok", "redis": "ok"}


@pytest.mark.asyncio
async def test_ready_503_names_postgres_when_db_down(client, monkeypatch) -> None:
    async def _boom() -> None:
        raise ConnectionError("db down")

    monkeypatch.setattr(health_mod, "_check_postgres", _boom)
    r = await client.get("/health/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "unavailable"
    assert body["checks"]["postgres"].startswith("error:")
    assert body["checks"]["redis"] == "ok"


@pytest.mark.asyncio
async def test_ready_503_names_redis_when_redis_down(client, monkeypatch) -> None:
    async def _boom() -> None:
        raise TimeoutError("redis timeout")

    monkeypatch.setattr(health_mod, "_check_redis", _boom)
    r = await client.get("/health/ready")
    assert r.status_code == 503
    assert r.json()["checks"]["redis"] == "error: TimeoutError"


@pytest.mark.asyncio
async def test_workers_reports_missing_heartbeat(client, fake_redis) -> None:
    r = await client.get("/health/workers")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    assert "nexus-worker" in body["missing"]


@pytest.mark.asyncio
async def test_workers_ok_with_live_heartbeat(client, fake_redis) -> None:
    await fake_redis.setex("nexus:health:nexus-worker:host-1", 60, "1")
    r = await client.get("/health/workers")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["missing"] == []
    assert body["services"]["nexus-worker"] == ["host-1"]
