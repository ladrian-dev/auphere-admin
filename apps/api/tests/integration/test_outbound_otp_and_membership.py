"""Spec 077 · R4.6 y R9.2 — el despachador con códigos y con membresía.

- Un código sale con el cuerpo posicional y el botón, y al terminar el envío
  la fila ya no lo guarda.
- Un cliente cuya membresía no está activa no envía plantillas: lo encolado se
  marca fallido con ``membership_inactive`` (no se retiene), y una respuesta de
  agente (texto) no se toca.
- Sin membresía, todo sale como hoy.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from nexus_channels.base import SendResult, SendStatus
from nexus_worker.streams.outbound import (
    REDACTED_CODE,
    _drain_tenant,
    _expire_codes_of_undrained_tenants,
)
from sqlalchemy import select

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
    ServiceMembership,
    Tenant,
    TenantPlan,
    TenantStatus,
)

pytestmark = pytest.mark.asyncio

_CODE = "482913"


@dataclass
class RecordingAdapter:
    provider: str = "meta"
    channel_type: str = "whatsapp"
    template_calls: list[dict[str, Any]] = field(default_factory=list)
    text_calls: list[dict[str, Any]] = field(default_factory=list)

    async def send_template(self, **kwargs: Any) -> SendResult:
        self.template_calls.append(kwargs)
        return SendResult(provider_message_id=f"wamid.{uuid.uuid4().hex}", status=SendStatus.SENT)

    async def send_text(self, **kwargs: Any) -> SendResult:
        self.text_calls.append(kwargs)
        return SendResult(provider_message_id=f"wamid.{uuid.uuid4().hex}", status=SendStatus.SENT)


@pytest_asyncio.fixture
async def tenant(db_session) -> dict[str, Any]:
    tid = uuid.uuid4()
    phone = f"+3463{tid.int % 10_000_000:07d}"
    db_session.add(
        Tenant(
            id=tid,
            name="Tecfin",
            slug=f"tf-{tid.hex[:6]}",
            plan=TenantPlan.PRO,
            status=TenantStatus.ACTIVE,
            send_only=True,
        )
    )
    await db_session.commit()
    channel = Channel(
        tenant_id=tid,
        type=ChannelType.WHATSAPP,
        provider="meta",
        provider_identifier=phone,
        status=ChannelStatus.ACTIVE,
    )
    db_session.add(channel)
    await db_session.commit()
    await db_session.refresh(channel)
    customer = Customer(tenant_id=tid, identifier="56911112223", preferences={})
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
    return {"tenant_id": tid, "conversation_id": conv.id}


def _otp_payload() -> dict[str, Any]:
    return {
        "name": "tecfin_codigo",
        "language": "es",
        "category": "AUTHENTICATION",
        "otp": True,
        "params": {
            "body": [_CODE],
            "buttons": [{"sub_type": "url", "parameters": [{"type": "text", "text": _CODE}]}],
        },
    }


async def _seed(info: dict[str, Any], *, template_payload: dict[str, Any] | None) -> uuid.UUID:
    msg = Message(
        tenant_id=info["tenant_id"],
        conversation_id=info["conversation_id"],
        direction=MessageDirection.OUTBOUND,
        status=MessageStatus.PENDING,
        content="[template:tecfin_codigo]" if template_payload else "hola",
        tool_calls=[],
        actor_kind="system" if template_payload else "agent",
        template_payload=template_payload,
    )
    async with get_sessionmaker()() as session, tenant_scoped_session(session, info["tenant_id"]):
        session.add(msg)
        await session.flush()
        await session.refresh(msg)
        return msg.id


async def _membership(info: dict[str, Any], **values: Any) -> None:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, info["tenant_id"]):
        session.add(ServiceMembership(tenant_id=info["tenant_id"], amount_cents=4000, **values))


async def _read(info: dict[str, Any], message_id: uuid.UUID) -> Message:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, info["tenant_id"]):
        return (await session.execute(select(Message).where(Message.id == message_id))).scalar_one()


async def test_code_goes_in_body_and_button_and_is_wiped_after(tenant) -> None:
    adapter = RecordingAdapter()
    msg_id = await _seed(tenant, template_payload=_otp_payload())

    await _drain_tenant(get_sessionmaker(), tenant["tenant_id"], {"meta": adapter}, batch_size=10)

    assert len(adapter.template_calls) == 1
    params = adapter.template_calls[0]["params"]
    assert params["body"] == [_CODE]
    assert params["buttons"][0]["parameters"][0]["text"] == _CODE
    stored = await _read(tenant, msg_id)
    assert stored.status is MessageStatus.SENT
    assert _CODE not in str(stored.template_payload)
    assert stored.template_payload["params"]["body"] == [REDACTED_CODE]


async def test_inactive_membership_fails_queued_templates_and_spares_text(tenant) -> None:
    adapter = RecordingAdapter()
    await _membership(tenant, payer="stripe", status="past_due")
    otp_id = await _seed(tenant, template_payload=_otp_payload())
    text_id = await _seed(tenant, template_payload=None)

    await _drain_tenant(get_sessionmaker(), tenant["tenant_id"], {"meta": adapter}, batch_size=10)

    otp = await _read(tenant, otp_id)
    assert otp.status is MessageStatus.FAILED
    assert otp.failure_code == "membership_inactive"
    assert _CODE not in str(otp.template_payload)
    assert adapter.template_calls == []
    text = await _read(tenant, text_id)
    assert text.status is MessageStatus.SENT
    assert len(adapter.text_calls) == 1


async def test_wallet_membership_with_expired_period_blocks(tenant) -> None:
    adapter = RecordingAdapter()
    await _membership(
        tenant,
        payer="partner_wallet",
        status="active",
        current_period_end=datetime.now(UTC) - timedelta(minutes=1),
    )
    otp_id = await _seed(tenant, template_payload=_otp_payload())

    await _drain_tenant(get_sessionmaker(), tenant["tenant_id"], {"meta": adapter}, batch_size=10)

    assert (await _read(tenant, otp_id)).failure_code == "membership_inactive"


async def test_active_membership_sends(tenant) -> None:
    adapter = RecordingAdapter()
    await _membership(
        tenant,
        payer="stripe",
        status="active",
        current_period_end=datetime.now(UTC) + timedelta(days=20),
    )
    otp_id = await _seed(tenant, template_payload=_otp_payload())

    await _drain_tenant(get_sessionmaker(), tenant["tenant_id"], {"meta": adapter}, batch_size=10)

    assert (await _read(tenant, otp_id)).status is MessageStatus.SENT


async def test_no_membership_sends_as_today(tenant) -> None:
    adapter = RecordingAdapter()
    named = {
        "name": "newair_instalacion_recordatorio",
        "language": "es",
        "params": {"body": {"nombre": "Juan"}},
        "category": "MARKETING",
    }
    msg_id = await _seed(tenant, template_payload=named)

    await _drain_tenant(get_sessionmaker(), tenant["tenant_id"], {"meta": adapter}, batch_size=10)

    stored = await _read(tenant, msg_id)
    assert stored.status is MessageStatus.SENT
    # A non-code template keeps its variables untouched.
    assert stored.template_payload == named


async def test_a_code_that_waited_too_long_is_not_sent(tenant) -> None:
    """Security review (LOW): after an outage, a stale code is useless."""
    adapter = RecordingAdapter()
    stale = {**_otp_payload(), "queued_at": (datetime.now(UTC) - timedelta(minutes=11)).isoformat()}
    msg_id = await _seed(tenant, template_payload=stale)

    await _drain_tenant(get_sessionmaker(), tenant["tenant_id"], {"meta": adapter}, batch_size=10)

    stored = await _read(tenant, msg_id)
    assert stored.failure_code == "code_expired"
    assert adapter.template_calls == []
    assert _CODE not in str(stored.template_payload)


async def test_a_paused_clients_stale_code_is_wiped_too(tenant, db_session) -> None:
    """/cso 2026-11-24 (R4.9): the drain only visits active clients, so the
    sweep fails and wipes the stale codes of the others; a fresh one waits."""
    from sqlalchemy import update

    stale = {**_otp_payload(), "queued_at": (datetime.now(UTC) - timedelta(minutes=11)).isoformat()}
    fresh = {**_otp_payload(), "queued_at": datetime.now(UTC).isoformat()}
    stale_id = await _seed(tenant, template_payload=stale)
    fresh_id = await _seed(tenant, template_payload=fresh)
    await db_session.execute(
        update(Tenant).where(Tenant.id == tenant["tenant_id"]).values(status=TenantStatus.PAUSED)
    )
    await db_session.commit()

    wiped = await _expire_codes_of_undrained_tenants(get_sessionmaker(), active=[])

    assert wiped >= 1
    old = await _read(tenant, stale_id)
    assert (old.status, old.failure_code) == (MessageStatus.FAILED, "code_expired")
    assert _CODE not in str(old.template_payload)
    new = await _read(tenant, fresh_id)
    assert new.status is MessageStatus.PENDING
