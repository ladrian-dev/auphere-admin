"""Spec 031 · R8.2, R8.3, R8.5, R9.3, R11.2 — el reparto de un aviso (T085).

``push_fanout.claim`` calcula los destinatarios **en el momento de repartir** y
compone el aviso con los datos de ese momento; ``settle`` anota lo que pasó.
Lo que se fija aquí, con un cliente con Bandeja y varios teléfonos:

- el aviso de espera va a todos los teléfonos activos con el tipo encendido;
- un teléfono sin destino, con el tipo apagado o de una persona quitada no
  recibe nada, y la entrega dice por qué;
- un mensaje para quien atiende solo va a sus teléfonos, y si ya no la atiende,
  a nadie;
- un escalado que alguien ya tomó no avisa (``no_longer_true``);
- una entrega por evento y teléfono, aunque el evento se reparta dos veces;
- lo transitorio se reintenta con espera creciente, como mucho cinco veces;
- un destino que Apple o Google dan de baja se quita del teléfono.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker

from nexus_api.db.models import (
    ClientMembership,
    ClientPhone,
    ClientPushDelivery,
    ClientPushEvent,
    Conversation,
    ConversationStatus,
)
from nexus_api.services import push_events, push_fanout
from tests.conftest import add_client_member, add_client_phone, make_inbox

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture
def identity(test_engine) -> async_sessionmaker:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False)


async def _with_token(db_session, phone_id: uuid.UUID, token: str, provider: str = "apns") -> None:
    await db_session.execute(
        sa.update(ClientPhone)
        .where(ClientPhone.id == phone_id)
        .values(
            push_provider=provider,
            push_token=token,
            push_token_updated_at=datetime.now(UTC),
            apns_environment="sandbox" if provider == "apns" else None,
        )
    )
    await db_session.commit()


@pytest.fixture
async def shop(db_session, console_world) -> dict[str, Any]:
    w = console_world["a"]
    box = await make_inbox(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"], conversations=2
    )
    second = await add_client_member(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"]
    )
    valeria_ios = await add_client_phone(db_session, membership_id=box["member"]["membership_id"])
    valeria_android = await add_client_phone(
        db_session, membership_id=box["member"]["membership_id"], platform="android"
    )
    marcos = await add_client_phone(db_session, membership_id=second["membership_id"])
    await _with_token(db_session, valeria_ios["phone_id"], "a" * 64)
    await _with_token(db_session, valeria_android["phone_id"], "fcm-valeria", provider="fcm")
    await _with_token(db_session, marcos["phone_id"], "b" * 64)
    conv = box["conversations"][0]
    await db_session.execute(
        sa.update(Conversation)
        .where(Conversation.id == conv)
        .values(status=ConversationStatus.ESCALATED, agent_active=False, assigned_user_id=None)
    )
    await db_session.commit()
    return {
        "w": w,
        "box": box,
        "second": second,
        "valeria_ios": valeria_ios,
        "valeria_android": valeria_android,
        "marcos": marcos,
        "conv": conv,
    }


async def _enqueue(db_session, tenant_id, **kw: Any) -> None:
    async with db_session.begin():
        await push_events.enqueue(db_session, tenant_id=tenant_id, **kw)


async def _claim(scoped_session_factory, identity, tenant_id, **kw: Any) -> list[Any]:
    session = await scoped_session_factory(tenant_id)
    try:
        out = await push_fanout.claim(session, identity, **kw)
        await session.commit()
        return out
    finally:
        await session.close()


async def _settle(scoped_session_factory, identity, tenant_id, results, **kw: Any) -> None:
    session = await scoped_session_factory(tenant_id)
    try:
        await push_fanout.settle(session, identity, results, **kw)
        await session.commit()
    finally:
        await session.close()


async def _deliveries(db_session, tenant_id) -> dict[uuid.UUID, ClientPushDelivery]:
    db_session.expire_all()
    rows = (
        await db_session.scalars(
            sa.select(ClientPushDelivery).where(ClientPushDelivery.tenant_id == tenant_id)
        )
    ).all()
    return {d.phone_id: d for d in rows}


async def test_waiting_goes_to_every_active_phone_with_the_kind_on(
    db_session, scoped_session_factory, identity, shop
) -> None:
    tid = shop["w"]["tenant_id"]
    await _enqueue(
        db_session, tid, kind="inbox.waiting", conversation_id=shop["conv"], dedupe_key="w:1"
    )

    out = await _claim(scoped_session_factory, identity, tid)

    phones = {o.phone_id for o in out}
    assert phones == {
        shop["valeria_ios"]["phone_id"],
        shop["valeria_android"]["phone_id"],
        shop["marcos"]["phone_id"],
    }
    notice = out[0].notice
    assert notice.kind == "inbox.waiting"
    assert notice.title == "Contacto 0 espera a una persona"
    assert notice.url == f"auphere-customers://inbox/{shop['conv']}"
    assert notice.badge >= 1


async def test_skips_say_why(db_session, scoped_session_factory, identity, shop) -> None:
    tid = shop["w"]["tenant_id"]
    await db_session.execute(
        sa.update(ClientPhone)
        .where(ClientPhone.id == shop["valeria_android"]["phone_id"])
        .values(notice_kinds=["client.balance"])
    )
    await db_session.execute(
        sa.update(ClientPhone)
        .where(ClientPhone.id == shop["marcos"]["phone_id"])
        .values(push_token=None, push_provider=None)
    )
    await db_session.commit()
    await _enqueue(
        db_session, tid, kind="inbox.waiting", conversation_id=shop["conv"], dedupe_key="w:2"
    )

    out = await _claim(scoped_session_factory, identity, tid)

    assert [o.phone_id for o in out] == [shop["valeria_ios"]["phone_id"]]
    d = await _deliveries(db_session, tid)
    assert d[shop["valeria_android"]["phone_id"]].skip_reason == "kind_disabled"
    assert d[shop["marcos"]["phone_id"]].skip_reason == "no_push_token"


async def test_a_removed_person_gets_nothing(
    db_session, scoped_session_factory, identity, shop
) -> None:
    tid = shop["w"]["tenant_id"]
    await db_session.execute(
        sa.update(ClientMembership)
        .where(ClientMembership.id == shop["second"]["membership_id"])
        .values(status="revoked")
    )
    await db_session.commit()
    await _enqueue(
        db_session, tid, kind="inbox.waiting", conversation_id=shop["conv"], dedupe_key="w:3"
    )

    out = await _claim(scoped_session_factory, identity, tid)

    assert shop["marcos"]["phone_id"] not in {o.phone_id for o in out}


async def test_a_taken_conversation_no_longer_waits(
    db_session, scoped_session_factory, identity, shop
) -> None:
    tid = shop["w"]["tenant_id"]
    await _enqueue(
        db_session, tid, kind="inbox.waiting", conversation_id=shop["conv"], dedupe_key="w:4"
    )
    await db_session.execute(
        sa.update(Conversation)
        .where(Conversation.id == shop["conv"])
        .values(status=ConversationStatus.OPEN, assigned_user_id=shop["second"]["user_id"])
    )
    await db_session.commit()

    out = await _claim(scoped_session_factory, identity, tid)

    assert out == []
    d = await _deliveries(db_session, tid)
    assert {x.skip_reason for x in d.values()} == {"no_longer_true"}
    status = await db_session.scalar(
        sa.select(ClientPushEvent.status).where(ClientPushEvent.dedupe_key == "w:4")
    )
    assert status == "fanned_out"


async def test_a_message_goes_only_to_whoever_handles_it(
    db_session, scoped_session_factory, identity, shop
) -> None:
    tid = shop["w"]["tenant_id"]
    me = shop["box"]["member"]["user_id"]
    await db_session.execute(
        sa.update(Conversation)
        .where(Conversation.id == shop["conv"])
        .values(status=ConversationStatus.OPEN, agent_active=False, assigned_user_id=me)
    )
    await db_session.commit()
    await _enqueue(
        db_session,
        tid,
        kind="inbox.message_for_you",
        conversation_id=shop["conv"],
        target_principal_id=me,
        dedupe_key="m:1",
    )

    out = await _claim(scoped_session_factory, identity, tid)

    assert {o.phone_id for o in out} == {
        shop["valeria_ios"]["phone_id"],
        shop["valeria_android"]["phone_id"],
    }
    assert out[0].notice.title == "Contacto 0"


async def test_one_delivery_per_event_and_phone(
    db_session, scoped_session_factory, identity, shop
) -> None:
    tid = shop["w"]["tenant_id"]
    await _enqueue(
        db_session, tid, kind="inbox.waiting", conversation_id=shop["conv"], dedupe_key="w:5"
    )
    first = await _claim(scoped_session_factory, identity, tid)
    # Se pasa el plazo sin que nadie liquide: otra vuelta lo vuelve a tomar.
    later = datetime.now(UTC) + push_fanout.LEASE + timedelta(seconds=1)
    second = await _claim(scoped_session_factory, identity, tid, now=later)

    assert {o.delivery_id for o in first} == {o.delivery_id for o in second}
    rows = (
        await db_session.scalars(
            sa.select(ClientPushDelivery).where(ClientPushDelivery.tenant_id == tid)
        )
    ).all()
    assert len(rows) == 3


async def test_the_lease_keeps_another_replica_out(
    db_session, scoped_session_factory, identity, shop
) -> None:
    tid = shop["w"]["tenant_id"]
    await _enqueue(
        db_session, tid, kind="inbox.waiting", conversation_id=shop["conv"], dedupe_key="w:6"
    )
    assert await _claim(scoped_session_factory, identity, tid)
    assert await _claim(scoped_session_factory, identity, tid) == []


async def test_transient_failures_retry_with_backoff_then_fail(
    db_session, scoped_session_factory, identity, shop
) -> None:
    tid = shop["w"]["tenant_id"]
    await _enqueue(
        db_session, tid, kind="inbox.waiting", conversation_id=shop["conv"], dedupe_key="w:7"
    )
    ts = datetime.now(UTC)
    for attempt in range(1, push_fanout.MAX_ATTEMPTS + 1):
        out = await _claim(scoped_session_factory, identity, tid, now=ts)
        assert out, f"attempt {attempt} claimed nothing"
        results = [
            push_fanout.Result(
                delivery_id=o.delivery_id,
                event_id=o.event_id,
                phone_id=o.phone_id,
                outcome="retry",
                error_code="503",
            )
            for o in out
        ]
        await _settle(scoped_session_factory, identity, tid, results, now=ts)
        db_session.expire_all()
        event = await db_session.scalar(
            sa.select(ClientPushEvent).where(ClientPushEvent.dedupe_key == "w:7")
        )
        if attempt < push_fanout.MAX_ATTEMPTS:
            assert event.status == "pending"
            assert event.next_attempt_at == ts + push_fanout.backoff(attempt)
            ts = event.next_attempt_at
    assert event.status == "failed"
    d = await _deliveries(db_session, tid)
    assert {x.status for x in d.values()} == {"failed"}


async def test_sent_and_unregistered_are_settled(
    db_session, scoped_session_factory, identity, shop
) -> None:
    tid = shop["w"]["tenant_id"]
    await _enqueue(
        db_session, tid, kind="inbox.waiting", conversation_id=shop["conv"], dedupe_key="w:8"
    )
    out = await _claim(scoped_session_factory, identity, tid)
    gone = shop["marcos"]["phone_id"]
    results = [
        push_fanout.Result(
            delivery_id=o.delivery_id,
            event_id=o.event_id,
            phone_id=o.phone_id,
            outcome="unregistered" if o.phone_id == gone else "sent",
            provider_message_id=None if o.phone_id == gone else "apns-1",
            error_code="Unregistered" if o.phone_id == gone else None,
        )
        for o in out
    ]

    await _settle(scoped_session_factory, identity, tid, results)

    d = await _deliveries(db_session, tid)
    assert d[gone].status == "failed"
    assert d[shop["valeria_ios"]["phone_id"]].status == "sent"
    assert d[shop["valeria_ios"]["phone_id"]].sent_at is not None
    token = await db_session.scalar(sa.select(ClientPhone.push_token).where(ClientPhone.id == gone))
    assert token is None
    status = await db_session.scalar(
        sa.select(ClientPushEvent.status).where(ClientPushEvent.dedupe_key == "w:8")
    )
    assert status == "fanned_out"


async def test_the_sweep_finds_tenants_with_due_work(db_session, identity, shop) -> None:
    tid = shop["w"]["tenant_id"]
    await _enqueue(
        db_session, tid, kind="inbox.waiting", conversation_id=shop["conv"], dedupe_key="w:9"
    )
    async with identity() as s:
        assert tid in await push_fanout.tenants_with_pending(s)


# ── spec 045 ─────────────────────────────────────────────────────────────


async def test_a_conversation_the_agent_never_attended_never_notifies(
    db_session, scoped_session_factory, identity, shop
) -> None:
    """R2.4: lo que la Bandeja no enseña no avisa."""
    tid = shop["w"]["tenant_id"]
    await db_session.execute(
        sa.update(Conversation).where(Conversation.id == shop["conv"]).values(attended_at=None)
    )
    await db_session.commit()
    await _enqueue(
        db_session, tid, kind="inbox.waiting", conversation_id=shop["conv"], dedupe_key="w:q1"
    )

    out = await _claim(scoped_session_factory, identity, tid)

    assert out == []
    assert {x.skip_reason for x in (await _deliveries(db_session, tid)).values()} == {
        "no_longer_true"
    }


async def _closed_all_week(db_session, tenant_id) -> None:
    from nexus_api.db.models import Tenant

    days = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    await db_session.execute(
        sa.update(Tenant)
        .where(Tenant.id == tenant_id)
        .values(business_hours={d: [] for d in days}, timezone="America/Santiago")
    )
    await db_session.commit()


async def test_quiet_hours_hold_back_what_is_not_urgent(
    db_session, scoped_session_factory, identity, shop
) -> None:
    """R5.3 y R5.4: fuera de horario, el mensaje para quien atiende no sale a
    un teléfono con el silencio puesto; a uno sin silencio, sí."""
    tid = shop["w"]["tenant_id"]
    me = shop["box"]["member"]["user_id"]
    await _closed_all_week(db_session, tid)
    await db_session.execute(
        sa.update(ClientPhone)
        .where(ClientPhone.id == shop["valeria_android"]["phone_id"])
        .values(quiet_outside_hours=False)
    )
    await db_session.execute(
        sa.update(Conversation)
        .where(Conversation.id == shop["conv"])
        .values(status=ConversationStatus.OPEN, agent_active=False, assigned_user_id=me)
    )
    await db_session.commit()
    await _enqueue(
        db_session,
        tid,
        kind="inbox.message_for_you",
        conversation_id=shop["conv"],
        target_principal_id=me,
        dedupe_key="m:q1",
    )

    out = await _claim(scoped_session_factory, identity, tid)

    assert {o.phone_id for o in out} == {shop["valeria_android"]["phone_id"]}
    d = await _deliveries(db_session, tid)
    assert d[shop["valeria_ios"]["phone_id"]].skip_reason == "quiet_hours"


async def test_quiet_hours_never_hold_back_a_waiting_conversation(
    db_session, scoped_session_factory, identity, shop
) -> None:
    tid = shop["w"]["tenant_id"]
    await _closed_all_week(db_session, tid)
    await _enqueue(
        db_session, tid, kind="inbox.waiting", conversation_id=shop["conv"], dedupe_key="w:q2"
    )

    out = await _claim(scoped_session_factory, identity, tid)

    assert {o.phone_id for o in out} == {
        shop["valeria_ios"]["phone_id"],
        shop["valeria_android"]["phone_id"],
        shop["marcos"]["phone_id"],
    }


# ── Spec 047 (T170, events.md §3.1): la bolsa, el agente y sus números ─────


async def test_the_bag_and_the_agent_reach_the_phone_with_their_screen(
    db_session, scoped_session_factory, identity, shop
) -> None:
    from nexus_api.db.models import ConsoleNotification, NotificationAudience
    from nexus_api.services.channel_config import announce
    from tests.integration.clients._client_world import add_agent

    tid = shop["w"]["tenant_id"]
    agent = await add_agent(db_session, tid, "Ventas")
    await db_session.commit()
    await announce(
        tenant_id=tid,
        kind="client.wallet.empty",
        severity="critical",
        data={"balance_micros": 0, "currency": "USD"},
        dedupe_key="wallet:1",
        to_client=True,
    )
    await announce(
        tenant_id=tid,
        kind="agent.paused",
        data={"agent_id": str(agent["agent_id"]), "origin": "console"},
        to_client=True,
        to_partner=False,
    )
    async with db_session.begin():
        rows = (
            await db_session.scalars(
                sa.select(ConsoleNotification).where(
                    ConsoleNotification.partner_id == shop["w"]["partner_id"],
                    ConsoleNotification.kind.in_(["client.wallet.empty", "agent.paused"]),
                )
            )
        ).all()
    audiences = sorted((r.kind, r.audience) for r in rows)
    assert audiences == [
        ("agent.paused", NotificationAudience.CLIENT.value),
        ("client.wallet.empty", NotificationAudience.CLIENT.value),
        ("client.wallet.empty", NotificationAudience.PARTNER.value),
    ], "la pausa del partner va solo al cliente; la bolsa, a los dos"

    out = await _claim(scoped_session_factory, identity, tid)
    by_kind = {o.notice.kind: o.notice for o in out}
    wallet, agents = by_kind["client.balance"], by_kind["agents.state"]
    assert wallet.url == "auphere-customers://usage"
    assert wallet.title == "Te quedaste sin saldo"
    assert agents.url == f"auphere-customers://agents/{agent['agent_id']}"
    assert agents.title == "Agente en pausa" and "Ventas" in agents.body
