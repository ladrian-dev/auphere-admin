"""Spec 045 R1 y R2.3 — el despachador marca lo que el agente atiende.

El despachador real, con el grafo sustituido por un doble (no probamos el
turno, probamos lo que se guarda antes de él):

- un entrante que la puerta deja pasar fija ``attended_at`` (la primera vez) y
  ``last_attended_inbound_at`` (cada vez);
- uno silenciado por los números permitidos no toca ninguna de las dos, y no
  avisa a la persona que atiende la conversación;
- un número solo de envío no atiende nada.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.runtime.dispatcher import InboundEvent, process_inbound

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Agent,
    AgentConfig,
    AgentConfigStatus,
    Channel,
    ChannelStatus,
    ChannelType,
    ClientPushEvent,
    Conversation,
    Tenant,
    TenantPlan,
    TenantStatus,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

ALLOWED = "+56911110001"
SILENCED = "+56922220002"


class _Pipeline:
    async def ainvoke(self, state: dict[str, Any], config: dict[str, Any] | None = None) -> Any:
        return {"intent": "info", "response": "ok", "tool_calls": []}


async def _world(*, admin_only: bool, channel_config: dict[str, Any] | None = None) -> Any:
    tenant_id = uuid.uuid4()
    sm = get_sessionmaker()
    async with sm() as s:
        s.add(
            Tenant(
                id=tenant_id,
                name="Atendido",
                slug=f"att-{tenant_id.hex[:8]}",
                plan=TenantPlan.PRO,
                status=TenantStatus.ACTIVE,
            )
        )
        await s.commit()
    async with sm() as s, tenant_scoped_session(s, tenant_id):
        agent = Agent(tenant_id=tenant_id, name="Agente")
        s.add(agent)
        await s.flush()
        policies = (
            {"admin_access": {"admin_only": True, "admin_phones": [ALLOWED]}} if admin_only else {}
        )
        s.add(
            AgentConfig(
                tenant_id=tenant_id,
                agent_id=agent.id,
                version=1,
                status=AgentConfigStatus.ACTIVE,
                system_prompt_rendered="Eres un agente.",
                channels=[],
                tools=[],
                policies=policies,
                created_by="test",
            )
        )
        channel = Channel(
            tenant_id=tenant_id,
            type=ChannelType.WHATSAPP,
            provider="meta",
            provider_identifier=f"att-{tenant_id.hex[:8]}",
            status=ChannelStatus.ACTIVE,
            config=dict(channel_config or {}),
        )
        s.add(channel)
        await s.flush()
        channel_id = channel.id
    return tenant_id, channel_id


async def _inbound(tenant_id: uuid.UUID, channel_id: uuid.UUID, sender: str) -> None:
    await process_inbound(
        InboundEvent(tenant_id=tenant_id, channel_id=channel_id, user_id=sender, content="hola"),
        pipeline=_Pipeline(),
    )


async def _conversation(tenant_id: uuid.UUID) -> Conversation:
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, tenant_id):
        return (await s.execute(sa.select(Conversation))).scalar_one()


async def test_an_attended_inbound_marks_the_conversation(db_session: Any) -> None:
    tenant_id, channel_id = await _world(admin_only=False)

    await _inbound(tenant_id, channel_id, ALLOWED)
    first = await _conversation(tenant_id)
    assert first.attended_at is not None
    assert first.last_attended_inbound_at == first.attended_at

    await _inbound(tenant_id, channel_id, ALLOWED)
    second = await _conversation(tenant_id)
    assert second.attended_at == first.attended_at
    assert second.last_attended_inbound_at > first.last_attended_inbound_at


async def test_a_silenced_number_is_never_attended(db_session: Any) -> None:
    tenant_id, channel_id = await _world(admin_only=True)

    await _inbound(tenant_id, channel_id, SILENCED)

    conv = await _conversation(tenant_id)
    assert conv.attended_at is None
    assert conv.last_attended_inbound_at is None


async def test_a_silenced_message_does_not_notify_the_person_in_control(db_session: Any) -> None:
    tenant_id, channel_id = await _world(admin_only=True)
    await _inbound(tenant_id, channel_id, SILENCED)
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, tenant_id):
        conv = (await s.execute(sa.select(Conversation))).scalar_one()
        conv.agent_active = False
        conv.assigned_user_id = "persona-1"

    await _inbound(tenant_id, channel_id, SILENCED)

    async with sm() as s, tenant_scoped_session(s, tenant_id):
        events = (
            await s.execute(
                sa.select(sa.func.count())
                .select_from(ClientPushEvent)
                .where(ClientPushEvent.kind == "inbox.message_for_you")
            )
        ).scalar_one()
    assert events == 0


async def test_an_allowed_message_still_notifies_the_person_in_control(db_session: Any) -> None:
    tenant_id, channel_id = await _world(admin_only=True)
    await _inbound(tenant_id, channel_id, ALLOWED)
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, tenant_id):
        conv = (await s.execute(sa.select(Conversation))).scalar_one()
        conv.agent_active = False
        conv.assigned_user_id = "persona-1"

    await _inbound(tenant_id, channel_id, ALLOWED)

    async with sm() as s, tenant_scoped_session(s, tenant_id):
        events = (
            await s.execute(
                sa.select(sa.func.count())
                .select_from(ClientPushEvent)
                .where(ClientPushEvent.kind == "inbox.message_for_you")
            )
        ).scalar_one()
    assert events == 1


async def test_a_send_only_number_attends_nothing(db_session: Any) -> None:
    tenant_id, channel_id = await _world(admin_only=False, channel_config={"agent_enabled": False})

    await _inbound(tenant_id, channel_id, ALLOWED)

    assert (await _conversation(tenant_id)).attended_at is None


async def test_only_an_attended_inbound_reaches_the_live_inbox(
    db_session: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """/cso CSO-002: ``message.new`` lleva el id del mensaje al stream de la
    Bandeja. Un entrante silenciado no se publica: su id no tiene que llegar a
    la consola (con él se pedía su adjunto)."""
    from nexus_worker.runtime import dispatcher

    published: list[dict[str, Any]] = []

    async def _publish(_redis: Any, **fields: Any) -> None:
        published.append(fields)

    monkeypatch.setattr(dispatcher, "publish_inbox_event", _publish)
    tenant_id, channel_id = await _world(admin_only=True)

    await _inbound(tenant_id, channel_id, SILENCED)

    def inbound_news() -> list[dict[str, Any]]:
        return [
            p for p in published if p["event"] == "message.new" and p.get("direction") == "inbound"
        ]

    assert inbound_news() == []

    await _inbound(tenant_id, channel_id, ALLOWED)
    assert len(inbound_news()) == 1
