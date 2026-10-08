"""Spec 030 T093 — el gasto sabe de qué agente es (R14.7).

Con varios agentes por cliente, el Panel y el Consumo dicen cuánto gastó cada
uno. Para eso el turno publica su ``agent_id`` y el consumidor lo escribe en
``usage_records`` (y en los asientos del libro, que prueba la suite de la API).
Un turno de antes de la spec 030 no lo lleva y la fila queda sin agente.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

from nexus_worker.metering import collector
from nexus_worker.metering.consumer import rows_from_entry

pytestmark = [pytest.mark.unit]


async def test_the_turn_publishes_its_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    published: list[dict[str, Any]] = []

    async def _xadd(_redis: Any, _stream: str, fields: dict[str, Any], **_kw: Any) -> None:
        published.append(fields)

    monkeypatch.setattr("nexus_api.core.streams.xadd_capped", _xadd)
    monkeypatch.setattr("nexus_api.core.redis_client.get_redis", lambda: object())
    tenant, agent, cfg = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with collector.usage_turn(
        tenant_id=tenant, turn_id="t-1", agent_config_id=cfg, agent_id=agent
    ):
        collector.record_usage(meter="llm.output_tokens", quantity=12, model="m")
    (fields,) = published
    assert fields["agent_id"] == str(agent)
    assert fields["agent_config_id"] == str(cfg)


def test_the_consumer_writes_the_agent_on_every_row() -> None:
    tenant, agent = uuid.uuid4(), uuid.uuid4()
    event = {
        "meter": "llm.output_tokens",
        "quantity": 12,
        "idempotency_key": "k1",
        "occurred_at": "2026-10-08T10:00:00+00:00",
        "model": "m",
    }
    _, rows = rows_from_entry(
        {"tenant_id": str(tenant), "events": json.dumps([event]), "agent_id": str(agent)}
    )
    assert [r["agent_id"] for r in rows] == [agent]
    _, legacy = rows_from_entry({"tenant_id": str(tenant), "events": json.dumps([event])})
    assert [r["agent_id"] for r in legacy] == [None]
