"""Spec 082 (Historia 4): el resumen del agente no se queda congelado.

El panel del contacto enseña el resumen del último escalado solo si:

- no hay un ``resolved`` posterior (4.1);
- el escalado no es anterior a ``conversation.context_from`` (4.2);
- un escalado nuevo trae el suyo (4.3).

Y, de la Historia 5, el detalle trae el nombre de usuario de WhatsApp (5.4).

Sin modelo: es una comparación de fechas en ``inbox_view.detail`` (4.4).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from nexus_api.db.models import Conversation, ConversationEvent, ConversationStatus, Customer
from tests.conftest import make_inbox

pytestmark = pytest.mark.asyncio

BASE = "/console/lite/inbox/conversations"


async def _summary(client, inbox, conversation_id) -> str | None:
    r = await client.get(f"{BASE}/{conversation_id}", headers=inbox["headers"]())
    assert r.status_code == 200, r.text
    summary: str | None = r.json()["summary"]
    return summary


def _event(tenant_id, conversation_id, kind: str, at: datetime, summary: str | None = None):
    payload = {"reason": "Pide un reembolso", "customer_summary": summary} if summary else {}
    return ConversationEvent(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        kind=kind,
        actor="agent" if kind == "escalated" else "user",
        payload=payload,
        created_at=at,
    )


async def test_escalated_then_resolved_has_no_summary(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    c0 = inbox["conversations"][0]
    now = datetime.now(UTC)
    db_session.add(
        _event(w["tenant_id"], c0, "escalated", now - timedelta(minutes=10), "Compró el lunes")
    )
    await db_session.commit()
    assert await _summary(client, inbox, c0) == "Compró el lunes"

    db_session.add(_event(w["tenant_id"], c0, "resolved", now - timedelta(minutes=5)))
    await db_session.commit()
    assert await _summary(client, inbox, c0) is None


async def test_an_escalation_before_context_from_has_no_summary(
    client, db_session, console_world
) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    c0 = inbox["conversations"][0]
    now = datetime.now(UTC)
    db_session.add(
        _event(w["tenant_id"], c0, "escalated", now - timedelta(hours=2), "De la vez anterior")
    )
    # The conversation started again an hour ago: what came before is not its context.
    await db_session.execute(
        sa.update(Conversation)
        .where(Conversation.id == c0)
        .values(context_from=now - timedelta(hours=1))
    )
    await db_session.commit()
    assert await _summary(client, inbox, c0) is None


async def test_a_new_escalation_brings_its_own_summary(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    c0 = inbox["conversations"][0]
    now = datetime.now(UTC)
    db_session.add_all(
        [
            _event(w["tenant_id"], c0, "escalated", now - timedelta(minutes=30), "Resumen viejo"),
            _event(w["tenant_id"], c0, "resolved", now - timedelta(minutes=20)),
            _event(
                w["tenant_id"],
                c0,
                "escalated",
                now - timedelta(minutes=10),
                "Quiere cambiar la cita",
            ),
        ]
    )
    await db_session.execute(
        sa.update(Conversation)
        .where(Conversation.id == c0)
        .values(status=ConversationStatus.ESCALATED)
    )
    await db_session.commit()
    assert await _summary(client, inbox, c0) == "Quiere cambiar la cita"


async def test_the_detail_carries_the_whatsapp_username(client, db_session, console_world) -> None:
    """5.4: el panel y la cabecera enseñan «@usuario»; la API lo da en ``contact``."""
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    c0, c1 = inbox["conversations"][0], inbox["conversations"][1]
    await db_session.execute(
        sa.update(Customer).where(Customer.id == inbox["customers"][0]).values(username="ana.rz")
    )
    await db_session.commit()

    with_name = await client.get(f"{BASE}/{c0}", headers=inbox["headers"]())
    assert with_name.status_code == 200, with_name.text
    assert with_name.json()["contact"]["username"] == "ana.rz"

    without = await client.get(f"{BASE}/{c1}", headers=inbox["headers"]())
    assert without.status_code == 200, without.text
    assert without.json()["contact"]["username"] is None
