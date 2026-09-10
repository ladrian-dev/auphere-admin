"""Requisito 6.1 — no hay forma de **entrar** hacia la máquina del partner.

Todo el tráfico es respuesta a un sondeo del dispositivo. Este test recorre las
rutas montadas y comprueba que ninguna empuja: si mañana alguien añade un
`POST /device/{id}/execute` «solo para depurar», esto se pone rojo antes de que
llegue a una máquina de otra persona.
"""

from __future__ import annotations

from fastapi.routing import APIRoute

from nexus_api.main import app

DEVICE_ROUTES = [r for r in app.routes if isinstance(r, APIRoute) and r.path.startswith("/device")]


def test_there_are_device_routes_to_inspect():
    assert DEVICE_ROUTES, "sin rutas que revisar, este test no prueba nada"


def test_no_route_addresses_a_device_by_id():
    """Una ruta con `{device_id}` sería una forma de dirigirse a una máquina."""
    for route in DEVICE_ROUTES:
        assert "{device_id}" not in route.path, route.path
        assert "{id}" not in route.path, route.path


def test_the_only_read_is_the_poll():
    """Lo que la plataforma entrega, lo entrega porque se lo han pedido."""
    gets = {r.path for r in DEVICE_ROUTES if "GET" in r.methods}
    assert gets == {"/device/poll"}


#: La única ruta de ``/device/*`` sin credencial: **el código es la credencial de
#: un solo uso** (spec 002, ``contracts/pairing.md``). Está aquí por nombre para
#: que añadir una segunda excepción obligue a escribirla — y a justificarla.
UNAUTHENTICATED_BY_DESIGN = {"/device/pair"}


def test_the_only_unauthenticated_route_is_the_pairing_exchange():
    paths = {r.path for r in DEVICE_ROUTES}
    assert paths >= UNAUTHENTICATED_BY_DESIGN, "el canje del código no está montado"


def test_the_credential_opens_exactly_five_operations():
    """Requisito 4.2: latir, sondear, devolver resultado, renovar, declarar directorio."""
    authenticated = {r.path for r in DEVICE_ROUTES} - UNAUTHENTICATED_BY_DESIGN
    assert authenticated == {
        "/device/heartbeat",
        "/device/poll",
        "/device/result",
        "/device/renew",
        "/device/links",
    }


def test_every_device_route_requires_the_device_credential():
    for route in DEVICE_ROUTES:
        if route.path in UNAUTHENTICATED_BY_DESIGN:
            continue
        names = {d.call.__name__ for d in route.dependant.dependencies if d.call}
        nested = {
            sub.call.__name__
            for d in route.dependant.dependencies
            for sub in d.dependencies
            if sub.call
        }
        assert "require_device" in (names | nested), route.path
