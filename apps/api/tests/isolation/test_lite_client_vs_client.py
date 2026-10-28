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
    # Spec 047: con Agentes y Negocio, para que sus rutas entren en el barrido.
    modules = ("panel", "inbox", "usage", "agents", "business")
    for tenant_id in (a["tenant_id"], neighbour):
        await make_client_access(
            db_session, partner_id=a["partner_id"], tenant_id=tenant_id, modules=modules
        )
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
    spec_047 = await _neighbour_spec_047(db_session, neighbour, inbox["conversations"][0], media.id)
    return {
        "member": member,
        "neighbour": neighbour,
        "notification_id": foreign_notice.id,
        "conversation_id": inbox["conversations"][0],
        "message_id": media.id,
        "reply_id": reply.id,
        **spec_047,
    }


async def _neighbour_spec_047(
    db_session, neighbour: uuid.UUID, conversation_id: uuid.UUID, message_id: uuid.UUID
) -> dict[str, uuid.UUID]:
    """Spec 047 (T167, T176): lo de la vecina que las rutas nuevas nombran por id
    — su agente y su número, una sede, una fecha especial, un servicio, un cambio
    de su ficha y una corrección."""
    from datetime import date

    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.models import InboxCorrection, ReservationService
    from nexus_api.db.models.business import (
        BusinessChange,
        BusinessLocation,
        BusinessSpecialDate,
    )
    from tests.integration.clients._client_world import add_agent

    agent = await add_agent(db_session, neighbour, "Agente de la vecina")
    await db_session.commit()
    async with tenant_scoped_session(db_session, neighbour):
        location = BusinessLocation(tenant_id=neighbour, name="Sede de la vecina")
        special = BusinessSpecialDate(
            tenant_id=neighbour,
            name="Festivo de la vecina",
            date_from=date(2026, 12, 25),
            date_to=date(2026, 12, 25),
        )
        service = ReservationService(
            tenant_id=neighbour, name="Servicio de la vecina", duration_minutes=30
        )
        change = BusinessChange(
            tenant_id=neighbour, section="locations", kind="edit", origin="lite_web"
        )
        db_session.add_all([location, special, service, change])
        await db_session.flush()
        correction = InboxCorrection(
            tenant_id=neighbour,
            conversation_id=conversation_id,
            message_id=message_id,
            agent_id=agent["agent_id"],
            author_client_user_id="vecina",
            origin="lite_web",
            scope="business",
            kind="data",
            lesson="Dato de la vecina.",
            status="draft",
        )
        db_session.add(correction)
        await db_session.flush()
        ids = {
            "agent_id": agent["agent_id"],
            "channel_id": agent["channel_id"],
            "location_id": location.id,
            "special_id": special.id,
            "service_id": service.id,
            "change_id": change.id,
            "correction_id": correction.id,
        }
    await db_session.commit()
    return {k: v for k, v in ids.items() if v is not None}


#: Para cada parámetro de ruta lite: qué objeto de la vecina se prueba.
_FOREIGN: dict[str, Callable[[dict[str, Any]], str]] = {
    "notification_id": lambda w: str(w["notification_id"]),
    "conversation_id": lambda w: str(w["conversation_id"]),
    "message_id": lambda w: str(w["message_id"]),
    "reply_id": lambda w: str(w["reply_id"]),
    # Spec 047.
    "agent_id": lambda w: str(w["agent_id"]),
    "channel_id": lambda w: str(w["channel_id"]),
    "location_id": lambda w: str(w["location_id"]),
    "special_id": lambda w: str(w["special_id"]),
    "service_id": lambda w: str(w["service_id"]),
    "change_id": lambda w: str(w["change_id"]),
    "correction_id": lambda w: str(w["correction_id"]),
}


#: La SSE de la Bandeja no termina nunca: un GET aquí esperaría para siempre.
#: Que solo reenvía el canal del cliente de la sesión lo fija
#: ``test_lite_inbox_media_and_stream.py::test_stream_relays_only_its_clients_channel``.
_STREAMS = {"/console/lite/inbox/stream"}

#: Spec 031: rutas que solo tienen sentido desde la app (la web recibe 403
#: ``phone_only``). Se barren con la credencial del teléfono en
#: ``test_phone_route_scope.py``, que importa este mismo vecindario.
PHONE_ONLY = {"/console/lite/phones/current/notices"}


