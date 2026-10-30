"""Spec 049, requirements 3 and 4 — how an Instagram / Messenger row leaves.

The dispatcher decides from the conversation and from who wrote the row:

- the agent within 24 h of the last DM: a plain response;
- the agent after 24 h: refused, never tagged, never retried;
- a team member after 24 h and within 7 days: ``human_agent=True``;
- the agent's answer to a comment: a private reply to that comment, once;
- a dead token flags THAT channel, never the tenant's WhatsApp credential.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from nexus_channels.base import SendResult, SendStatus
from nexus_worker.streams.outbound import _drain_tenant
from sqlalchemy import select, update

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    ConversationStatus,
    Customer,
    Message,
    MessageDirection,
    MessageStatus,
    Tenant,
    TenantPlan,
    TenantStatus,
)

pytestmark = pytest.mark.asyncio

IG_ID = "17841400000000099"
IGSID = "530000000000099"


@dataclass
class Recording:
    provider: str = "meta_instagram"
    channel_type: str = "instagram"
    text_calls: list[dict[str, Any]] = field(default_factory=list)

    async def send_text(self, **kwargs: Any) -> SendResult:
        self.text_calls.append(kwargs)
        return SendResult(provider_message_id=f"mid.{len(self.text_calls)}", status=SendStatus.SENT)


@dataclass
class DeadToken:
    provider: str = "meta_instagram"
    channel_type: str = "instagram"

    async def send_text(self, **kwargs: Any) -> SendResult:
        from nexus_channels.whatsapp_meta.exceptions import TokenInvalidatedError

        raise TokenInvalidatedError("token invalidated", status_code=401, code=190)


@pytest_asyncio.fixture
async def ig(db_session) -> dict[str, Any]:
    tid = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tid,
            name="IG Window",
            slug=f"ig-{tid.hex[:6]}",
            plan=TenantPlan.PRO,
            status=TenantStatus.ACTIVE,
            owner_phone="+56999990077",
        )
    )
    await db_session.commit()
    channel = Channel(
        tenant_id=tid,
        type=ChannelType.INSTAGRAM,
        provider="meta_instagram",
        provider_identifier=IG_ID,
        status=ChannelStatus.ACTIVE,
        config={"account_id": IG_ID},
    )
    db_session.add(channel)
    await db_session.commit()
    await db_session.refresh(channel)
    customer = Customer(tenant_id=tid, identifier=IGSID, preferences={})
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)
    conv = Conversation(
        tenant_id=tid,
        channel_id=channel.id,
        customer_id=customer.id,
        status=ConversationStatus.OPEN,
    )
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)
    return {"tenant_id": tid, "channel_id": channel.id, "conversation_id": conv.id}


async def _set_last_dm(info: dict[str, Any], ago: timedelta | None) -> None:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, info["tenant_id"]):
        await session.execute(
            update(Conversation)
            .where(Conversation.id == info["conversation_id"])
            .values(last_inbound_at=None if ago is None else datetime.now(UTC) - ago)
        )


async def _inbound(
    info: dict[str, Any], *, provider_message_id: str, context: str | None = None
) -> None:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, info["tenant_id"]):
        session.add(
            Message(
                tenant_id=info["tenant_id"],
                conversation_id=info["conversation_id"],
                direction=MessageDirection.INBOUND,
                status=MessageStatus.DELIVERED,
                content="Price?",
                tool_calls=[],
                provider_message_id=provider_message_id,
                context_message_id=context,
            )
        )


async def _pending(info: dict[str, Any], content: str, *, actor_kind: str = "agent") -> uuid.UUID:
    sm = get_sessionmaker()
    msg = Message(
        tenant_id=info["tenant_id"],
        conversation_id=info["conversation_id"],
        direction=MessageDirection.OUTBOUND,
        status=MessageStatus.PENDING,
        content=content,
        tool_calls=[],
        actor_kind=actor_kind,
    )
    async with sm() as session, tenant_scoped_session(session, info["tenant_id"]):
        session.add(msg)
        await session.flush()
        await session.refresh(msg)
        return msg.id


async def _read(info: dict[str, Any], message_id: uuid.UUID) -> Message:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, info["tenant_id"]):
        return (await session.execute(select(Message).where(Message.id == message_id))).scalar_one()


async def _drain(info: dict[str, Any], adapter: Any) -> None:
    await _drain_tenant(
        get_sessionmaker(), info["tenant_id"], {"meta_instagram": adapter}, batch_size=10
    )


async def test_agent_within_24h_is_a_plain_response(ig):
    await _set_last_dm(ig, timedelta(hours=2))
    rec = Recording()
    msg_id = await _pending(ig, "Abrimos a las 9")

    await _drain(ig, rec)

    assert (await _read(ig, msg_id)).status is MessageStatus.SENT
    [call] = rec.text_calls
    assert call["human_agent"] is False
    assert call["recipient"] == IGSID
    assert call["from_phone"] == IG_ID


async def test_agent_after_24h_is_refused_and_never_tagged(ig):
    await _set_last_dm(ig, timedelta(hours=30))
    rec = Recording()
    msg_id = await _pending(ig, "late")

    await _drain(ig, rec)

    msg = await _read(ig, msg_id)
    assert msg.status is MessageStatus.FAILED
    assert msg.failure_code == "window_closed"
    assert rec.text_calls == []


async def test_person_after_24h_sends_with_human_agent(ig):
    await _set_last_dm(ig, timedelta(days=3))
    rec = Recording()
    msg_id = await _pending(ig, "Soy Ana, del equipo", actor_kind="member")

    await _drain(ig, rec)

    assert (await _read(ig, msg_id)).status is MessageStatus.SENT
    assert rec.text_calls[0]["human_agent"] is True


async def test_nobody_after_7_days(ig):
    await _set_last_dm(ig, timedelta(days=8))
    rec = Recording()
    msg_id = await _pending(ig, "too late", actor_kind="member")

    await _drain(ig, rec)

    assert (await _read(ig, msg_id)).failure_code == "window_closed"
    assert rec.text_calls == []


async def test_answer_to_a_comment_is_one_private_reply(ig):
    await _set_last_dm(ig, None)  # the commenter never wrote a DM
    await _inbound(ig, provider_message_id="comment:C_9", context="comment:C_9")
    rec = Recording()
    first = await _pending(ig, "Te escribimos por privado")

    await _drain(ig, rec)

    sent = await _read(ig, first)
    assert sent.status is MessageStatus.SENT
    assert sent.context_message_id == "comment:C_9"
    assert rec.text_calls[0]["context_message_id"] == "comment:C_9"

    # A second agent answer to the same comment is not another private reply,
    # and without a DM there is no window to send it in.
    second = await _pending(ig, "otra vez")
    await _drain(ig, rec)
    assert (await _read(ig, second)).failure_code == "window_closed"
    assert len(rec.text_calls) == 1


async def test_dead_token_flags_the_channel_not_whatsapp(ig):
    await _set_last_dm(ig, timedelta(hours=1))
    msg_id = await _pending(ig, "hola")

    await _drain(ig, DeadToken())

    msg = await _read(ig, msg_id)
    assert msg.status is MessageStatus.FAILED
    assert msg.failure_code == "token_revoked"
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, ig["tenant_id"]):
        channel = await session.get(Channel, ig["channel_id"])
        assert channel is not None
        assert channel.status is ChannelStatus.DEGRADED
        assert channel.config["needs_attention"] == "token_revoked"


@dataclass
class Refuses:
    """Graph answering a send with a fixed error envelope."""

    code: int
    subcode: int | None = None
    message: str = "refused"
    provider: str = "meta_instagram"
    channel_type: str = "instagram"

    async def send_text(self, **kwargs: Any) -> SendResult:
        from nexus_channels.whatsapp_meta.exceptions import MetaAPIError

        raise MetaAPIError(self.message, status_code=400, code=self.code, subcode=self.subcode)


async def test_graph_refusals_say_what_they_mean(ig):
    """QA 2026-10-30 (INC-22): every refusal left as failure_code "10" and a
    disabled Instagram inbox never marked the channel."""
    await _set_last_dm(ig, timedelta(hours=1))
    window = await _pending(ig, "uno")
    await _drain(ig, Refuses(code=10, subcode=2018278))
    assert (await _read(ig, window)).failure_code == "window_closed"

    gone = await _pending(ig, "dos")
    await _drain(ig, Refuses(code=551))
    assert (await _read(ig, gone)).failure_code == "recipient_gone"

    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, ig["tenant_id"]):
        channel = await session.get(Channel, ig["channel_id"])
        assert channel is not None and channel.status is ChannelStatus.ACTIVE

    off = await _pending(ig, "tres")
    await _drain(ig, Refuses(code=200))
    msg = await _read(ig, off)
    assert msg.status is MessageStatus.FAILED and msg.failure_code == "messages_disabled"
    async with sm() as session, tenant_scoped_session(session, ig["tenant_id"]):
        channel = await session.get(Channel, ig["channel_id"])
        assert channel is not None
        assert channel.status is ChannelStatus.DEGRADED
        assert channel.config["needs_attention"] == "messages_disabled"
