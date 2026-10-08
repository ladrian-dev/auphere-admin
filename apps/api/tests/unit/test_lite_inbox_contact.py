"""Spec 030 T077 — el panel de contacto (Requisito 13 y 16.1).

- el resumen y el motivo salen del último escalado; sin escalado, nada;
- «primer mensaje» y «conversaciones» cuentan todo lo del contacto: sus filas
  y las veces que volvió a escribir tras resolverla;
- la actividad va de lo más reciente a lo más antiguo;
- las etiquetas se limpian (sin vacíos, sin duplicados sin distinguir
  mayúsculas, ≤ 20 de ≤ 40 caracteres) y las sugerencias son las del cliente;
- la nota interna es del contacto, ≤ 4.000 caracteres, y la auditoría guarda
  su longitud, nunca su texto.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from nexus_api.db.models import (
    AuditLog,
    Conversation,
    ConversationEvent,
    ConversationStatus,
    Message,
    MessageDirection,
    MessageStatus,
)
from tests.conftest import make_inbox

pytestmark = pytest.mark.asyncio

BASE = "/console/lite/inbox/conversations"


async def _detail(client, inbox, conversation_id) -> dict:
    r = await client.get(f"{BASE}/{conversation_id}", headers=inbox["headers"]())
    assert r.status_code == 200, r.text
    return r.json()


async def test_summary_and_reason_come_from_the_last_escalation(
    client, db_session, console_world
) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    c0 = inbox["conversations"][0]
    assert (await _detail(client, inbox, c0))["summary"] is None

    now = datetime.now(UTC)
    for i, (reason, summary) in enumerate(
        [("Primera duda", "Resumen viejo"), ("Pide un reembolso", "Compró el lunes")]
    ):
        db_session.add(
            ConversationEvent(
                tenant_id=w["tenant_id"],
                conversation_id=c0,
                kind="escalated",
                actor="agent",
                payload={"reason": reason, "customer_summary": summary},
                created_at=now - timedelta(minutes=10 - i),
            )
        )
    await db_session.execute(
        sa.update(Conversation)
        .where(Conversation.id == c0)
        .values(status=ConversationStatus.ESCALATED)
    )
    await db_session.commit()

    d = await _detail(client, inbox, c0)
    assert d["summary"] == "Compró el lunes"
    assert d["waiting_reason"] == "Pide un reembolso"
    assert [a["kind"] for a in d["activity"]] == ["escalated", "escalated"]
    assert d["activity"][0]["at"] > d["activity"][1]["at"]

    assert (
        await client.post(f"{BASE}/{c0}/resolve", headers=inbox["headers"]())
    ).status_code == 200
    d = await _detail(client, inbox, c0)
    assert d["waiting_reason"] is None  # ya no espera
    assert d["summary"] == "Compró el lunes"
    assert d["activity"][0]["kind"] == "resolved"
    assert d["activity"][0]["actor"]["is_me"] is True


async def test_the_contact_counts_everything_of_theirs(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    c0, customer = inbox["conversations"][0], inbox["customers"][0]
    old_at = datetime.now(UTC) - timedelta(days=40)
    old = Conversation(
        id=uuid.uuid4(),
        tenant_id=w["tenant_id"],
        channel_id=inbox["channel_id"],
        customer_id=customer,
        status=ConversationStatus.CLOSED,
        last_message_at=old_at,
    )
    db_session.add(old)
    await db_session.flush()
    db_session.add_all(
        [
            Message(
                tenant_id=w["tenant_id"],
                conversation_id=old.id,
                direction=MessageDirection.INBOUND,
                status=MessageStatus.DELIVERED,
                content="la primera vez",
                created_at=old_at,
            ),
            ConversationEvent(
                tenant_id=w["tenant_id"],
                conversation_id=c0,
                kind="reopened",
                actor="contact",
                payload={},
            ),
        ]
    )
    await db_session.commit()

    contact = (await _detail(client, inbox, c0))["contact"]
    assert contact["name"] == "Contacto 0"
    assert contact["conversations"] == 3  # dos filas + una vez que volvió
    assert contact["first_message_at"].startswith(old_at.date().isoformat())


async def test_tags_are_cleaned_and_suggested_per_client(client, db_session, console_world) -> None:
    a, b = console_world["a"], console_world["b"]
    inbox = await make_inbox(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
    other = await make_inbox(db_session, partner_id=b["partner_id"], tenant_id=b["tenant_id"])
    c0, c1 = inbox["conversations"]
    put = f"{BASE}/{c0}/tags"

    r = await client.put(
        put,
        headers=inbox["headers"](),
        json={"tags": ["  VIP ", "vip", "", "   ", "Reembolso", "x" * 50]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["tags"] == ["VIP", "Reembolso", "x" * 40]
    too_many = await client.put(
        put, headers=inbox["headers"](), json={"tags": [f"t{i}" for i in range(21)]}
    )
    assert too_many.status_code == 422

    await client.put(f"{BASE}/{c1}/tags", headers=inbox["headers"](), json={"tags": ["VIP"]})
    await client.put(
        f"{BASE}/{other['conversations'][0]}/tags",
        headers=other["headers"](),
        json={"tags": ["De otro cliente"]},
    )
    suggested = (await client.get("/console/lite/inbox/tags", headers=inbox["headers"]())).json()
    assert suggested["tags"][0] == "VIP"
    assert "De otro cliente" not in suggested["tags"]

    r = await client.put(put, headers=inbox["headers"](), json={"tags": ["VIP"]})
    assert r.json()["tags"] == ["VIP"]
    actions = (
        await db_session.execute(
            sa.select(AuditLog.action, AuditLog.after_json)
            .where(AuditLog.tenant_id == a["tenant_id"], AuditLog.action.like("inbox.%tagged"))
            .order_by(AuditLog.created_at)
        )
    ).all()
    assert ("inbox.untagged", {"tags": ["Reembolso", "x" * 40]}) in actions
    assert actions[0] == ("inbox.tagged", {"tags": sorted(["VIP", "Reembolso", "x" * 40])})


async def test_the_note_belongs_to_the_contact_and_is_never_audited(
    client, db_session, console_world
) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    c0 = inbox["conversations"][0]
    text = "Prefiere que le llamen por la tarde. Alérgico al látex."

    r = await client.put(f"{BASE}/{c0}/note", headers=inbox["headers"](), json={"body": text})
    assert r.status_code == 200, r.text
    assert r.json()["body"] == text
    assert r.json()["updated_at"]

    # La nota es del contacto: la ve otra conversación suya.
    second = Conversation(
        id=uuid.uuid4(),
        tenant_id=w["tenant_id"],
        channel_id=inbox["channel_id"],
        customer_id=inbox["customers"][0],
        status=ConversationStatus.CLOSED,
    )
    db_session.add(second)
    await db_session.commit()
    assert (await _detail(client, inbox, second.id))["note"]["body"] == text

    long = await client.put(
        f"{BASE}/{c0}/note", headers=inbox["headers"](), json={"body": "x" * 4001}
    )
    assert long.status_code == 422

    (row,) = (
        await db_session.execute(
            sa.select(AuditLog).where(
                AuditLog.tenant_id == w["tenant_id"], AuditLog.action == "inbox.note_saved"
            )
        )
    ).scalars()
    assert row.after_json == {"length": len(text)}
    assert "látex" not in str(row.after_json)
