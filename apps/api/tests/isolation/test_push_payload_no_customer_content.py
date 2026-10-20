"""Spec 031 · R15.4, R9.2 — lo que sale hacia Apple y Google es lo mínimo (T035).

Los avisos son normales: viajan con su título y su texto. Este barrido fija qué
es «lo mínimo»: con datos «canario» en todos los sitios donde hay contenido de
un cliente final —el número del contacto, un mensaje largo, una nota interna,
el nombre de un archivo— se reparten los tres tipos de aviso y se inspecciona
**el payload exacto** de APNs y de FCM:

- solo lleva los campos del contrato (``contracts/push.md``);
- los textos miden 100 caracteres o menos;
- ningún canario aparece, en ningún campo, en ninguna plataforma.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker

from nexus_api.db.models import (
    ClientPhone,
    ContactNote,
    Conversation,
    ConversationEventKind,
    ConversationStatus,
    Customer,
    Message,
    MessageDirection,
    MessageStatus,
)
from nexus_api.services import push_events, push_fanout, push_payloads, wallet_alerts
from tests.conftest import add_client_phone, make_inbox

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

PHONE = "+34 611 222 333"
PHONE_DIGITS = "611222333"
LONG = "CANARIO-MENSAJE " + ("x" * 480)
NOTE = "CANARIO-NOTA-INTERNA"
FILENAME = "CANARIO-ARCHIVO.pdf"

APNS_TOP = {"aps", "body"}
APS_KEYS = {"alert", "sound", "badge", "interruption-level", "category", "thread-id"}
FCM_DATA = {"title", "message", "channelId", "categoryId", "threadIdentifier", "badge", "body"}


def _flat(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _check(notice: push_payloads.Notice) -> None:
    headers, body = push_payloads.apns(notice, topic="com.auphere.customers")
    message = push_payloads.fcm(notice, token="t" * 40)
    assert set(body) == APNS_TOP
    assert set(body["aps"]) == APS_KEYS
    assert set(body["aps"]["alert"]) == {"title", "body"}
    assert set(body["body"]) == {"url", "kind"}
    assert set(message["message"]["data"]) == FCM_DATA
    assert set(json.loads(message["message"]["data"]["body"])) == {"url", "kind"}
    assert len(notice.title) <= 100 and len(notice.body) <= 100
    everything = _flat(headers) + _flat(body) + _flat(message)
    for canary in (PHONE, PHONE_DIGITS, "CANARIO-MENSAJE " + "x" * 120, NOTE, FILENAME):
        assert canary not in everything, f"{canary[:30]!r} leaked into the payload"
    assert "x" * 120 not in everything


@pytest.fixture
async def canaries(db_session, console_world) -> dict[str, Any]:
    w = console_world["a"]
    box = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    conv_id = box["conversations"][0]
    conv = await db_session.get(Conversation, conv_id)
    assert conv is not None
    await db_session.execute(
        sa.update(Customer)
        .where(Customer.id == conv.customer_id)
        .values(name=PHONE, identifier=PHONE)
    )
    db_session.add(
        Message(
            id=uuid.uuid4(),
            tenant_id=w["tenant_id"],
            conversation_id=conv_id,
            direction=MessageDirection.INBOUND,
            status=MessageStatus.DELIVERED,
            content=f"Escríbeme al {PHONE}. " + LONG,
            media_kind="document",
            media_filename=FILENAME,
            created_at=datetime.now(UTC),
        )
    )
    db_session.add(ContactNote(tenant_id=w["tenant_id"], customer_id=conv.customer_id, body=NOTE))
    await db_session.commit()
    phone = await add_client_phone(db_session, membership_id=box["member"]["membership_id"])
    await db_session.execute(
        sa.update(ClientPhone)
        .where(ClientPhone.id == phone["phone_id"])
        .values(push_provider="apns", push_token="a" * 64, push_token_updated_at=datetime.now(UTC))
    )
    await db_session.commit()
    return {"w": w, "box": box, "conv": conv_id}


@pytest.mark.parametrize("kind", ["inbox.waiting", "inbox.message_for_you", "client.balance"])
@pytest.mark.parametrize("locale", ["es", "en"])
async def test_the_payload_is_the_minimum(
    kind: str, locale: str, db_session, scoped_session_factory, test_engine, canaries
) -> None:
    w, conv = canaries["w"], canaries["conv"]
    tid = w["tenant_id"]
    me = canaries["box"]["member"]["user_id"]
    await db_session.execute(
        sa.update(ClientPhone).where(ClientPhone.tenant_id == tid).values(locale=locale)
    )
    if kind == "inbox.waiting":
        await db_session.execute(
            sa.update(Conversation)
            .where(Conversation.id == conv)
            .values(status=ConversationStatus.ESCALATED, agent_active=False, assigned_user_id=None)
        )
        await db_session.commit()
        async with db_session.begin():
            from nexus_api.services import inbox_lifecycle

            c = await db_session.get(Conversation, conv)
            await inbox_lifecycle.record_event(
                db_session,
                c,
                ConversationEventKind.ESCALATED,
                "agent",
                {"reason": f"Llamar al {PHONE} " + LONG},
            )
            await push_events.enqueue(
                db_session, tenant_id=tid, kind=kind, conversation_id=conv, dedupe_key="z"
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
                dedupe_key="z",
            )
    else:
        await db_session.commit()
        async with db_session.begin():
            await wallet_alerts._emit_client_balance(
                db_session, w["partner_id"], tid, w["ref"], "balance_out"
            )

    identity = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    session = await scoped_session_factory(tid)
    try:
        out = await push_fanout.claim(session, identity)
        await session.commit()
    finally:
        await session.close()

    assert out, "nothing to inspect: the sweep would pass for the wrong reason"
    for o in out:
        _check(o.notice)