#: Spec 043: Reservas tiene rutas por modo y con rango de fechas; su barrido,
#: en los dos modos y con las dos credenciales, es
#: ``test_reservas_client_vs_client.py``.
RESERVAS_PREFIX = "/console/lite/reservas"


def _lite_gets() -> list[str]:
    return [
        r.path
        for r in _console_routes()
        if r.path.startswith("/console/lite")
        and "GET" in r.methods
        and r.path not in _STREAMS
        and r.path not in PHONE_ONLY
        and not r.path.startswith(RESERVAS_PREFIX)
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
    # Spec 047 (T176): corregir una respuesta del agente.
    (
        "POST",
        "/console/lite/inbox/{conversation_id}/messages/{message_id}/corrections",
        {"text": "El aparcamiento está detrás.", "scope": "business"},
    ),
]

#: Spec 047 (T167, T176): las escrituras nuevas con id fuera de la Bandeja, con un
#: cuerpo válido. Todas llevan ``If-Match`` (las de la ficha y las correcciones lo
#: exigen; las demás lo ignoran).
_LITE_WRITES: list[tuple[str, str, dict[str, Any] | None]] = [
    ("POST", "/console/lite/agents/{agent_id}/pause", {"confirm": True}),
    ("POST", "/console/lite/agents/{agent_id}/resume", None),
    ("POST", "/console/lite/channels/{channel_id}/pause", None),
    ("POST", "/console/lite/channels/{channel_id}/resume", None),
    ("PATCH", "/console/lite/business/special-dates/{special_id}", {"closed": True}),
    ("POST", "/console/lite/business/special-dates/{special_id}/archive", None),
    ("PATCH", "/console/lite/business/services/{service_id}", {"duration_min": 30}),
    ("POST", "/console/lite/business/services/{service_id}/archive", None),
    ("PATCH", "/console/lite/business/locations/{location_id}", {"address": "Calle Mayor 1"}),
    ("POST", "/console/lite/business/locations/{location_id}/archive", None),
    ("POST", "/console/lite/business/locations/{location_id}/restore", None),
    ("POST", "/console/lite/business/history/{change_id}/undo", None),
    ("PATCH", "/console/lite/corrections/{correction_id}", {"paraphrase": "Un cliente pregunta."}),
    ("POST", "/console/lite/corrections/{correction_id}/send", None),
    ("POST", "/console/lite/corrections/{correction_id}/undo", None),
]
_IF_MATCH = {"If-Match": '"1"'}


async def probe_write(
    client,
    world: dict[str, Any],
    headers: Callable[[], dict[str, str]],
    method: str,
    path: str,
    body: Any,
) -> None:
    """La escritura sobre lo de la vecina responde **igual, byte a byte**, que sobre
    un id que no existe. Cada parámetro de la ruta se cambia por su objeto de la
    vecina (o por un id inventado)."""
    params = [seg[1:-1] for seg in path.split("/") if seg.startswith("{")]
    foreign_path, ghost_path = path, path
    for p in params:
        foreign_path = foreign_path.replace("{" + p + "}", str(world[p]))
        ghost_path = ghost_path.replace("{" + p + "}", str(uuid.uuid4()))
    # Los tokens de la consola son de un solo uso: uno por petición.
    foreign = await client.request(
        method, foreign_path, headers={**headers(), **_IF_MATCH}, json=body
    )
    ghost = await client.request(method, ghost_path, headers={**headers(), **_IF_MATCH}, json=body)
    assert foreign.status_code == ghost.status_code, (path, foreign.status_code, ghost.status_code)
    assert foreign.status_code in (404, 412), (path, foreign.status_code, foreign.text[:200])
    assert foreign.content == ghost.content, path


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
    await probe_write(client, world, world["member"]["headers"], method, path, body)


@pytest.mark.parametrize(("method", "path", "body"), _LITE_WRITES)
async def test_lite_writes_on_a_neighbour_object_are_the_same_404(
    method: str, path: str, body: dict[str, Any] | None, client, db_session, console_world
) -> None:
    """Spec 047: pausar el agente o el número de la vecina, tocar su ficha o su
    corrección, igual que tocar algo que no existe."""
    world = await _neighbourhood(db_session, console_world)
    await probe_write(client, world, world["member"]["headers"], method, path, body)


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
