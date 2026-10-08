"""Spec 030 T018 — los cuerpos de mensaje viven solo en la Bandeja (eje C8).

``test_console_scope`` deja pasar campos de cuerpo bajo
``/console/lite/inbox/*`` (``BODY_ROUTES_PREFIX``) y en ningún otro sitio.
Este archivo fija lo que hace que esa excepción no sea un agujero:

1. **Las rutas que sirven cuerpos son exactamente las de la Bandeja**: se
   recorre el OpenAPI entero sin la excepción y todo lo que expone texto
   libre con nombre de cuerpo está bajo el prefijo.
2. **Solo las alcanza la persona de un cliente con el módulo ``inbox``**:
   un cliente sin el módulo recibe 403 en todas, igual que un miembro del
   partner (``test_lite_route_scope`` cubre al partner en toda ruta lite).

Una ruta nueva de la Bandeja entra en el barrido el día que se monta.
"""

from __future__ import annotations

from typing import Any

import pytest

from nexus_api.main import app
from tests.conftest import add_client_member, make_client_access
from tests.isolation.test_console_scope import (
    ALLOWED_FIELDS_BY_SCHEMA,
    ALLOWED_RESPONSE_FIELDS,
    BODY_ROUTES_PREFIX,
    FORBIDDEN_RESPONSE_FIELDS,
    _console_routes,
    _fill,
    _route_response_fields,
)

pytestmark = [pytest.mark.isolation]

_IDS = {"tenant_id", "tenantid"}


def _inbox_route_ids() -> list[str]:
    return [
        f"{sorted(r.methods)[0]} {r.path}"
        for r in _console_routes()
        if r.path.startswith(BODY_ROUTES_PREFIX)
    ]


def test_the_inbox_is_mounted() -> None:
    assert len(_inbox_route_ids()) >= 15, _inbox_route_ids()


def test_routes_with_bodies_are_exactly_inbox_routes() -> None:
    spec = app.openapi()
    components = spec["components"]["schemas"]
    with_bodies: set[str] = set()
    for route in _console_routes():
        method = sorted(route.methods)[0]
        op = spec["paths"][route.path][method.lower()]
        fields = _route_response_fields(op, components)
        body_like = {
            (owner, prop)
            for owner, prop in fields
            if prop in FORBIDDEN_RESPONSE_FIELDS - ALLOWED_RESPONSE_FIELDS - _IDS
            and (owner, prop) not in ALLOWED_FIELDS_BY_SCHEMA
        }
        if body_like:
            with_bodies.add(f"{method} {route.path}")
    outside = {r for r in with_bodies if not r.split(" ", 1)[1].startswith(BODY_ROUTES_PREFIX)}
    assert not outside, f"bodies outside the Inbox: {sorted(outside)}"
    # Control: el recorrido ve de verdad los cuerpos de la Bandeja.
    assert "GET /console/lite/inbox/conversations/{conversation_id}/messages" in with_bodies
    assert "PUT /console/lite/inbox/conversations/{conversation_id}/note" in with_bodies


@pytest.fixture
async def member_without_inbox(db_session, console_world) -> dict[str, Any]:
    w = console_world["a"]
    await make_client_access(
        db_session,
        partner_id=w["partner_id"],
        tenant_id=w["tenant_id"],
        modules=("panel", "usage"),
    )
    return await add_client_member(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])


@pytest.mark.asyncio
@pytest.mark.parametrize("route_id", _inbox_route_ids())
async def test_a_client_without_the_inbox_reaches_no_inbox_route(
    route_id: str, client, member_without_inbox
) -> None:
    method, path = route_id.split(" ", 1)
    resp = await client.request(
        method, _fill(path, ref="x"), headers=member_without_inbox["headers"](), json={}
    )
    assert resp.status_code == 403, f"{route_id} answered {resp.status_code}: {resp.text[:200]}"
