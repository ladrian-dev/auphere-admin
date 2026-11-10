"""Spec 031 · R15.1 — un hecho de un cliente nunca avisa a un teléfono de otro (T034).

Dos clientes del mismo partner —el vecino más peligroso, porque todo lo que no
sea el filtro por cliente lo deja pasar—, cada uno con personas y teléfonos. Se
reparten los tres tipos de aviso de A y se comprueba que **ninguna** entrega va
a un teléfono de B. Y la regla de un destino, un dueño: si una fila vieja de A
comparte destino con una nueva de B, el reparto de A no envía a ese destino.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker

from nexus_api.db.models import (
    ClientPhone,
    ClientPushDelivery,
    Conversation,
    ConversationStatus,
    PartnerTenant,
    Tenant,
    TenantPlan,
)
from nexus_api.services import push_events, push_fanout, wallet_alerts
from tests.conftest import add_client_phone, make_inbox

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]


async def _token(db_session, phone_id: uuid.UUID, token: str, at: datetime) -> None:
    await db_session.execute(
        sa.update(ClientPhone)
        .where(ClientPhone.id == phone_id)
        .values(push_provider="apns", push_token=token, push_token_updated_at=at)
    )
    await db_session.commit()


@pytest.fixture
async def two_clients(db_session, console_world) -> dict[str, Any]:
    a = console_world["a"]
    b_tenant = uuid.uuid4()
    db_session.add(
        Tenant(
            id=b_tenant,
            name="Vecina",
            slug=f"vecina-{b_tenant.hex[:6]}",
            plan=TenantPlan.PRO,
            partner_id=a["partner_id"],
        )
    )
    await db_session.flush()
    db_session.add(
        PartnerTenant(
            partner_id=a["partner_id"],
            external_client_ref="vecina-a-2",
            tenant_id=b_tenant,
            client_name="Vecina",
        )
    )
    await db_session.commit()
    box_a = await make_inbox(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
    box_b = await make_inbox(db_session, partner_id=a["partner_id"], tenant_id=b_tenant)
    now = datetime.now(UTC)
    phone_a = await add_client_phone(db_session, membership_id=box_a["member"]["membership_id"])
    phone_b = await add_client_phone(db_session, membership_id=box_b["member"]["membership_id"])
    await _token(db_session, phone_a["phone_id"], "a" * 64, now)
    await _token(db_session, phone_b["phone_id"], "b" * 64, now)
    return {"a": a, "b_tenant": b_tenant, "box_a": box_a, "phone_a": phone_a, "phone_b": phone_b}


async def _fan(scoped_session_factory, identity, tenant_id) -> list[Any]:
    session = await scoped_session_factory(tenant_id)
    try:
        out = await push_fanout.claim(session, identity)
        await session.commit()
        return out
    finally:
        await session.close()


@pytest.mark.parametrize("kind", ["inbox.waiting", "inbox.message_for_you", "client.balance"])
async def test_a_fact_of_a_never_reaches_a_phone_of_b(
    kind: str, db_session, scoped_session_factory, test_engine, two_clients
) -> None:
    w = two_clients
    tid = w["a"]["tenant_id"]
    conv = w["box_a"]["conversations"][0]
    me = w["box_a"]["member"]["user_id"]
    if kind == "inbox.waiting":
        await db_session.execute(
            sa.update(Conversation)
            .where(Conversation.id == conv)
            .values(status=ConversationStatus.ESCALATED, agent_active=False, assigned_user_id=None)
        )
        await db_session.commit()
        async with db_session.begin():
            await push_events.enqueue(
                db_session, tenant_id=tid, kind=kind, conversation_id=conv, dedupe_key="x"
            )
    elif kind == "inbox.message_for_you":
        await db_session.execute(
            sa.update(Conversation)
            .where(Conversation.id == conv)
            .values(agent_active=False, assigned_user_id=me)
        )
        await db_session.commit()
        async with db_session.begin():
            await push_events.enqueue(
                db_session,
                tenant_id=tid,
                kind=kind,
                conversation_id=conv,
                target_principal_id=me,
                dedupe_key="x",
            )
    else:
        async with db_session.begin():
            await wallet_alerts._emit_client_balance(
                db_session, w["a"]["partner_id"], tid, w["a"]["ref"], "balance_low", days_left=2
            )

    identity = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    out = await _fan(scoped_session_factory, identity, tid)

    assert out, "the event reached nobody: the sweep would pass for the wrong reason"
    assert {o.phone_id for o in out} == {w["phone_a"]["phone_id"]}
    assert all(o.token == "a" * 64 for o in out)
    leaked = await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(ClientPushDelivery)
        .where(ClientPushDelivery.phone_id == w["phone_b"]["phone_id"])
    )
    assert leaked == 0


async def test_a_stale_phone_of_a_does_not_send_to_a_token_now_owned_by_b(
    db_session, scoped_session_factory, test_engine, two_clients
) -> None:
    w = two_clients
    tid = w["a"]["tenant_id"]
    shared = "c" * 64
    await _token(
        db_session, w["phone_a"]["phone_id"], shared, datetime.now(UTC) - timedelta(days=3)
    )
    await _token(db_session, w["phone_b"]["phone_id"], shared, datetime.now(UTC))
    conv = w["box_a"]["conversations"][0]
    await db_session.execute(
        sa.update(Conversation)
        .where(Conversation.id == conv)
        .values(status=ConversationStatus.ESCALATED, agent_active=False, assigned_user_id=None)
    )
    await db_session.commit()
    async with db_session.begin():
        await push_events.enqueue(
            db_session, tenant_id=tid, kind="inbox.waiting", conversation_id=conv, dedupe_key="y"
        )

    identity = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    out = await _fan(scoped_session_factory, identity, tid)

    assert out == []
    db_session.expire_all()
    token_a = await db_session.scalar(
        sa.select(ClientPhone.push_token).where(ClientPhone.id == w["phone_a"]["phone_id"])
    )
    token_b = await db_session.scalar(
        sa.select(ClientPhone.push_token).where(ClientPhone.id == w["phone_b"]["phone_id"])
    )
    assert token_a is None and token_b == shared
