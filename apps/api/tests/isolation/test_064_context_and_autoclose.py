"""Spec 064 — garantías 8 y 1 en el ciclo de una conversación.

**Garantía 8** (requisito 4.7): el contexto que el agente lee en un turno es
solo el del contacto de ese turno. El corte de una conversación resuelta quita
mensajes de ese contacto; nunca mete los de otro, ni su nombre. Dos contactos
del mismo negocio son filas legítimas del mismo cliente: la RLS no los separa.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.runtime.pipeline import _load_recent_history

from nexus_api.db.models import Conversation, Customer, Message, MessageDirection, MessageStatus
from nexus_api.services import inbox_lifecycle
from tests.conftest import make_inbox

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]


async def _conv(db_session: Any, cid: uuid.UUID) -> Conversation:
    db_session.expire_all()
    row = await db_session.get(Conversation, cid)
    assert row is not None
    return row


async def _inbound(db_session: Any, conv: Conversation, text: str) -> None:
    db_session.add(
        Message(
            id=uuid.uuid4(),
            tenant_id=conv.tenant_id,
            conversation_id=conv.id,
            direction=MessageDirection.INBOUND,
            status=MessageStatus.DELIVERED,
            content=text,
        )
    )
    await db_session.commit()


async def test_the_context_of_a_turn_is_only_that_contacts(db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    a_id, b_id = inbox["conversations"]
    # (Cada lectura caduca lo anterior de la sesión: los ids se apuntan al leer.)
    ana = (await _conv(db_session, a_id)).customer_id
    bruno = (await _conv(db_session, b_id)).customer_id
    await db_session.execute(sa.update(Customer).where(Customer.id == ana).values(name="Ana"))
    await db_session.execute(sa.update(Customer).where(Customer.id == bruno).values(name="Bruno"))
    await db_session.commit()

    def texts(history: list[dict[str, str]]) -> str:
        return " | ".join(m["content"] for m in history)

    # Antes del corte: cada uno lee lo suyo.
    before_a = texts(await _load_recent_history(w["tenant_id"], str(a_id)))
    assert "contacto 0" in before_a and "contacto 1" not in before_a

    # Se resuelve la de Ana, y Ana vuelve.
    a = await _conv(db_session, a_id)
    assert await inbox_lifecycle.resolve(db_session, a, actor="client:dueña@salon.es")
    await db_session.commit()
    a = await _conv(db_session, a_id)
    assert await inbox_lifecycle.reopen(db_session, a, actor="contact")
    await db_session.commit()
    await _inbound(db_session, await _conv(db_session, a_id), "hola, soy Ana otra vez")
    await _inbound(db_session, await _conv(db_session, b_id), "y yo soy Bruno, con otra duda")

    after_a = await _load_recent_history(w["tenant_id"], str(a_id))
    said = texts(after_a)
    # Nada de Bruno, ni su nombre, ni lo de Ana anterior al corte.
    assert "Bruno" not in said and "contacto 1" not in said
    assert "contacto 0" not in said
    assert "hola, soy Ana otra vez" in said
    assert after_a[-1]["content"].endswith("<client_name>\nAna\n</client_name>")
    assert after_a[-1]["role"] == "system"

    # Y a Bruno el corte de Ana no le toca: lee su hilo entero, sin nota.
    after_b = await _load_recent_history(w["tenant_id"], str(b_id))
    assert "contacto 1" in texts(after_b) and "y yo soy Bruno, con otra duda" in texts(after_b)
    assert "Ana" not in texts(after_b)
    assert all(m["role"] != "system" for m in after_b)

    # Desde otro cliente, la conversación de Ana no existe.
    other = console_world["b"]["tenant_id"]
    assert await _load_recent_history(other, str(a_id)) == []


# ── garantía 1 (requisito 5.8): el plazo de cierre es de cada cliente ────────
#
# ``client_access`` lleva RLS FORCE. El ajuste se lee y se escribe en la sesión
# del cliente de la petición, y el cierre recorre cada cliente en la suya.

SETTINGS = "/console/lite/inbox/settings"


async def _term(db_session: Any, tenant_id: uuid.UUID) -> int | None:
    from nexus_api.db.models import ClientAccess

    db_session.expire_all()
    return await db_session.scalar(
        sa.select(ClientAccess.inbox_autoclose_hours).where(ClientAccess.tenant_id == tenant_id)
    )


async def _two_inboxes(db_session: Any, console_world: dict[str, Any]) -> tuple[Any, Any]:
    a, b = console_world["a"], console_world["b"]
    inbox_a = await make_inbox(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
    inbox_b = await make_inbox(db_session, partner_id=b["partner_id"], tenant_id=b["tenant_id"])
    return inbox_a, inbox_b


async def test_a_client_never_reads_or_sets_anothers_term(
    client, db_session, console_world
) -> None:
    a, b = console_world["a"], console_world["b"]
    inbox_a, inbox_b = await _two_inboxes(db_session, console_world)

    assert (
        await client.patch(SETTINGS, headers=inbox_a["headers"](), json={"autoclose_hours": 24})
    ).status_code == 200
    assert await _term(db_session, a["tenant_id"]) == 24
    assert await _term(db_session, b["tenant_id"]) is None
    # B lee lo suyo, no lo de A.
    assert (await client.get(SETTINGS, headers=inbox_b["headers"]())).json() == {
        "autoclose_hours": None
    }
    # Y no hay forma de nombrar a otro cliente: ni en el cuerpo ni en la ruta.
    for extra in ({"tenant_id": str(b["tenant_id"])}, {"client": b["slug"]}):
        r = await client.patch(
            SETTINGS, headers=inbox_a["headers"](), json={"autoclose_hours": 72, **extra}
        )
        assert r.status_code == 422, r.text
    r = await client.patch(
        f"{SETTINGS}?tenant_id={b['tenant_id']}",
        headers=inbox_a["headers"](),
        json={"autoclose_hours": 72},
    )
    assert r.status_code == 200
    assert await _term(db_session, a["tenant_id"]) == 72  # se guardó en A, que es quien pide
    assert await _term(db_session, b["tenant_id"]) is None


async def test_one_clients_term_never_closes_anothers_conversations(
    db_session, console_world
) -> None:
    from datetime import UTC, datetime, timedelta

    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.base import get_sessionmaker
    from nexus_api.db.models import ClientAccess, ConversationStatus

    a, b = console_world["a"], console_world["b"]
    inbox_a, inbox_b = await _two_inboxes(db_session, console_world)
    await db_session.execute(
        sa.update(ClientAccess)
        .where(ClientAccess.tenant_id == a["tenant_id"])
        .values(inbox_autoclose_hours=24)
    )
    # Todas las conversaciones, de los dos, llevan un mes en silencio.
    await db_session.execute(
        sa.update(Conversation).values(last_message_at=datetime.now(UTC) - timedelta(days=30))
    )
    await db_session.commit()

    async def tick(tenant_id: uuid.UUID) -> list[uuid.UUID]:
        async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
            return await inbox_lifecycle.autoclose_tick(s, tenant_id, datetime.now(UTC))

    closed = await tick(a["tenant_id"])
    assert set(closed) == set(inbox_a["conversations"])
    # B no tiene plazo: su pasada no cierra nada, ni lo suyo ni lo de A.
    assert await tick(b["tenant_id"]) == []
    for cid in inbox_b["conversations"]:
        assert (await _conv(db_session, cid)).status == ConversationStatus.OPEN

    # Y aunque alguien llame al cierre de A dentro de la sesión de B, la RLS
    # no le deja ver las conversaciones de A.
    for cid in inbox_a["conversations"]:
        await db_session.execute(
            sa.update(Conversation)
            .where(Conversation.id == cid)
            .values(status=ConversationStatus.OPEN, closed_at=None)
        )
    await db_session.commit()
    async with get_sessionmaker()() as s, tenant_scoped_session(s, b["tenant_id"]):
        seen = await inbox_lifecycle.close_inactive(s, hours=24, now=datetime.now(UTC))
    assert set(seen) == set(inbox_b["conversations"])
    for cid in inbox_a["conversations"]:
        assert (await _conv(db_session, cid)).status == ConversationStatus.OPEN


async def test_the_pass_of_one_client_refuses_to_run_as_another(db_session, console_world) -> None:
    """/cso 2026-11-19: el cierre no se fía solo de la RLS. Un ``tenant_id`` que
    no es el de la sesión se rechaza, y la consulta filtra por el de la sesión."""
    from datetime import UTC, datetime

    from nexus_api.core.errors import IsolationViolation
    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.base import get_sessionmaker

    a, b = console_world["a"], console_world["b"]
    await _two_inboxes(db_session, console_world)
    with pytest.raises(IsolationViolation):
        async with get_sessionmaker()() as s, tenant_scoped_session(s, a["tenant_id"]):
            await inbox_lifecycle.autoclose_tick(s, b["tenant_id"], datetime.now(UTC))
