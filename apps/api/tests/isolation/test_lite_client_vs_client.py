"""Spec 030 — un cliente no ve a otro del mismo partner (R2.3, R17.3).

El eje nuevo que la consola lite abre: hasta hoy nadie podía cruzar de un
cliente a otro **dentro** de un partner, porque solo el partner entraba y los
veía todos a propósito. Ahora entra la persona de un cliente, y sus dos
vecinos legítimos de partner son exactamente lo que no puede ver.

Barrido sobre todas las rutas ``GET`` de ``/console/lite/*``:

- las que no llevan identificador no devuelven ningún nombre ni ref del otro
  cliente;
- las que llevan el identificador de un objeto responden al id de un objeto
  del otro cliente **igual, byte a byte,** que a un id que no existe.

Cada parámetro de ruta lite tiene que saber qué objeto del vecino probar
(``_FOREIGN``); uno nuevo sin entrada pone el barrido en rojo a propósito.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import pytest

from nexus_api.db.models import (
    ConsoleNotification,
    Message,
    MessageDirection,
    MessageStatus,
    PartnerTenant,
    SavedReply,
    Tenant,
    TenantPlan,
)
from tests.conftest import add_client_member, make_client_access, make_inbox
from tests.isolation.test_console_scope import _console_routes

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

NEIGHBOUR_NAME = "Vecina de Partner A"
NEIGHBOUR_REF = "vecina-a-2"


async def _neighbourhood(db_session, console_world) -> dict[str, Any]:
    """Partner A con dos clientes: el de la persona y una vecina."""
    a = console_world["a"]
    neighbour = uuid.uuid4()
    db_session.add(
        Tenant(
            id=neighbour,
            name=NEIGHBOUR_NAME,
            slug=f"vecina-{neighbour.hex[:6]}",
            plan=TenantPlan.PRO,
            partner_id=a["partner_id"],
        )
    )
    await db_session.flush()
    db_session.add(
        PartnerTenant(
            partner_id=a["partner_id"],
            external_client_ref=NEIGHBOUR_REF,
            tenant_id=neighbour,
            client_name=NEIGHBOUR_NAME,
        )
    )
    await db_session.commit()
    for tenant_id in (a["tenant_id"], neighbour):
        await make_client_access(db_session, partner_id=a["partner_id"], tenant_id=tenant_id)
    member = await add_client_member(
        db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"]
    )
    foreign_notice = ConsoleNotification(
        partner_id=a["partner_id"],
        external_client_ref=NEIGHBOUR_REF,
        kind="inbox.waiting",
        payload={"contact": NEIGHBOUR_NAME},
        audience="client",
    )
    db_session.add(foreign_notice)
    await db_session.commit()
    # Spec 030: la Bandeja de la vecina — una conversación con un archivo
    # recibido y una respuesta guardada. Del mismo partner: la vecina más
    # peligrosa, porque todo lo que no sea la RLS del cliente la deja pasar.
    inbox = await make_inbox(
        db_session,
        partner_id=a["partner_id"],
        tenant_id=neighbour,
        conversations=1,
        with_access=False,
    )
    media = Message(
        id=uuid.uuid4(),
        tenant_id=neighbour,
        conversation_id=inbox["conversations"][0],
        direction=MessageDirection.INBOUND,
        status=MessageStatus.DELIVERED,
        content="",
        media_kind="image",
        media_s3_key=f"tenants/{neighbour}/inbound/vecina.jpg",
        media_mime="image/jpeg",
        media_filename="vecina.jpg",
    )
    reply = SavedReply(
        id=uuid.uuid4(), tenant_id=neighbour, title="Horario de la vecina", body="De 9 a 14 h."
    )
    db_session.add_all([media, reply])
    await db_session.commit()
    return {
        "member": member,
        "neighbour": neighbour,
        "notification_id": foreign_notice.id,
        "conversation_id": inbox["conversations"][0],
        "message_id": media.id,
        "reply_id": reply.id,
    }


#: Para cada parámetro de ruta lite: qué objeto de la vecina se prueba.
_FOREIGN: dict[str, Callable[[dict[str, Any]], str]] = {
    "notification_id": lambda w: str(w["notification_id"]),
    "conversation_id": lambda w: str(w["conversation_id"]),
    "message_id": lambda w: str(w["message_id"]),
    "reply_id": lambda w: str(w["reply_id"]),
}


#: La SSE de la Bandeja no termina nunca: un GET aquí esperaría para siempre.
#: Que solo reenvía el canal del cliente de la sesión lo fija
#: ``test_lite_inbox_media_and_stream.py::test_stream_relays_only_its_clients_channel``.
_STREAMS = {"/console/lite/inbox/stream"}


def _lite_gets() -> list[str]:
    return [
        r.path
        for r in _console_routes()
        if r.path.startswith("/console/lite") and "GET" in r.methods and r.path not in _STREAMS
    ]


@pytest.mark.parametrize("path", _lite_gets())
async def test_reads_never_show_the_neighbour(path: str, client, db_session, console_world) -> None:
    world = await _neighbourhood(db_session, console_world)
    headers = world["member"]["headers"]
    params = [seg[1:-1] for seg in path.split("/") if seg.startswith("{")]
    if not params:
        resp = await client.get(path, headers=headers())
        assert resp.status_code == 200, f"{path}: {resp.status_code} {resp.text[:200]}"
        assert NEIGHBOUR_NAME not in resp.text
        assert NEIGHBOUR_REF not in resp.text
        assert str(world["neighbour"]) not in resp.text
        return
    missing = [p for p in params if p not in _FOREIGN]
    assert not missing, f"{path}: no foreign object to probe for {missing}"
    foreign_path, ghost_path = path, path
    for p in params:
        foreign_path = foreign_path.replace("{" + p + "}", _FOREIGN[p](world))
        ghost_path = ghost_path.replace("{" + p + "}", str(uuid.uuid4()))
    foreign = await client.get(foreign_path, headers=headers())
    ghost = await client.get(ghost_path, headers=headers())
    assert foreign.status_code == ghost.status_code == 404, (path, foreign.status_code)
    assert foreign.content == ghost.content


async def test_writes_on_a_neighbour_object_are_the_same_404(
    client, db_session, console_world
) -> None:
    """Las escrituras con id también: marcar leído un aviso de la vecina."""
    world = await _neighbourhood(db_session, console_world)
    headers = world["member"]["headers"]
    foreign = await client.post(
        f"/console/lite/notifications/{world['notification_id']}/read", headers=headers()
    )
    ghost = await client.post(f"/console/lite/notifications/{uuid.uuid4()}/read", headers=headers())
    assert foreign.status_code == ghost.status_code == 404
    assert foreign.content == ghost.content


#: Spec 030: cada escritura de la Bandeja con id, con un cuerpo válido para
#: que el 404 sea el de la RLS y no un 422.
_INBOX_WRITES: list[tuple[str, str, dict[str, Any] | None]] = [
    ("POST", "/console/lite/inbox/conversations/{conversation_id}/read", None),
    ("POST", "/console/lite/inbox/conversations/{conversation_id}/unread", None),
    ("POST", "/console/lite/inbox/conversations/{conversation_id}/takeover", None),
    ("POST", "/console/lite/inbox/conversations/{conversation_id}/release", None),
    ("POST", "/console/lite/inbox/conversations/{conversation_id}/messages", {"text": "hola"}),
    ("POST", "/console/lite/inbox/conversations/{conversation_id}/resolve", None),
    ("POST", "/console/lite/inbox/conversations/{conversation_id}/reopen", None),
    ("PUT", "/console/lite/inbox/conversations/{conversation_id}/tags", {"tags": ["x"]}),
    ("PUT", "/console/lite/inbox/conversations/{conversation_id}/note", {"body": "x"}),
    ("PATCH", "/console/lite/inbox/replies/{reply_id}", {"body": "x"}),
    ("DELETE", "/console/lite/inbox/replies/{reply_id}", None),
]


def test_every_inbox_write_with_an_id_is_probed() -> None:
    """Una escritura nueva de la Bandeja con id sin entrada arriba: rojo."""
    mounted = {
        (sorted(r.methods)[0], r.path)
        for r in _console_routes()
        if r.path.startswith("/console/lite/inbox/")
        and "{" in r.path
        and sorted(r.methods)[0] != "GET"
        and not r.path.endswith("/attachments")  # multipart: probado aparte
    }
    assert mounted == {(m, p) for m, p, _ in _INBOX_WRITES}


@pytest.mark.parametrize(("method", "path", "body"), _INBOX_WRITES)
async def test_inbox_writes_on_a_neighbour_object_are_the_same_404(
    method: str, path: str, body: dict[str, Any] | None, client, db_session, console_world
) -> None:
    world = await _neighbourhood(db_session, console_world)
    headers = world["member"]["headers"]
    param = path.split("{", 1)[1].split("}", 1)[0]
    foreign = await client.request(
        method, path.replace("{" + param + "}", str(world[param])), headers=headers(), json=body
    )
    ghost = await client.request(
        method, path.replace("{" + param + "}", str(uuid.uuid4())), headers=headers(), json=body
    )
    assert foreign.status_code == ghost.status_code == 404, (path, foreign.status_code)
    assert foreign.content == ghost.content


async def test_an_attachment_to_a_neighbour_conversation_is_the_same_404(
    client, db_session, console_world
) -> None:
    world = await _neighbourhood(db_session, console_world)
    headers = world["member"]["headers"]
    files = {"file": ("a.jpg", b"\xff\xd8", "image/jpeg")}
    url = "/console/lite/inbox/conversations/{}/attachments"
    foreign = await client.post(
        url.format(world["conversation_id"]), headers=headers(), files=files
    )
    ghost = await client.post(url.format(uuid.uuid4()), headers=headers(), files=files)
    assert foreign.status_code == ghost.status_code == 404
    assert foreign.content == ghost.content
