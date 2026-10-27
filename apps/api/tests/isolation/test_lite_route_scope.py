"""Spec 030 — la frontera entre las dos consolas, barrida (R2.2, R2.5, R17.1).

Dos tipos de persona entran por la misma consola. Este archivo recorre
**todas** las rutas registradas de ``/console/*`` —no una muestra— y fija:

1. Una persona de cliente recibe 403 en toda ruta que no sea de
   ``/console/lite/*``: ni las del partner (``require_console_principal`` no
   la encuentra en ``partner_memberships``) ni las de servicio (su token no es
   de servicio).
2. Un miembro del partner recibe 403 en toda ruta de ``/console/lite/*``
   (``require_client_principal`` no lo encuentra en ``client_memberships``).
3. Ninguna ruta lite acepta ``ref`` ni ``customer_id``: el cliente sale de la
   membresía, y el cliente final, del objeto (el barrido general de
   ``test_console_scope`` ya prohíbe ``tenant_id`` y ``partner_id``).

Una ruta nueva entra en el barrido el día que se monta.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from fastapi import APIRouter
from fastapi.routing import APIRoute

from nexus_api.main import app
from tests.conftest import add_client_member, make_client_access
from tests.isolation.test_console_scope import _console_routes, _fill

pytestmark = [pytest.mark.isolation]

LITE = "/console/lite"


def _route_ids(*, lite: bool) -> list[str]:
    return [
        f"{sorted(r.methods)[0]} {r.path}"
        for r in _console_routes()
        if r.path.startswith(LITE) == lite
    ]


def test_the_lite_family_is_mounted() -> None:
    assert _route_ids(lite=True), "no /console/lite routes registered"


@pytest.mark.parametrize("route_id", _route_ids(lite=True))
def test_lite_routes_take_no_client_or_customer_reference(route_id: str) -> None:
    method, path = route_id.split(" ", 1)
    op: dict[str, Any] = app.openapi()["paths"][path][method.lower()]
    names = {p["name"].lower() for p in op.get("parameters", [])}
    assert not names & {"ref", "client", "client_ref", "customer_id", "customer"}, (
        f"{route_id} accepts {names}"
    )
    assert "{ref}" not in path


@pytest.fixture
async def client_member(db_session, console_world) -> dict[str, Any]:
    w = console_world["a"]
    await make_client_access(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    return await add_client_member(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])


@pytest.mark.asyncio
@pytest.mark.parametrize("route_id", _route_ids(lite=False))
async def test_a_client_user_reaches_no_partner_route(route_id: str, client, client_member) -> None:
    method, path = route_id.split(" ", 1)
    resp = await client.request(
        method, _fill(path, ref="client-a-1"), headers=client_member["headers"](), json={}
    )
    assert resp.status_code == 403, f"{route_id} answered {resp.status_code}: {resp.text[:200]}"


@pytest.mark.asyncio
@pytest.mark.parametrize("route_id", _route_ids(lite=True))
async def test_a_partner_member_reaches_no_lite_route(
    route_id: str, client, console_world, client_member
) -> None:
    method, path = route_id.split(" ", 1)
    resp = await client.request(
        method, _fill(path, ref="x"), headers=console_world["a"]["headers"](), json={}
    )
    assert resp.status_code == 403, f"{route_id} answered {resp.status_code}: {resp.text[:200]}"


def test_every_lite_route_is_an_api_route() -> None:
    """Control del control: el filtro de arriba ve las rutas lite."""
    lite = [r for r in app.routes if isinstance(r, APIRoute) and r.path.startswith(LITE)]
    assert {f"{sorted(r.methods)[0]} {r.path}" for r in lite} == set(_route_ids(lite=True))


# ── Spec 047, T021: una ruta de mañana entra sola ──────────────────────────


@contextmanager
def mounted(*routes: tuple[str, str]) -> Iterator[None]:
    """Monta rutas de prueba en la app de verdad y las quita al salir. Las
    funciones de barrido leen ``app.routes`` cada vez: si una ruta montada aquí
    no aparece en ellas, el barrido era una lista y no lo sabíamos."""
    router = APIRouter()
    for method, path in routes:

        async def _probe() -> dict[str, str]:  # pragma: no cover - nunca se llama
            return {}

        router.add_api_route(path, _probe, methods=[method])
    app.include_router(router)
    try:
        yield
    finally:
        probes = set(routes)
        app.router.routes[:] = [
            r
            for r in app.router.routes
            if not (isinstance(r, APIRoute) and any((m, r.path) in probes for m in r.methods or ()))
        ]


def test_a_lite_route_mounted_tomorrow_enters_both_sweeps() -> None:
    """Spec 047 (requisito 56.10): las rutas nuevas de ``/console/lite/*`` entran
    en este barrido —y en el de ``test_phone_route_scope``— el día que se montan,
    porque los dos se calculan de ``app.routes``, no de una lista escrita."""
    from tests.isolation.test_phone_route_scope import _lite_gets

    probe = ("GET", "/console/lite/agents/{agent_id}/probe-047")
    with mounted(probe):
        assert f"GET {probe[1]}" in _route_ids(lite=True)
        assert f"GET {probe[1]}" not in _route_ids(lite=False)
        assert probe[1] in _lite_gets()
    assert f"GET {probe[1]}" not in _route_ids(lite=True), "la ruta de prueba no se desmontó"


def test_an_app_route_mounted_tomorrow_breaks_the_closed_app_list() -> None:
    """``/app/*`` lo barre ``test_app_public_routes`` con una lista CERRADA: una
    ruta nueva bajo ``/app`` lo pone en rojo hasta que alguien la escribe."""
    from tests.isolation.test_app_public_routes import PUBLIC_APP_ROUTES, _mounted_app_routes

    with mounted(("GET", "/app/probe-047")):
        assert _mounted_app_routes() - PUBLIC_APP_ROUTES == {("GET", "/app/probe-047")}
    assert _mounted_app_routes() == PUBLIC_APP_ROUTES
