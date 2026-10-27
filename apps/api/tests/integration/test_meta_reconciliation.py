"""Spec 047, T030 — cada día se cuadra lo que Meta entregó con lo guardado.

Requisito 2.6. El webhook anota, por canal y día, el ``wamid`` de cada entrante
que Meta le entrega y que encola (solo el identificador: nunca el cuerpo ni el
teléfono). El cron diario compara ese conjunto con los entrantes guardados en
``messages``: una diferencia es un mensaje que se perdió entre el webhook y la
base —el stream, el consumidor, la DLQ— y Auphere tiene que enterarse.

Cada pasada deja su fila en ``meta_reconciliation_runs`` (la vista del admin es
T172) y es idempotente: el mismo día no se cuadra ni se avisa dos veces.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_channels.whatsapp_meta.signature import sign_meta_request
from nexus_worker.streams import meta_reconciliation_cron as cron
from structlog.testing import capture_logs

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Conversation,
    ConversationStatus,
    Customer,
    Message,
    MessageDirection,
    MetaReconciliationRun,
)
from nexus_api.services import meta_reconciliation

from ._turn_world import make_world

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

DAY = date(2026, 10, 26)
NOON = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)


async def _store(world: Any, wamids: list[str], at: datetime) -> None:
    async with get_sessionmaker()() as s, tenant_scoped_session(s, world.tenant_id):
        customer = Customer(tenant_id=world.tenant_id, identifier="+34600111222", preferences={})
        s.add(customer)
        await s.flush()
        conv = Conversation(
            tenant_id=world.tenant_id,
            channel_id=world.channel_id,
            customer_id=customer.id,
            status=ConversationStatus.OPEN,
        )
        s.add(conv)
        await s.flush()
        for i, wamid in enumerate(wamids):
            s.add(
                Message(
                    tenant_id=world.tenant_id,
                    conversation_id=conv.id,
                    direction=MessageDirection.INBOUND,
                    content="hola",
                    provider_message_id=wamid,
                    created_at=at + timedelta(seconds=i),
                    tool_calls=[],
                )
            )
        await s.commit()


async def _runs(world: Any) -> list[MetaReconciliationRun]:
    async with get_sessionmaker()() as s, tenant_scoped_session(s, world.tenant_id):
        rows = list((await s.execute(sa.select(MetaReconciliationRun))).scalars().all())
        for r in rows:
            s.expunge(r)
        return rows


async def test_a_message_lost_between_the_webhook_and_the_base_is_reported(
    db_session, fake_redis, monkeypatch
) -> None:
    world = await make_world(db_session)
    for wamid in ("wamid.a", "wamid.b", "wamid.c"):
        await meta_reconciliation.record_delivered(
            fake_redis, channel_id=world.channel_id, wamid=wamid, at=NOON
        )
    await _store(world, ["wamid.a", "wamid.b"], NOON)
    sent: list[dict[str, Any]] = []

    async def _email(**kw: Any) -> None:
        sent.append(kw)

    monkeypatch.setattr(cron, "send_email", _email)
    monkeypatch.setattr(cron, "_alert_email", lambda: "ops@auphere.test")

    with capture_logs() as logs:
        report = await cron.reconcile_day(DAY, redis=fake_redis)

    [run] = await _runs(world)
    assert (run.meta_count, run.stored_count, run.diff) == (3, 2, 1)
    assert run.date == DAY
    assert report.channels_with_diff == 1
    alerts = [e for e in logs if e.get("event") == "ops.meta_reconciliation"]
    assert len(alerts) == 1
    assert alerts[0]["missing"] == 1
    assert str(world.tenant_id) in json.dumps(alerts[0]["channels"])
    assert "hola" not in json.dumps(alerts[0], default=str), "nunca el cuerpo de un mensaje"
    assert len(sent) == 1 and sent[0]["to"] == "ops@auphere.test"


async def test_the_same_day_is_reconciled_once(db_session, fake_redis, monkeypatch) -> None:
    world = await make_world(db_session)
    await meta_reconciliation.record_delivered(
        fake_redis, channel_id=world.channel_id, wamid="wamid.x", at=NOON
    )
    sent: list[dict[str, Any]] = []

    async def _email(**kw: Any) -> None:
        sent.append(kw)

    monkeypatch.setattr(cron, "send_email", _email)
    monkeypatch.setattr(cron, "_alert_email", lambda: "ops@auphere.test")

    await cron.reconcile_day(DAY, redis=fake_redis)
    await cron.reconcile_day(DAY, redis=fake_redis)

    assert len(await _runs(world)) == 1
    assert len(sent) == 1, "un aviso al día"


async def test_a_day_that_squares_leaves_its_row_and_tells_nobody(
    db_session, fake_redis, monkeypatch
) -> None:
    world = await make_world(db_session)
    await meta_reconciliation.record_delivered(
        fake_redis, channel_id=world.channel_id, wamid="wamid.ok", at=NOON
    )
    # Guardado pasada la medianoche: el cuadre va por wamid, no por la hora.
    await _store(world, ["wamid.ok"], datetime(2026, 10, 27, 0, 0, 30, tzinfo=UTC))
    sent: list[Any] = []

    async def _email(**kw: Any) -> None:
        sent.append(kw)

    monkeypatch.setattr(cron, "send_email", _email)

    report = await cron.reconcile_day(DAY, redis=fake_redis)

    [run] = await _runs(world)
    assert (run.meta_count, run.stored_count, run.diff) == (1, 1, 0)
    assert report.channels_with_diff == 0
    assert sent == []


async def test_the_webhook_notes_what_meta_delivered(client, db_session, fake_redis) -> None:
    world = await make_world(db_session)
    body = json.dumps(
        {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "WABA1",
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": world.provider_identifier.lstrip("+"),
                                    "phone_number_id": "PN",
                                },
                                "contacts": [{"profile": {"name": "Ana"}, "wa_id": "34600111222"}],
                                "messages": [
                                    {
                                        "from": "34600111222",
                                        "id": "wamid.delivered-1",
                                        "timestamp": "1761480000",
                                        "type": "text",
                                        "text": {"body": "hola"},
                                    }
                                ],
                            },
                        }
                    ],
                }
            ],
        }
    ).encode()
    signature = sign_meta_request("dev-meta-app-secret-change-me", body)

    response = await client.post(
        "/webhook/meta", content=body, headers={"X-Hub-Signature-256": signature}
    )

    assert response.json()["status"] == "ok"
    key = meta_reconciliation.delivered_key(world.channel_id, datetime.now(UTC).date())
    assert await fake_redis.smembers(key) == {"wamid.delivered-1"}
    assert await fake_redis.ttl(key) > 0, "el conjunto caduca solo"


def test_the_cron_follows_the_scheduler_contract() -> None:
    import inspect

    sig = inspect.signature(cron.run_meta_reconciliation_cron)
    assert "stop" in sig.parameters
    assert sig.parameters["stop"].kind is inspect.Parameter.KEYWORD_ONLY
    assert cron.TASK_NAME == "meta-reconciliation-cron"
