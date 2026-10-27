"""Spec 047, T025 — se guarda siempre, y la conversación dice por qué no contestó.

Requisitos 2.1 a 2.3. Hoy, sin saldo, el mensaje ni se guarda (research D8):
la puerta de saldo iba antes de ``persist_inbound_message`` y el consumidor
hacía ``ack``. Ahora todo entrante se guarda **antes** de cualquier puerta, y la
puerta que no deja contestar escribe su código de ``contracts/events.md`` §2 en
``conversations.waiting_reason``. Salvo fuera de la audiencia, la conversación
pasa a la Bandeja como «Espera a una persona» (``status = escalated``).

El tope del agente y la pausa del agente llegan con sus columnas (olas 7 y 4):
sus puertas no existen todavía y no se prueban aquí.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from fakeredis import aioredis as fakeaioredis
from nexus_worker.runtime.dispatcher import process_inbound
from nexus_worker.streams import consumer as consumer_mod

from nexus_api.db.models import (
    AgentConfigStatus,
    ChannelStatus,
    ConversationStatus,
    TenantStatus,
)

from ._turn_world import (
    RecordingPipeline,
    conversation_of,
    inbound_rows,
    make_world,
    wallet_closed,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _send(world: Any, pipeline: RecordingPipeline, content: str = "hola") -> dict[str, Any]:
    return await process_inbound(world.event(content), pipeline=pipeline)


async def _assert_waiting(world: Any, reason: str) -> None:
    rows = await inbound_rows(world)
    assert [r.content for r in rows] == ["hola"], "el entrante tiene que estar guardado"
    conv = await conversation_of(world)
    assert conv.waiting_reason == reason
    assert conv.status == ConversationStatus.ESCALATED, "va a la Bandeja: espera a una persona"
    # Spec 045: la Bandeja enseña lo atendido. Una conversación que espera a una
    # persona tiene que aparecer, aunque el agente no haya contestado.
    assert conv.attended_at is not None
    assert rows[0].skipped_reason is None


async def test_an_empty_bag_still_saves_the_message(db_session, monkeypatch) -> None:
    world = await make_world(db_session)
    wallet_closed(monkeypatch)
    pipeline = RecordingPipeline()

    result = await _send(world, pipeline)

    assert result["skipped"] == "wallet_empty"
    assert result["reason"] == "no_balance"
    assert pipeline.calls == []
    await _assert_waiting(world, "no_balance")


async def test_an_unpublished_agent_saves_and_waits(db_session) -> None:
    world = await make_world(db_session, agent_config=AgentConfigStatus.STAGED)
    pipeline = RecordingPipeline()

    result = await _send(world, pipeline)

    assert result["reason"] == "agent_unpublished"
    assert pipeline.calls == []
    await _assert_waiting(world, "agent_unpublished")


async def test_an_agent_with_only_archived_versions_is_unpublished_not_lost(db_session) -> None:
    """Antes llegaba al cargador, reventaba y acababa en la DLQ: un mensaje
    perdido para la Bandeja. Ahora espera a una persona con su motivo."""
    world = await make_world(db_session, agent_config=AgentConfigStatus.ARCHIVED)
    pipeline = RecordingPipeline()

    result = await _send(world, pipeline)

    assert result["reason"] == "agent_unpublished"
    await _assert_waiting(world, "agent_unpublished")


@pytest.mark.parametrize(
    ("status", "reason"),
    [(TenantStatus.PAUSED, "paused_client"), (TenantStatus.ARCHIVED, "archived_client")],
)
async def test_a_paused_or_archived_client_saves_and_waits(db_session, status, reason) -> None:
    world = await make_world(db_session, tenant_status=status)
    pipeline = RecordingPipeline()

    result = await _send(world, pipeline)

    assert result["skipped"] == "tenant_inactive"
    assert result["reason"] == reason
    assert pipeline.calls == []
    await _assert_waiting(world, reason)


async def test_a_paused_channel_saves_and_waits(db_session) -> None:
    world = await make_world(db_session, channel_status=ChannelStatus.PAUSED)
    pipeline = RecordingPipeline()

    result = await _send(world, pipeline)

    assert result["reason"] == "paused_channel"
    assert pipeline.calls == []
    await _assert_waiting(world, "paused_channel")


async def test_a_degraded_channel_keeps_answering(db_session) -> None:
    """Historia 1, escenario 3: con la calidad en amarillo los mensajes siguen
    llegando y el agente sigue respondiendo. Se guarda y se contesta."""
    world = await make_world(db_session, channel_status=ChannelStatus.DEGRADED)
    pipeline = RecordingPipeline()

    result = await _send(world, pipeline)

    assert result.get("skipped") is None
    assert len(pipeline.calls) == 1
    assert [r.content for r in await inbound_rows(world)] == ["hola"]
    conv = await conversation_of(world)
    assert conv.waiting_reason is None
    assert conv.status == ConversationStatus.OPEN


async def test_out_of_audience_saves_but_never_goes_to_the_inbox(db_session) -> None:
    """Spec 024: un número que no está en «A quién responde». Se guarda con su
    motivo, pero no es una conversación que espere a nadie."""
    world = await make_world(
        db_session,
        policies={"admin_access": {"admin_only": True, "admin_phones": ["+34999000111"]}},
    )
    pipeline = RecordingPipeline()

    result = await _send(world, pipeline)

    assert result["skipped"] == "not_admin"
    assert result["reason"] == "out_of_audience"
    assert pipeline.calls == []
    rows = await inbound_rows(world)
    assert [r.content for r in rows] == ["hola"]
    assert rows[0].skipped_reason == "not_admin"
    conv = await conversation_of(world)
    assert conv.waiting_reason == "out_of_audience"
    assert conv.status == ConversationStatus.OPEN
    assert conv.attended_at is None


async def test_a_person_in_control_keeps_the_conversation(db_session) -> None:
    """La lleva una persona: el motivo queda, pero no se convierte en «espera»."""
    world = await make_world(db_session)
    pipeline = RecordingPipeline()
    await _send(world, pipeline)
    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.base import get_sessionmaker
    from nexus_api.db.models import Conversation

    conv = await conversation_of(world)
    async with get_sessionmaker()() as s, tenant_scoped_session(s, world.tenant_id):
        row = await s.get(Conversation, conv.id)
        assert row is not None
        row.agent_active = False
        await s.commit()

    result = await process_inbound(world.event("¿hay alguien?"), pipeline=pipeline)

    assert result["skipped"] == "human_takeover"
    assert result["reason"] == "human_takeover"
    assert len(pipeline.calls) == 1, "solo el primer mensaje llegó al agente"
    conv = await conversation_of(world)
    assert conv.waiting_reason == "human_takeover"
    assert conv.status == ConversationStatus.OPEN


async def test_no_model_available_saves_and_waits(db_session, monkeypatch) -> None:
    """El proxy de modelos del partner no está configurado: «Sin modelo
    disponible», en la Bandeja, en vez de un turno descartado en el log."""
    from nexus_api.core import llm_proxy

    world = await make_world(db_session)
    monkeypatch.setattr(
        llm_proxy, "partner_id_for_tenant_standalone", AsyncMock(return_value=world.tenant_id)
    )

    def _missing(_partner: Any) -> None:
        raise llm_proxy.LLMProxyUnavailable("missing partner virtual key")

    monkeypatch.setattr(llm_proxy, "resolve_litellm_proxy_optional", _missing)
    pipeline = RecordingPipeline()

    result = await _send(world, pipeline)

    assert result["reason"] == "no_model"
    assert pipeline.calls == []
    await _assert_waiting(world, "no_model")


async def test_the_agent_answering_again_clears_a_gate_reason(db_session, monkeypatch) -> None:
    """Vuelve el saldo: el siguiente mensaje lo contesta el agente y la
    conversación deja de esperar por «sin saldo»."""
    world = await make_world(db_session)
    wallet_closed(monkeypatch)
    pipeline = RecordingPipeline()
    await _send(world, pipeline)
    wallet_closed(monkeypatch, closed=False)

    result = await process_inbound(world.event("¿sigues ahí?"), pipeline=pipeline)

    assert result.get("skipped") is None
    assert len(pipeline.calls) == 1
    assert pipeline.calls[0]["user_message"] == "¿sigues ahí?", (
        "lo que se quedó sin contestar no se contesta tarde"
    )
    conv = await conversation_of(world)
    assert conv.waiting_reason is None
    assert conv.status == ConversationStatus.OPEN


async def test_a_retried_entry_does_not_save_the_message_twice(db_session, monkeypatch) -> None:
    """El índice único de ``provider_message_id`` lleva ``created_at`` (la tabla
    está particionada) y no impide una segunda fila: el despachador reutiliza
    la que ya existe."""
    world = await make_world(db_session)
    wallet_closed(monkeypatch)
    event = world.event("hola", wamid="wamid.retry-1")
    pipeline = RecordingPipeline()

    await process_inbound(event, pipeline=pipeline)
    await process_inbound(event, pipeline=pipeline)

    assert len(await inbound_rows(world)) == 1


# ── El consumidor no hace ``ack`` sin guardar ────────────────────────────────

STREAM = "nexus:inbound:standard"
GROUP = "nexus-worker"


def _entry(world: Any, content: str = "hola") -> dict[str, str]:
    return {
        "tenant_id": str(world.tenant_id),
        "channel_id": str(world.channel_id),
        "user_id": "+34600111222",
        "content": content,
        "provider": "meta",
        "provider_message_id": f"wamid.{content}",
    }


async def _deliver(redis: Any, fields: dict[str, str]) -> tuple[Any, Any]:
    await redis.xadd(STREAM, fields)
    resp = await redis.xreadgroup(groupname=GROUP, consumername="c1", streams={STREAM: ">"})
    return resp[0][1][0]


@pytest.mark.parametrize("window_ms", [0, 3000])
async def test_the_consumer_acks_only_what_it_saved(db_session, monkeypatch, window_ms) -> None:
    world = await make_world(db_session)
    wallet_closed(monkeypatch)
    redis = fakeaioredis.FakeRedis()
    await redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    entry_id, raw = await _deliver(redis, _entry(world))

    acked = await consumer_mod.handle_entry(
        redis,
        pipeline=RecordingPipeline(),
        stream=STREAM,
        group=GROUP,
        entry_id=entry_id,
        raw_fields=raw,
        coalesce_window_ms=window_ms,
    )

    assert acked is True
    assert [r.content for r in await inbound_rows(world)] == ["hola"]


async def test_a_save_that_fails_is_not_acked(db_session, monkeypatch) -> None:
    world = await make_world(db_session)
    redis = fakeaioredis.FakeRedis()
    await redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    entry_id, raw = await _deliver(redis, _entry(world))
    from nexus_worker.runtime import dispatcher

    monkeypatch.setattr(
        dispatcher, "persist_inbound_message", AsyncMock(side_effect=RuntimeError("bd caída"))
    )

    acked = await consumer_mod.handle_entry(
        redis,
        pipeline=RecordingPipeline(),
        stream=STREAM,
        group=GROUP,
        entry_id=entry_id,
        raw_fields=raw,
        coalesce_window_ms=3000,
    )

    assert acked is False
    assert (await redis.xpending(STREAM, GROUP))["pending"] == 1


# ── El webhook: el número en pausa o con problemas sigue siendo del cliente ──


def _meta_body(world: Any, wamid: str) -> bytes:
    import json

    return json.dumps(
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
                                        "id": wamid,
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


async def _enqueued(redis: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for stream in ("nexus:inbound:standard", "nexus:inbound:priority"):
        out.extend(fields for _id, fields in await redis.xrange(stream))
    return out


@pytest.mark.parametrize(
    ("status", "mark_read"),
    [(ChannelStatus.PAUSED, False), (ChannelStatus.DEGRADED, True)],
)
async def test_the_webhook_takes_a_paused_or_degraded_number(
    client, db_session, fake_redis, status, mark_read
) -> None:
    """En pausa nadie contesta: el entrante se encola para guardarlo, sin los
    dos ticks azules. Con problemas de calidad el agente sigue respondiendo."""
    from nexus_channels.whatsapp_meta.signature import sign_meta_request

    world = await make_world(db_session, channel_status=status)
    body = _meta_body(world, f"wamid.webhook-{status.value}")

    response = await client.post(
        "/webhook/meta",
        content=body,
        headers={"X-Hub-Signature-256": sign_meta_request("dev-meta-app-secret-change-me", body)},
    )

    assert response.json()["status"] == "ok"
    [fields] = await _enqueued(fake_redis)
    assert fields["channel_id"] == str(world.channel_id)
    assert (fields.get("mark_read") == "1") is mark_read
