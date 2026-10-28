"""Ayudantes de las pruebas de la página del canal y de su menú — spec 047,
T104 y T106. Los fixtures ``biz`` y ``bag`` están en ``conftest.py``."""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from nexus_worker.runtime.dispatcher import InboundEvent, process_inbound
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import Channel, ChannelStatus, ChannelType, Message, MessageDirection

from .._turn_world import RecordingPipeline
from ..business._business_world import Biz, seed_agent

TEAM = "+34600100100"
CUSTOMER = "+34600200200"


async def _channel(
    db_session: AsyncSession, biz: Biz, agent_id: uuid.UUID | None, number: str
) -> uuid.UUID:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        channel = Channel(
            tenant_id=biz.tenant_id,
            agent_id=agent_id,
            type=ChannelType.WHATSAPP,
            provider="meta",
            provider_identifier=number,
            config={"phone_number_id": f"PN{number[-4:]}", "waba_id": f"WABA{number[-4:]}"},
            status=ChannelStatus.ACTIVE,
        )
        db_session.add(channel)
        await db_session.flush()
        return channel.id


async def _published(db_session: AsyncSession, biz: Biz, name: str = "Recepción") -> uuid.UUID:
    agent_id, _cfg = await seed_agent(
        db_session, biz.tenant_id, name=name, prompt="Eres la recepción de la barbería."
    )
    await db_session.commit()
    return agent_id


def _url(biz: Biz, channel_id: uuid.UUID) -> str:
    return f"/console/clients/{biz.ref}/channels/{channel_id}"


async def _page(client: Any, biz: Biz, channel_id: uuid.UUID) -> dict[str, Any]:
    resp = await client.get(_url(biz, channel_id), headers=biz.headers())
    assert resp.status_code == 200, resp.text
    assert resp.headers["ETag"] == f'"{resp.json()["revision"]}"'
    out: dict[str, Any] = resp.json()
    return out


def _config(
    mode: str,
    *,
    tests: list[str] | None = None,
    exceptions: list[str] | None = None,
    recipients: list[dict[str, Any]] | None = None,
    wait: str | None = None,
) -> dict[str, Any]:
    return {
        "audience": {"mode": mode, "test_numbers": tests or [], "exceptions": exceptions or []},
        "escalation": {"recipients": recipients or [], "summary": True},
        "wait_message": wait,
    }


async def _put(
    client: Any,
    biz: Biz,
    channel_id: uuid.UUID,
    body: dict[str, Any],
    revision: int | None,
    expect: int = 200,
) -> dict[str, Any]:
    headers = biz.headers()
    if revision is not None:
        headers["If-Match"] = f'"{revision}"'
    resp = await client.put(f"{_url(biz, channel_id)}/config", json=body, headers=headers)
    assert resp.status_code == expect, resp.text
    out: dict[str, Any] = resp.json()
    return out


async def _say(biz: Biz, channel_id: uuid.UUID, user: str, text: str) -> RecordingPipeline:
    pipeline = RecordingPipeline()
    await process_inbound(
        InboundEvent(
            tenant_id=biz.tenant_id,
            channel_id=channel_id,
            user_id=user,
            content=text,
            provider_message_id=f"wamid.{uuid.uuid4().hex}",
        ),
        pipeline=pipeline,
    )
    return pipeline


async def _inbound(db_session: AsyncSession, biz: Biz, text: str) -> Message:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        row = await db_session.scalar(
            sa.select(Message).where(
                Message.direction == MessageDirection.INBOUND, Message.content == text
            )
        )
    assert row is not None, f"el mensaje «{text}» no se guardó"
    return row
