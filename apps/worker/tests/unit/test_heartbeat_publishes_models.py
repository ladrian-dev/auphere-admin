"""Spec 059 (requisito 1.5; T005) — el latido publica los modelos que usa el worker.

La API decide si un modelo está en uso con el registro de valores por defecto. Lo
calcula ella, pero el worker puede tener otros ajustes en su despliegue: por eso
cada latido publica lo que el worker resuelve de verdad, ``{"v": 1, "models": …}``,
con la misma caducidad de siempre. Un latido sin modelos (``"1"``, de una versión
anterior) hace que la API no pueda verificar y rechace.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fakeredis import aioredis as fakeaioredis

from nexus_worker import health
from nexus_worker.platform_models import default_models

pytestmark = pytest.mark.asyncio


async def _one_beat(redis: fakeaioredis.FakeRedis, **kwargs: object) -> bytes:
    stop = asyncio.Event()
    task = asyncio.create_task(
        health.run_heartbeat(redis, service="nexus-worker", stop=stop, interval_s=0.05, **kwargs)  # type: ignore[arg-type]
    )
    await asyncio.sleep(0.02)
    [key] = await redis.keys("nexus:health:nexus-worker:*")
    value = await redis.get(key)
    ttl = await redis.ttl(key)
    stop.set()
    await asyncio.wait_for(task, timeout=2.0)
    assert 0 < ttl <= health.HEARTBEAT_TTL_S, "la caducidad no cambia"
    assert value is not None
    return bytes(value)


async def test_the_heartbeat_carries_the_registry() -> None:
    value = json.loads(await _one_beat(fakeaioredis.FakeRedis(), payload=health.models_payload()))
    assert value == {"v": health.HEARTBEAT_VERSION, "models": default_models()}


async def test_a_deployment_override_is_what_gets_published(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEXUS_LLM_JUDGE_MODEL", "anthropic/claude-haiku-5-5")
    value = json.loads(await _one_beat(fakeaioredis.FakeRedis(), payload=health.models_payload()))
    assert value["models"]["judge"] == "anthropic/claude-haiku-5-5"


async def test_without_a_payload_the_old_value_stays() -> None:
    assert await _one_beat(fakeaioredis.FakeRedis()) == b"1"


async def test_a_registry_that_cannot_be_read_still_beats() -> None:
    """Si el registro falla, el latido sigue (el servicio está vivo) y escribe "1":
    la API leerá «sin publicar» y rechazará, que es lo seguro."""

    def broken() -> str:
        raise RuntimeError("config rota")

    assert await _one_beat(fakeaioredis.FakeRedis(), payload=broken) == b"1"
