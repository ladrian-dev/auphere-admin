"""Spec 059 (requisito 3.2; T027) — un cambio de pesos cobra desde el turno siguiente.

Los pesos de venta se leen del catálogo del medidor (``metering.pricing``), que se
cachea cinco minutos. Cuando Auphere cambia los pesos o el objetivo en el panel, la
API publica ``CATALOG_CHANGED``: el worker tiene que olvidar el catálogo del medidor
y el objetivo de venta en ese momento, para que la valoración siguiente use los
pesos nuevos sin esperar a que caduque.
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import pytest
from nexus_api.metering import sale_policy
from nexus_api.services.router_catalog import CATALOG_CHANGED

from nexus_worker.metering import pricing
from nexus_worker.metering.pricing import ModelPrice
from nexus_worker.runtime import promote_subscriber

pytestmark = pytest.mark.asyncio


async def _deliver(*messages: str) -> None:
    class _Loader:
        async def invalidate(self, tenant_id: uuid.UUID, agent_id: uuid.UUID | None = None) -> None:
            pass

    class _PubSub:
        def __init__(self) -> None:
            self.queue = list(messages)

        async def subscribe(self, channel: str) -> None:
            pass

        async def get_message(self, **_kw: object) -> dict[str, str] | None:
            if self.queue:
                return {"data": self.queue.pop(0)}
            stop.set()
            return None

        async def unsubscribe(self, channel: str) -> None:
            pass

        async def aclose(self) -> None:
            pass

    class _Redis:
        def pubsub(self) -> _PubSub:
            return _PubSub()

    stop = asyncio.Event()
    await promote_subscriber.run_promote_subscriber(_Redis(), _Loader(), stop=stop)  # type: ignore[arg-type]


async def test_a_catalog_change_forgets_the_meter_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    old = {"m": ModelPrice(model_id="m", quota_weight_input=Decimal("0.88"))}
    monkeypatch.setattr(pricing, "_cache", old)
    monkeypatch.setattr(pricing, "_cached_at", 10**12)  # «recién leído»
    monkeypatch.setattr(sale_policy, "_cache", (10**12, Decimal("2.2")))

    await _deliver(CATALOG_CHANGED)

    assert pricing._cache is None, "la valoración siguiente relee los pesos"
    assert sale_policy._cache is None, "y el objetivo de venta"


async def test_a_tenant_promotion_does_not_touch_the_meter(monkeypatch: pytest.MonkeyPatch) -> None:
    old = {"m": ModelPrice(model_id="m")}
    monkeypatch.setattr(pricing, "_cache", old)
    await _deliver(str(uuid.uuid4()))
    assert pricing._cache is old
