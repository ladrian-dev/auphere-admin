"""Unit tests for the owner backchannel repositories."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from nexus_api.core.tenant_context import tenant_context
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
from nexus_api.repositories import (
    OwnerConsultationRepository,
    OwnerPhoneIndexRepository,
    generate_correlation_id,
)

pytestmark = pytest.mark.asyncio


async def _seed_conversation(session, tenant_id: uuid.UUID) -> uuid.UUID:
    suffix = tenant_id.hex[:8]
    channel = Channel(
        tenant_id=tenant_id,
        type=ChannelType.WHATSAPP,
        provider="ycloud",
        provider_identifier=f"+5697{suffix}",
        status=ChannelStatus.ACTIVE,
    )
    session.add(channel)
    await session.flush()
    customer = Customer(
        tenant_id=tenant_id,
        identifier=f"+5698{suffix}",
        name="customer",
    )
    session.add(customer)
    await session.flush()
    conv = Conversation(
        tenant_id=tenant_id,
        channel_id=channel.id,
        customer_id=customer.id,
        status=ConversationStatus.OPEN,
    )
    session.add(conv)
    await session.flush()
    return conv.id


async def _apply_tenant(session, tenant_id: uuid.UUID) -> None:
    await session.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"),
        {"t": str(tenant_id)},
    )
    await session.execute(text("SET LOCAL ROLE nexus_app"))


@pytest.mark.asyncio
async def test_generate_correlation_id_is_short_and_distinct() -> None:
    ids = {generate_correlation_id() for _ in range(200)}
    assert len(ids) == 200
    assert all(len(i) == 8 for i in ids)


async def test_consultation_create_persists_with_tenant_from_context(
    db_session, seed_tenants
):
    tid = seed_tenants["a"]
    with tenant_context(tid):
        async with db_session.begin():
            await _apply_tenant(db_session, tid)
            conv_id = await _seed_conversation(db_session, tid)
            repo = OwnerConsultationRepository(db_session)
            row = await repo.create(
                conversation_id=conv_id,
                question_text="Pregunta de prueba",
                urgency="normal",
                expected_reply_kind="free_text",
                template_name="auphere_owner_consult",
                template_params={"tenant_name": "Test"},
                context_summary="ctx",
            )
            assert row.tenant_id == tid
            assert row.status == "pending"
            assert row.created_by == "agent"
            assert len(row.correlation_id) == 8


async def test_consultation_count_in_window_filters_by_tenant(
    db_session, seed_tenants
):
    a, b = seed_tenants["a"], seed_tenants["b"]
    now = datetime.now(UTC)
    # Seed 3 rows on A and 5 on B in the last hour. Counter under A
    # should report 3, not 8.
    with tenant_context(a):
        async with db_session.begin():
            await _apply_tenant(db_session, a)
            conv_a = await _seed_conversation(db_session, a)
            for _ in range(3):
                db_session.add(
                    OwnerConsultation(
                        tenant_id=a,
                        conversation_id=conv_a,
                        correlation_id=generate_correlation_id(),
                        asked_at=now,
                        question_text="q",
                        urgency="normal",
                        expected_reply_kind="free_text",
                        template_name="auphere_owner_consult",
                        template_params_json={},
                        status="pending",
                        created_by="agent",
                    )
                )

    with tenant_context(b):
        async with db_session.begin():
            await _apply_tenant(db_session, b)
            conv_b = await _seed_conversation(db_session, b)
            for _ in range(5):
                db_session.add(
                    OwnerConsultation(
                        tenant_id=b,
                        conversation_id=conv_b,
                        correlation_id=generate_correlation_id(),
                        asked_at=now,
                        question_text="q",
                        urgency="normal",
                        expected_reply_kind="free_text",
                        template_name="auphere_owner_consult",
                        template_params_json={},
                        status="pending",
                        created_by="agent",
                    )
                )

    with tenant_context(a):
        async with db_session.begin():
            await _apply_tenant(db_session, a)
            repo = OwnerConsultationRepository(db_session)
            cnt = await repo.count_in_window(since=now - timedelta(hours=1))
            assert cnt == 3


async def test_phone_index_get_phone_for_tenant_returns_active_only(
    db_session, seed_tenants
):
    a = seed_tenants["a"]
    now = datetime.now(UTC)
    async with db_session.begin():
        db_session.add_all(
            [
                OwnerPhoneIndex(
                    phone_e164="+56900000001",
                    tenant_id=a,
                    user_label="old",
                    added_at=now - timedelta(days=10),
                    active=False,
                ),
                OwnerPhoneIndex(
                    phone_e164="+56900000002",
                    tenant_id=a,
                    user_label="active",
                    added_at=now,
                    active=True,
                ),
            ]
        )

    repo = OwnerPhoneIndexRepository(db_session)
    found = await repo.get_phone_for_tenant(a)
    assert found == "+56900000002"


async def test_phone_index_lookup_returns_none_for_unknown(db_session):
    repo = OwnerPhoneIndexRepository(db_session)
    assert await repo.lookup("+99999999999") is None
