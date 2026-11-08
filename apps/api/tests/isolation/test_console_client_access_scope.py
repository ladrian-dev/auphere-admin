"""Spec 056, T028 — el acceso del cliente desde la consola de partners, aislado
(garantía 1 y C8; requisitos 3.10, 4.1 y 4.2; ``contracts/api.md``).

Las cinco rutas de ``/console/clients/{ref}/client-access`` y
``…/client-members`` ya entran solas en el barrido de ``test_console_scope.py``
(sin ``tenant_id`` ni ``partner_id``, el 404 opaco con un ``ref`` ajeno, todas
exigen principal). Lo que este archivo añade, propio de estas rutas:

- **El id de una persona de otro cliente no existe**, aunque el ``ref`` sea el
  propio: el mismo 404, byte a byte, que un id inventado. Vale para un cliente de
  otro partner y para una vecina del mismo partner.
- **Solo owner y admin** (D4): builder, analyst y billing reciben 403 en las
  cinco, antes de leer nada.
- **Nada de la Bandeja** (4.2, C8): ni conversaciones, ni contactos, ni el texto
  de los avisos, aunque el cliente tenga la Bandeja llena. El riesgo aceptado en
  D3 (una persona invitada por el partner lee la Bandeja) es de la consola lite,
  no de estas rutas.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from nexus_api.db.models import ConsoleNotification, PartnerTenant, Tenant, TenantPlan
from tests.conftest import add_client_member, add_console_member, make_client_access, make_inbox

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

#: Las cinco rutas del partner, con un cuerpo válido para que el 403 o el 404 sea
#: el de la regla y no un 422.
ROUTES: list[tuple[str, str, dict[str, Any] | None]] = [
    ("GET", "/console/clients/{ref}/client-access", None),
    ("PUT", "/console/clients/{ref}/client-access", {"enabled": False, "modules": []}),
    ("POST", "/console/clients/{ref}/client-members", {"email": "x@example.com"}),
    ("POST", "/console/clients/{ref}/client-members/{member_id}/resend", None),
    ("POST", "/console/clients/{ref}/client-members/{member_id}/revoke", None),
]

NOTICE_TEXT = "Contacto 0 pregunta por su pedido"


def _url(path: str, ref: str, member_id: uuid.UUID | str | None = None) -> str:
    return path.replace("{ref}", ref).replace("{member_id}", str(member_id or uuid.uuid4()))


async def test_the_five_routes_are_mounted() -> None:
    from tests.isolation.test_console_scope import _console_routes

    mounted = {
        (m, r.path)
        for r in _console_routes()
        if r.path.startswith("/console/clients/{ref}/client-")
        for m in r.methods
    }
    assert mounted == {(m, p) for m, p, _ in ROUTES}


@pytest.mark.parametrize("action", ["resend", "revoke"])
async def test_a_person_of_another_client_is_the_same_404(
    action: str, client, db_session, console_world
) -> None:
    """3.10: con el ``ref`` propio, la persona de otro partner o de una vecina del
    mismo partner responde igual que un id que no existe."""
    a, b = console_world["a"], console_world["b"]
    await make_client_access(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
    await make_client_access(db_session, partner_id=b["partner_id"], tenant_id=b["tenant_id"])
    theirs = await add_client_member(
        db_session, partner_id=b["partner_id"], tenant_id=b["tenant_id"]
    )
    neighbour = uuid.uuid4()
    db_session.add(
        Tenant(
            id=neighbour,
            name="Vecina",
            slug=f"vecina-{neighbour.hex[:6]}",
            plan=TenantPlan.PRO,
            partner_id=a["partner_id"],
        )
    )
    await db_session.flush()
    db_session.add(
        PartnerTenant(
            partner_id=a["partner_id"],
            external_client_ref="vecina-1",
            tenant_id=neighbour,
            client_name="Vecina",
        )
    )
    await db_session.commit()
    await make_client_access(db_session, partner_id=a["partner_id"], tenant_id=neighbour)
    next_door = await add_client_member(db_session, partner_id=a["partner_id"], tenant_id=neighbour)

    path = f"/console/clients/{{ref}}/client-members/{{member_id}}/{action}"
    ghost = await client.post(_url(path, a["ref"]), headers=a["headers"]())
    assert ghost.status_code == 404, ghost.text
    for foreign in (theirs["membership_id"], next_door["membership_id"]):
        resp = await client.post(_url(path, a["ref"], foreign), headers=a["headers"]())
        assert resp.status_code == 404, resp.text
        assert resp.content == ghost.content


@pytest.mark.parametrize("role", ["builder", "analyst", "billing"])
@pytest.mark.parametrize(("method", "path", "body"), ROUTES)
async def test_only_owner_and_admin_manage_the_access(
    role: str,
    method: str,
    path: str,
    body: dict[str, Any] | None,
    client,
    db_session,
    console_world,
) -> None:
    """D4 y 3.2: invitar a alguien a los datos de un negocio es de quien gestiona
    la cuenta. Los demás roles reciben 403 y nada cambia."""
    a = console_world["a"]
    await make_client_access(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
    person = await add_client_member(
        db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"]
    )
    member = await add_console_member(db_session, partner_id=a["partner_id"], role=role)
    resp = await client.request(
        method,
        _url(path, a["ref"], person["membership_id"]),
        headers=member["headers"](),
        json=body,
    )
    assert resp.status_code == 403, f"{role} {method} {path}: {resp.status_code} {resp.text}"
    after = await client.get(_url(ROUTES[0][1], a["ref"]), headers=a["headers"]())
    assert after.json()["enabled"] is True
    assert {m["status"] for m in after.json()["members"]} == {"active"}


@pytest.mark.parametrize("role", ["owner", "admin"])
async def test_owner_and_admin_read_it(role: str, client, db_session, console_world) -> None:
    a = console_world["a"]
    headers = a["headers"]
    if role == "admin":
        headers = (await add_console_member(db_session, partner_id=a["partner_id"], role=role))[
            "headers"
        ]
    resp = await client.get(_url(ROUTES[0][1], a["ref"]), headers=headers())
    assert resp.status_code == 200, resp.text


async def test_nothing_of_the_inbox_comes_back(client, db_session, console_world) -> None:
    """4.2 (C8): con la Bandeja llena y un aviso que nombra al contacto, ninguna
    respuesta de estas rutas trae conversaciones, contactos ni el texto del aviso."""
    a = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
    db_session.add(
        ConsoleNotification(
            partner_id=a["partner_id"],
            external_client_ref=a["ref"],
            kind="inbox.waiting",
            payload={"contact": "Contacto 0", "preview": NOTICE_TEXT},
            audience="client",
        )
    )
    await db_session.commit()
    canaries = [
        "Contacto 0",
        "Contacto 1",
        "Hola, soy el contacto",
        "¿en qué te ayudo?",
        NOTICE_TEXT,
        "+54911",
        *(str(c) for c in inbox["conversations"]),
        *(str(c) for c in inbox["customers"]),
        str(a["tenant_id"]),
        str(a["partner_id"]),
    ]

    responses = [
        await client.get(_url(ROUTES[0][1], a["ref"]), headers=a["headers"]()),
        await client.put(
            _url(ROUTES[1][1], a["ref"]),
            headers=a["headers"](),
            json={"enabled": True, "modules": ["panel", "inbox", "usage"]},
        ),
    ]
    invited = await client.post(
        _url(ROUTES[2][1], a["ref"]), headers=a["headers"](), json={"email": "ana@negocio.test"}
    )
    responses.append(invited)
    invitation = invited.json()["id"]
    responses.append(
        await client.post(_url(ROUTES[3][1], a["ref"], invitation), headers=a["headers"]())
    )
    responses.append(
        await client.post(
            _url(ROUTES[4][1], a["ref"], inbox["member"]["membership_id"]), headers=a["headers"]()
        )
    )
    for resp in responses:
        assert resp.status_code in (200, 201), resp.text
        leaked = [c for c in canaries if c in resp.text]
        assert not leaked, f"{resp.request.method} {resp.request.url.path}: {leaked}"
        assert "partner" not in resp.json(), "la salida del partner no lleva ``partner``"
