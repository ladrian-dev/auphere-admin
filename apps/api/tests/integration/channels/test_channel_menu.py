"""Spec 047, T106 — mover, pausar y desconectar un número (historia 11;
requisito 34).

- **El menú**: «Configuración», «Pasar a otro agente» si hay otros agentes que no
  son borradores, «Pausar» o «Reanudar» y «Desconectar».
- **Mover**: vale desde el siguiente mensaje y conserva la configuración del canal
  y las conversaciones; el destino puede estar en pausa, un borrador no.
- **Pausar y reanudar**: lo que llega se guarda y espera a una persona con «Canal
  en pausa»; reanudar devuelve lo de antes.
- **Desconectar**: pide confirmación en la consola y conserva la fila y el
  historial; si Meta falla queda con «Reintentar» y nunca rompe la suscripción
  de otro entorno. Eso lo prueban ``tests/unit/test_endpoint_console_channels.py``
  (``test_disconnect_marks_the_channel_and_leaves_its_row``,
  ``test_meta_down_still_disconnects_and_says_what_is_pending`` y
  ``test_a_subscription_to_another_environment_is_left_alone``); aquí, que un
  número desconectado ya no ofrece el menú.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import Agent, AuditLog, Channel, ChannelStatus, Conversation

from ..business._business_world import Biz
from ._channel_world import (
    CUSTOMER,
    TEAM,
    _channel,
    _config,
    _page,
    _published,
    _put,
    _say,
    _url,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _post(client: Any, biz: Biz, channel_id: uuid.UUID, action: str, **body: Any) -> Any:
    return await client.post(
        f"{_url(biz, channel_id)}/{action}", json=body or None, headers=biz.headers()
    )


async def test_the_menu_offers_what_each_number_can_do(
    client: Any, db_session: AsyncSession, biz: Biz, bag: dict[str, bool]
) -> None:
    first = await _published(db_session, biz, "Recepción")
    channel_id = await _channel(db_session, biz, first, "34911000101")
    alone = await _page(client, biz, channel_id)
    assert alone["allowed"] == ["configure", "pause", "disconnect"], (
        "sin otro agente que no sea borrador, no se ofrece pasar el número"
    )
    async with tenant_scoped_session(db_session, biz.tenant_id):
        db_session.add(Agent(id=uuid.uuid4(), tenant_id=biz.tenant_id, name="Borrador"))
    await db_session.commit()
    assert "move" not in (await _page(client, biz, channel_id))["allowed"]

    second = await _published(db_session, biz, "Ventas")
    async with tenant_scoped_session(db_session, biz.tenant_id):
        agent = await db_session.get(Agent, second)
        assert agent is not None
        agent.lifecycle = "published"
    await db_session.commit()
    page = await _page(client, biz, channel_id)
    assert page["allowed"] == ["configure", "move", "pause", "disconnect"]
    assert [t["name"] for t in page["move_targets"]] == ["Ventas"]


async def test_moving_applies_from_the_next_message_and_keeps_config_and_history(
    client: Any, db_session: AsyncSession, biz: Biz, bag: dict[str, bool]
) -> None:
    first = await _published(db_session, biz, "Recepción")
    second = await _published(db_session, biz, "Ventas")
    async with tenant_scoped_session(db_session, biz.tenant_id):
        for agent_id, life in ((first, "published"), (second, "paused")):
            agent = await db_session.get(Agent, agent_id)
            assert agent is not None
            agent.lifecycle = life
            agent.pause_reason = "manual" if life == "paused" else None
    await db_session.commit()
    channel_id = await _channel(db_session, biz, first, "34911000102")
    await _put(client, biz, channel_id, _config("everyone", exceptions=[TEAM]), 0)
    before = await _say(biz, channel_id, CUSTOMER, "antes de mover")
    assert len(before.calls) == 1 and before.calls[0]["agent_id"] == str(first)

    # El destino está en pausa: no tiene que estar atendiendo (34.2).
    moved = await _post(client, biz, channel_id, "move", to_agent_id=str(second))
    assert moved.status_code == 200, moved.text
    assert moved.json()["agent"]["id"] == str(second)
    assert moved.json()["config"]["audience"] == {
        "mode": "everyone",
        "test_numbers": [],
        "exceptions": [TEAM],
    }, "la configuración del canal viaja con el número"

    after = await _say(biz, channel_id, CUSTOMER, "después de mover")
    assert after.calls == [], "el agente de destino está en pausa: no contesta, pero se guarda"
    async with tenant_scoped_session(db_session, biz.tenant_id):
        conversations = (
            await db_session.scalars(
                sa.select(Conversation).where(Conversation.channel_id == channel_id)
            )
        ).all()
        audit = await db_session.scalar(
            sa.select(AuditLog).where(AuditLog.action == "channel.moved")
        )
    assert len(conversations) == 1, "las conversaciones siguen en el mismo hilo"
    assert conversations[0].waiting_reason == "paused_agent"
    assert audit is not None and audit.after_json == {"from": str(first), "to": str(second)}

    draft = Agent(id=uuid.uuid4(), tenant_id=biz.tenant_id, name="Borrador")
    async with tenant_scoped_session(db_session, biz.tenant_id):
        db_session.add(draft)
    await db_session.commit()
    refused = await _post(client, biz, channel_id, "move", to_agent_id=str(draft.id))
    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "unknown_target_agent"


async def test_pausing_keeps_the_messages_and_resuming_gives_back_what_it_was(
    client: Any, db_session: AsyncSession, biz: Biz, bag: dict[str, bool]
) -> None:
    agent_id = await _published(db_session, biz)
    channel_id = await _channel(db_session, biz, agent_id, "34911000103")
    await _put(client, biz, channel_id, _config("everyone"), 0)

    paused = await _post(client, biz, channel_id, "pause")
    assert paused.status_code == 200, paused.text
    body = paused.json()
    assert body["visible_state"]["code"] == "paused"
    assert "resume" in body["allowed"] and "pause" not in body["allowed"]

    quiet = await _say(biz, channel_id, CUSTOMER, "¿hay alguien?")
    assert quiet.calls == []
    async with tenant_scoped_session(db_session, biz.tenant_id):
        conversation = await db_session.scalar(
            sa.select(Conversation).where(Conversation.channel_id == channel_id)
        )
        channel = await db_session.get(Channel, channel_id, populate_existing=True)
    assert conversation is not None and conversation.waiting_reason == "paused_channel"
    assert channel is not None and channel.paused_origin == "console"

    resumed = await _post(client, biz, channel_id, "resume")
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "active"
    assert resumed.json()["visible_state"]["code"] == "everyone"
    assert len((await _say(biz, channel_id, CUSTOMER, "ya estáis")).calls) == 1


async def test_a_disconnected_number_offers_no_menu_and_keeps_its_row(
    client: Any, db_session: AsyncSession, biz: Biz, bag: dict[str, bool]
) -> None:
    agent_id = await _published(db_session, biz)
    channel_id = await _channel(db_session, biz, agent_id, "34911000104")
    async with tenant_scoped_session(db_session, biz.tenant_id):
        channel = await db_session.get(Channel, channel_id)
        assert channel is not None
        channel.status = ChannelStatus.DISCONNECTED
    await db_session.commit()
    page = await _page(client, biz, channel_id)
    assert page["allowed"] == [] and page["visible_state"]["code"] == "disconnected"
    refused = await _post(client, biz, channel_id, "pause")
    assert refused.status_code == 409
