"""Spec 031 · R15.5 — la credencial del teléfono solo abre ``/console/lite`` (T031).

Barrido sobre **todas** las rutas de la consola que no son lite y sobre todas
las del admin: con la credencial de un teléfono, 401. Un token HS256 de la app
no es el JWT EdDSA de la BFF ni el token del panel de operador, y ninguna de
esas puertas lo confunde.
"""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute

from nexus_api.main import app
from tests.conftest import add_client_member, add_client_phone, make_client_access
from tests.isolation.test_console_scope import _console_routes, _fill

pytestmark = [pytest.mark.isolation]


def _partner_routes() -> list[str]:
    return [
        f"{sorted(r.methods)[0]} {r.path}"
        for r in _console_routes()
        if not r.path.startswith("/console/lite")
    ]


def _admin_routes() -> list[str]:
    return [
        f"{sorted(r.methods)[0]} {r.path}"
        for r in app.routes
        if isinstance(r, APIRoute) and r.path.startswith("/admin")
    ]


def _fill_admin(path: str) -> str:
    import uuid

    out = _fill(path, ref="whatever")
    for seg in [s for s in out.split("/") if s.startswith("{")]:
        out = out.replace(seg, str(uuid.uuid4()))
    return out


@pytest.fixture
async def phone(db_session, console_world) -> dict:
    w = console_world["a"]
    await make_client_access(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    member = await add_client_member(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"]
    )
    return await add_client_phone(db_session, membership_id=member["membership_id"])


async def test_the_sweeps_see_routes() -> None:
    assert _partner_routes() and _admin_routes()


@pytest.mark.asyncio
@pytest.mark.parametrize("route_id", _partner_routes())
async def test_a_phone_reaches_no_partner_route(route_id: str, client, phone) -> None:
    method, path = route_id.split(" ", 1)
    resp = await client.request(
        method, _fill(path, ref="client-a-1"), headers=phone["headers"](), json={}
    )
    assert resp.status_code == 401, f"{route_id} answered {resp.status_code}: {resp.text[:200]}"


@pytest.mark.asyncio
@pytest.mark.parametrize("route_id", _admin_routes())
async def test_a_phone_is_no_better_than_no_token_on_the_admin(
    route_id: str, client, phone
) -> None:
    """La credencial del teléfono no abre nada del admin: cada ruta responde con
    ella **exactamente lo mismo** que sin ningún token, y nunca un 2xx.

    No se exige 401 en todas: algunas rutas del admin resuelven el tenant de la
    ruta antes que el token y responden 404 a un tenant que no existe, con
    token o sin él. Lo que importa aquí es que el teléfono no cambie nada.
    """
    method, path = route_id.split(" ", 1)
    url = _fill_admin(path)
    with_phone = await client.request(method, url, headers=phone["headers"](), json={})
    anonymous = await client.request(method, url, json={})
    assert not 200 <= with_phone.status_code < 300, f"{route_id} answered {with_phone.status_code}"
    assert with_phone.status_code == anonymous.status_code, (
        f"{route_id}: phone {with_phone.status_code} vs anonymous {anonymous.status_code}"
    )
