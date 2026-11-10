"""El cron del ciclo de vida de los modelos (spec 047, T149 · 41.7, 41.8, 41.9).

La lógica vive en ``nexus_api.services.model_lifecycle`` y la prueba
``apps/api/tests/integration/models/test_model_lifecycle.py`` contra la base.
Aquí, el cableado del worker:

- el cron pasa el modelo de respuesta global (los agentes de hoy sin modelo
  propio están fijados en él) y, si algo cambió, avisa a los demás procesos:
  ``catalog`` por el canal de promoción y el cliente de cada agente movido;
- el suscriptor de promoción, al oír ``catalog``, olvida el catálogo en memoria:
  el siguiente turno lee el nuevo (41.9: «desde el siguiente turno»);
- una pasada que falla no tumba el cron.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from nexus_api.services.model_lifecycle import LifecycleReport

from nexus_worker.runtime import model_resolver
from nexus_worker.runtime.promote_subscriber import PROMOTE_CHANNEL, run_promote_subscriber
from nexus_worker.streams import model_lifecycle_cron as cron

pytestmark = pytest.mark.asyncio

TENANT = uuid.UUID("00000000-0000-0000-0000-0000000000a1")


class _Redis:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, message: str) -> int:
        self.published.append((channel, message))
        return 1


async def test_a_tick_passes_the_global_model_and_tells_the_other_processes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    async def run(*, now: datetime | None = None, default_respond: str | None = None) -> Any:
        seen.update(now=now, default_respond=default_respond)
        report = LifecycleReport(moved_agents=1, retired=["prov/old"])
        report.tenants_changed.add(TENANT)
        return report

    monkeypatch.setattr(cron, "run_lifecycle", run)
    redis = _Redis()
    moment = datetime(2026, 11, 1, tzinfo=UTC)
    report = await cron.lifecycle_tick(redis=redis, now=moment)
    assert report.moved_agents == 1
    assert seen["now"] == moment
    assert seen["default_respond"] == cron.get_worker_settings().llm_respond_model
    assert redis.published == [(PROMOTE_CHANNEL, "catalog"), (PROMOTE_CHANNEL, str(TENANT))]


async def test_a_quiet_tick_publishes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run(**_: Any) -> LifecycleReport:
        return LifecycleReport(retirement_notices=2)

    monkeypatch.setattr(cron, "run_lifecycle", run)
    redis = _Redis()
    await cron.lifecycle_tick(redis=redis)
    assert redis.published == []


async def test_a_failed_tick_does_not_stop_the_cron(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    stop = asyncio.Event()

    async def run(**_: Any) -> LifecycleReport:
        nonlocal calls
        calls += 1
        if calls == 2:
            stop.set()
        raise RuntimeError("la base no responde")

    monkeypatch.setattr(cron, "run_lifecycle", run)
    await asyncio.wait_for(cron.run_model_lifecycle_cron(stop=stop, tick_seconds=0.01), timeout=2)
    assert calls == 2


class _PubSub:
    def __init__(self, messages: list[str], stop: asyncio.Event) -> None:
        self._messages = list(messages)
        self._stop = stop

    async def subscribe(self, _channel: str) -> None:
        return None

    async def get_message(self, **_: Any) -> dict[str, Any] | None:
        if not self._messages:
            self._stop.set()
            return None
        return {"data": self._messages.pop(0).encode()}

    async def unsubscribe(self, _channel: str) -> None:
        return None

    async def aclose(self) -> None:
        return None


class _SubRedis:
    def __init__(self, pubsub: _PubSub) -> None:
        self._pubsub = pubsub

    def pubsub(self) -> _PubSub:
        return self._pubsub


class _Loader:
    def __init__(self) -> None:
        self.invalidated: list[tuple[uuid.UUID, uuid.UUID | None]] = []

    async def invalidate(self, tenant_id: uuid.UUID, agent_id: uuid.UUID | None = None) -> None:
        self.invalidated.append((tenant_id, agent_id))


async def test_the_promote_subscriber_drops_the_catalog_on_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dropped: list[bool] = []
    monkeypatch.setattr(model_resolver, "invalidate_catalog", lambda: dropped.append(True))
    stop = asyncio.Event()
    loader = _Loader()
    redis = _SubRedis(_PubSub(["catalog", str(TENANT)], stop))
    await asyncio.wait_for(
        run_promote_subscriber(redis, loader, stop=stop),  # type: ignore[arg-type]
        timeout=5,
    )
    assert dropped == [True], "el siguiente turno lee el catálogo nuevo"
    assert loader.invalidated == [(TENANT, None)], "y los agentes movidos, su versión nueva"
