"""Spec 047, T024 — «Construcción y pruebas» se mide aparte y no toca la bolsa.

Requisito 46.4 (y 15.7, 20.6, 5.10, 12.6, 38.5, 51.6, 42.6). El constructor, el
playground, las pruebas (y las certificaciones que lanza el partner), la lectura
de webs, la indexación y las sugerencias se miden con ``line = build``: los paga Auphere
hasta el tope del partner (ola 7) y **nunca** salen de la bolsa del cliente ni
alimentan su presupuesto. Hoy existen el playground (``qa``) y el Companion; el
resto entra por el mismo mecanismo: ``usage_turn(source=...)`` con su origen.

Por el camino de verdad: colector → ``nexus:usage`` → ``drain_once`` →
``usage_records``.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.metering import collector
from nexus_worker.metering import consumer as metering

from nexus_api.core import redis_client
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import PartnerAllocation, UsageLedger, UsageRecord

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

BUILD_SOURCES = (
    collector.SOURCE_QA,
    collector.SOURCE_BUILDER,
    collector.SOURCE_TESTS,
    collector.SOURCE_READER,
    collector.SOURCE_INDEXER,
    collector.SOURCE_SUGGESTIONS,
)
TASK_OF = {
    collector.SOURCE_QA: "tool_turn",
    collector.SOURCE_BUILDER: "build",
    collector.SOURCE_TESTS: "judge",
    collector.SOURCE_READER: "read_source",
    collector.SOURCE_INDEXER: "embed",
    collector.SOURCE_SUGGESTIONS: "summarize",
}


async def _spend(tenant_id: uuid.UUID, source: str, task: str) -> None:
    async with collector.usage_turn(
        tenant_id=tenant_id, turn_id=f"{source}:{uuid.uuid4()}", source=source
    ):
        collector.record_llm_usage(
            model="anthropic/claude-haiku-5-5",
            provider="anthropic",
            usage={"prompt_tokens": 1000, "completion_tokens": 200},
            task=task,
            route_decision_id=uuid.uuid4(),
        )


async def _rows(tenant_id: uuid.UUID) -> list[UsageRecord]:
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        rows = list((await s.execute(sa.select(UsageRecord))).scalars().all())
        for r in rows:
            s.expunge(r)
        return rows


async def _drain() -> None:
    await metering.drain_once(redis_client.get_redis(), consumer_name="t024")


@pytest.fixture(autouse=True)
def _strict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_USAGE_REQUIRE_TASK", "1")
    metering._partner_of.clear()


async def test_every_build_source_lands_on_the_build_line(console_world) -> None:
    tenant_id = console_world["a"]["tenant_id"]
    for source in BUILD_SOURCES:
        await _spend(tenant_id, source, TASK_OF[source])

    await _drain()

    rows = await _rows(tenant_id)
    assert {r.source for r in rows} == set(BUILD_SOURCES)
    assert {r.line for r in rows} == {"build"}
    assert all(r.task for r in rows), "cada llamada lleva su tarea"
    assert all(r.route_decision_id for r in rows), "y la decisión que la eligió"
    assert {(r.source, r.task) for r in rows} == set(TASK_OF.items())


async def test_build_never_comes_out_of_the_clients_bag(db_session, console_world) -> None:
    a = console_world["a"]
    before = await db_session.scalar(
        sa.select(PartnerAllocation.remaining).where(PartnerAllocation.tenant_id == a["tenant_id"])
    )
    for source in BUILD_SOURCES:
        await _spend(a["tenant_id"], source, TASK_OF[source])

    await _drain()

    db_session.expire_all()
    after = await db_session.scalar(
        sa.select(PartnerAllocation.remaining).where(PartnerAllocation.tenant_id == a["tenant_id"])
    )
    assert after == before, "el tope del cliente no se mueve"
    ledger = await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(UsageLedger)
        .where(UsageLedger.tenant_id == a["tenant_id"])
    )
    assert ledger == 0, "ningún asiento contra la bolsa"


async def test_channel_companion_and_certification_keep_their_own_lines(console_world) -> None:
    """Las certificaciones que lanza Auphere (un despliegue más barato, una
    retirada) son de Auphere: partida ``platform``, fuera de las del partner
    (requisito 42.6). Las que lanza el partner al cambiar la calidad entran
    como ``tests``."""
    tenant_id = console_world["a"]["tenant_id"]
    await _spend(tenant_id, collector.SOURCE_CHANNEL, "tool_turn")
    await _spend(tenant_id, collector.SOURCE_COMPANION, "tool_turn")
    await _spend(tenant_id, collector.SOURCE_CERTIFICATION, "judge")

    await _drain()

    lines: dict[str, Any] = {r.source: r.line for r in await _rows(tenant_id)}
    assert lines == {
        "channel": "conversations",
        "companion": "companion",
        "certification": "platform",
    }
