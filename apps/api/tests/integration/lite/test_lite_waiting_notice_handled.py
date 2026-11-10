"""Spec 056, T040 — el aviso «espera a una persona» se cierra solo (requisitos 8.1
y 8.2, D8).

Cuando la conversación deja de esperar —alguien la toma, la devuelve al agente,
la resuelve o la elimina, la puerta del turno se abre o el cliente se queda sin
Bandeja—, su aviso ``inbox.waiting`` pasa a atendido (``handled_at``, migración
0227):

- deja de contar en el número de la campana y sigue en la lista, con
  ``handled: true``;
- un escalado nuevo de la misma conversación abre un aviso nuevo, pendiente;
- el aviso de otro cliente del mismo partner no se toca, aunque nombre la misma
  conversación: el ``UPDATE`` filtra por el partner y por el cliente.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.runtime.dispatcher import process_inbound

from nexus_api.core.tenant_context import declare_tenant, tenant_scoped_session
from nexus_api.db.models import ConsoleNotification, Conversation, Customer
from nexus_api.services import client_access, inbox_lifecycle
from tests.conftest import add_client_member, make_client_access, make_inbox

from .._turn_world import RecordingPipeline, conversation_of, make_world, wallet_closed

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

BELL = "/console/lite/notifications"
INBOX = "/console/lite/inbox/conversations"


async def _escalate(db_session: Any, tenant_id: uuid.UUID, conversation_id: uuid.UUID) -> None:
    """Como la herramienta de escalar: la espera en la transacción del turno y
    el aviso después del commit."""
    async with tenant_scoped_session(db_session, tenant_id):
        conv = await db_session.get(Conversation, conversation_id)
        assert conv is not None
        mark = await inbox_lifecycle.mark_waiting(
            db_session, conv, reason="Quiere hablar con alguien", summary=None
        )
    await inbox_lifecycle.announce_waiting(mark)


async def _neighbour(
    db_session: Any, partner_id: uuid.UUID, conversation_id: uuid.UUID
) -> uuid.UUID:
    """Un aviso pendiente de OTRO cliente del mismo partner que nombra la misma
    conversación: solo el cliente lo separa del bueno."""
    row = ConsoleNotification(
        id=uuid.uuid4(),
        partner_id=partner_id,
        external_client_ref="otro-cliente",
        kind="inbox.waiting",
        severity="warning",
        payload={"conversation_id": str(conversation_id)},
        audience="client",
    )
    db_session.add(row)
    await db_session.commit()
    return row.id


async def _unread(client: Any, member: dict[str, Any]) -> int:
    resp = await client.get(f"{BELL}/unread-count", headers=member["headers"]())
    assert resp.status_code == 200, resp.text
    return int(resp.json()["unread"])


async def _handled_at(db_session: Any, notification_id: uuid.UUID) -> Any:
    db_session.expire_all()
    async with db_session.begin():
        return await db_session.scalar(
            sa.select(ConsoleNotification.handled_at).where(
                ConsoleNotification.id == notification_id
            )
        )


async def _drop_the_inbox(
    client: Any, db_session: Any, w: dict[str, Any], _c: Any, _m: Any
) -> None:
    """Auphere (o el partner) quita la Bandeja: las calladas vuelven al agente."""
    async with db_session.begin():
        await declare_tenant(db_session, w["tenant_id"])
        await client_access.set_access(
            db_session,
            w["tenant_id"],
            enabled=True,
            modules=["panel", "usage"],
            actor="operator:tests@auphere.com",
        )


def _route(path: str, expect: int) -> Any:
    async def _call(client: Any, _db: Any, _w: Any, conversation: uuid.UUID, member: Any) -> None:
        resp = await client.post(f"{INBOX}/{conversation}/{path}", headers=member["headers"]())
        assert resp.status_code == expect, resp.text

    return _call


TRANSITIONS = {
    "take_over": _route("takeover", 200),
    "give_back": _route("release", 200),
    "resolve": _route("resolve", 200),
    "archive": _route("archive", 204),
    "release_escalated_for_tenant": _drop_the_inbox,
}


@pytest.mark.parametrize("transition", sorted(TRANSITIONS))
async def test_the_notice_is_handled_when_the_wait_ends(
    transition: str, client: Any, db_session: Any, console_world: dict[str, Any]
) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    member = inbox["member"]
    conversation = inbox["conversations"][0]
    await _escalate(db_session, w["tenant_id"], conversation)
    neighbour = await _neighbour(db_session, w["partner_id"], conversation)
    assert await _unread(client, member) == 1

    await TRANSITIONS[transition](client, db_session, w, conversation, member)

    assert await _unread(client, member) == 0, "lo atendido no cuenta en la campana"
    listed = (await client.get(BELL, headers=member["headers"]())).json()["items"]
    (notice,) = [n for n in listed if n["kind"] == "inbox.waiting"]
    assert notice["handled"] is True, "sigue en la lista, atendido"
    assert await _handled_at(db_session, neighbour) is None, "el otro cliente no se toca"

    if transition == "release_escalated_for_tenant":
        return  # Sin Bandeja, un escalado ya no avisa a nadie.
    await _escalate(db_session, w["tenant_id"], conversation)
    assert await _unread(client, member) == 1, "un escalado nuevo abre un aviso pendiente"
    fresh = [
        n
        for n in (await client.get(BELL, headers=member["headers"]())).json()["items"]
        if n["kind"] == "inbox.waiting"
    ]
    assert sorted(n["handled"] for n in fresh) == [False, True]


async def test_a_nameless_contact_is_named_by_its_number_with_plus(
    client: Any, db_session: Any, console_world: dict[str, Any]
) -> None:
    """Requisito 13.3: sin nombre, el aviso nombra al contacto por su número, y
    en WhatsApp con «+» como en la Bandeja (``inbox_view.display_handle``); Meta
    da el número sin él."""
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    member = inbox["member"]
    conversation = inbox["conversations"][0]
    async with tenant_scoped_session(db_session, w["tenant_id"]):
        customer = await db_session.get(Customer, inbox["customers"][0])
        assert customer is not None
        customer.name = None
        customer.identifier = "34600111222"

    await _escalate(db_session, w["tenant_id"], conversation)

    listed = (await client.get(BELL, headers=member["headers"]())).json()["items"]
    (notice,) = [n for n in listed if n["kind"] == "inbox.waiting"]
    assert notice["data"]["contact"] == "+34600111222"


async def test_the_gate_opening_handles_its_notice(
    client: Any, db_session: Any, console_world: dict[str, Any], monkeypatch: Any
) -> None:
    """``release_reason`` (desde el despachador): sin saldo la conversación espera
    con su aviso; con saldo, el agente vuelve a contestar y el aviso se atiende."""
    a = console_world["a"]
    world = await make_world(db_session, tenant_id=a["tenant_id"])
    await make_client_access(
        db_session,
        partner_id=a["partner_id"],
        tenant_id=a["tenant_id"],
        modules=("panel", "inbox", "usage"),
    )
    member = await add_client_member(
        db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"]
    )

    wallet_closed(monkeypatch)
    await process_inbound(world.event("hola"), pipeline=RecordingPipeline())
    conv = await conversation_of(world)
    neighbour = await _neighbour(db_session, a["partner_id"], conv.id)
    # Sin saldo también avisa «sin saldo» (``client.balance_out``): ese sigue.
    before = await _unread(client, member)

    wallet_closed(monkeypatch, closed=False)
    await process_inbound(world.event("¿ya hay alguien?"), pipeline=RecordingPipeline())

    assert await _unread(client, member) == before - 1
    listed = (await client.get(BELL, headers=member["headers"]())).json()["items"]
    (waiting,) = [n for n in listed if n["kind"] == "inbox.waiting"]
    assert waiting["handled"] is True
    assert await _handled_at(db_session, neighbour) is None
