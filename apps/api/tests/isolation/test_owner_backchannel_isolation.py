"""Owner backchannel isolation — ADR-018 garantías 1, 2 y 4 (the three
Phase 1 tests called out in ``architecture/owner-backchannel.md`` §8).

1. ``test_owner_inbound_routes_to_correct_tenant`` — when the webhook
   resolves the ``from`` phone via ``owner_phone_index`` and applies
   ``app.tenant_id`` for the tenant that owns that phone, RLS keeps
   downstream reads off the *other* tenant's rows.
2. ``test_owner_orphan_message_does_not_leak`` — an owner with NO open
   consultations on their tenant does not accidentally surface another
   tenant's open consultation when the webhook fetches "the latest open
   one".
3. ``test_owner_phone_index_uniqueness`` — registering the same E.164
   for a second tenant raises ``IntegrityError``; the first mapping
   stays intact.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from nexus_api.db.models import (
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    ConversationStatus,
    Customer,
    OwnerConsultation,
    OwnerPhoneIndex,
)

from .conftest import set_tenant

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]


async def _seed_tenant_world(session, tenant_id: uuid.UUID, slug: str) -> dict[str, uuid.UUID]:
    """Create the minimum entities a consultation needs for a tenant:
    channel, customer, conversation. Returns the FK ids."""
    await set_tenant(session, tenant_id)
    channel = Channel(
        tenant_id=tenant_id,
        type=ChannelType.WHATSAPP,
        provider="ycloud",
        provider_identifier=f"+5690000{slug}",
        status=ChannelStatus.ACTIVE,
    )
    session.add(channel)
    await session.flush()
    customer = Customer(
        tenant_id=tenant_id,
        identifier=f"+5691111{slug}",
        name=f"customer-{slug}",
    )
    session.add(customer)
    await session.flush()
    conversation = Conversation(
        tenant_id=tenant_id,
        channel_id=channel.id,
        customer_id=customer.id,
        status=ConversationStatus.OPEN,
    )
    session.add(conversation)
    await session.flush()
    return {
        "channel_id": channel.id,
        "customer_id": customer.id,
        "conversation_id": conversation.id,
    }


async def test_owner_inbound_routes_to_correct_tenant(db_session, tenants_ab):
    """End-to-end of the webhook discovery step:

    - Register owner A's phone → tenant A.
    - Register owner B's phone → tenant B.
    - Open one consultation in each tenant.
    - Resolve A's phone, switch RLS to tenant A, query
      ``owner_consultations``: only A's row is visible. B's row is
      filtered by RLS.
    """
    a, b = tenants_ab["a"], tenants_ab["b"]

    async with db_session.begin():
        worlds = {"a": await _seed_tenant_world(db_session, a, "AA")}

    async with db_session.begin():
        worlds["b"] = await _seed_tenant_world(db_session, b, "BB")

    # Register both owner phones (global table, no RLS).
    async with db_session.begin():
        db_session.add_all(
            [
                OwnerPhoneIndex(
                    phone_e164="+56911111111",
                    tenant_id=a,
                    user_label="Owner A",
                    added_at=datetime.now(UTC),
                    active=True,
                ),
                OwnerPhoneIndex(
                    phone_e164="+56922222222",
                    tenant_id=b,
                    user_label="Owner B",
                    added_at=datetime.now(UTC),
                    active=True,
                ),
            ]
        )

    async with db_session.begin():
        await set_tenant(db_session, a)
        db_session.add(
            OwnerConsultation(
                tenant_id=a,
                conversation_id=worlds["a"]["conversation_id"],
                correlation_id="AAAAAAAA",
                asked_at=datetime.now(UTC),
                question_text="A pregunta?",
                urgency="normal",
                expected_reply_kind="free_text",
                template_name="auphere_owner_consult",
                template_params_json={},
                status="pending",
                created_by="agent",
            )
        )

    async with db_session.begin():
        await set_tenant(db_session, b)
        db_session.add(
            OwnerConsultation(
                tenant_id=b,
                conversation_id=worlds["b"]["conversation_id"],
                correlation_id="BBBBBBBB",
                asked_at=datetime.now(UTC),
                question_text="B pregunta?",
                urgency="normal",
                expected_reply_kind="free_text",
                template_name="auphere_owner_consult",
                template_params_json={},
                status="pending",
                created_by="agent",
            )
        )

    # Webhook step 1: resolve the sender — global lookup, no tenant scope.
    sender = "+56911111111"
    async with db_session.begin():
        idx = await db_session.get(OwnerPhoneIndex, sender)
        assert idx is not None
        assert idx.tenant_id == a

    # Webhook step 2: switch to tenant A and read consultations. Only A
    # should be visible.
    async with db_session.begin():
        await set_tenant(db_session, idx.tenant_id)
        rows = (
            await db_session.execute(select(OwnerConsultation))
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].correlation_id == "AAAAAAAA"
        assert rows[0].tenant_id == a


async def test_owner_orphan_message_does_not_leak(db_session, tenants_ab):
    """Owner A writes free text. Tenant A has NO open consultations, but
    tenant B does. The webhook's "latest open" fallback must NOT cross
    tenants — when scoped to A, the lookup returns no row even though
    B's consultation is open.
    """
    a, b = tenants_ab["a"], tenants_ab["b"]

    async with db_session.begin():
        await _seed_tenant_world(db_session, b, "OB")

    # Open consultation only on tenant B.
    async with db_session.begin():
        await set_tenant(db_session, b)
        worlds_b = (
            await db_session.execute(select(Conversation))
        ).scalars().all()
        conversation_b_id = worlds_b[0].id
        db_session.add(
            OwnerConsultation(
                tenant_id=b,
                conversation_id=conversation_b_id,
                correlation_id="ZZZZZZZZ",
                asked_at=datetime.now(UTC),
                question_text="B pregunta?",
                urgency="normal",
                expected_reply_kind="free_text",
                template_name="auphere_owner_consult",
                template_params_json={},
                status="sent",
                sent_at=datetime.now(UTC),
                created_by="agent",
            )
        )

    # Owner A is registered but has no open consultation on A.
    async with db_session.begin():
        db_session.add(
            OwnerPhoneIndex(
                phone_e164="+56911111111",
                tenant_id=a,
                added_at=datetime.now(UTC),
                active=True,
            )
        )

    # Webhook step: resolve A, scope to A, look up open consultations.
    async with db_session.begin():
        idx = await db_session.get(OwnerPhoneIndex, "+56911111111")
        assert idx is not None and idx.tenant_id == a
        await set_tenant(db_session, idx.tenant_id)
        rows = (
            await db_session.execute(
                select(OwnerConsultation).where(
                    OwnerConsultation.status.in_(("pending", "sent"))
                )
            )
        ).scalars().all()
        # The orphan owner must see zero — B's consultation is filtered.
        assert rows == []


async def test_owner_phone_index_uniqueness(db_session, tenants_ab):
    """A single E.164 must NOT be claimable by two tenants. The PK on
    ``phone_e164`` enforces this and the second insert raises
    ``IntegrityError``; the first mapping survives unchanged."""
    a, b = tenants_ab["a"], tenants_ab["b"]

    async with db_session.begin():
        db_session.add(
            OwnerPhoneIndex(
                phone_e164="+56933333333",
                tenant_id=a,
                user_label="Owner A",
                added_at=datetime.now(UTC),
                active=True,
            )
        )

    with pytest.raises(IntegrityError):
        async with db_session.begin():
            db_session.add(
                OwnerPhoneIndex(
                    phone_e164="+56933333333",
                    tenant_id=b,
                    user_label="Owner B (collision)",
                    added_at=datetime.now(UTC),
                    active=True,
                )
            )

    # First mapping survives unchanged after the rollback.
    async with db_session.begin():
        idx = await db_session.get(OwnerPhoneIndex, "+56933333333")
        assert idx is not None
        assert idx.tenant_id == a
        assert idx.user_label == "Owner A"
