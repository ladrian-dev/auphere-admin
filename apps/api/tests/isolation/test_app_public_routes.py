"""Spec 031 · R15.1, R15.2 (enmienda del 2026-10-20) — lo público de la app
(tarea T117).

``/app/*`` vive fuera de ``/console`` porque se llama **antes** de tener sesión:
entrar, renovar, pedir el enlace de contraseña y leer la configuración. Por eso
``test_console_scope`` no lo barre, y por eso lo barre este archivo:

- la lista de rutas públicas es **cerrada**: una ruta nueva bajo ``/app`` rompe
  esta prueba hasta que alguien decide, por escrito, que puede ser pública;
- sin credenciales, ninguna devuelve un nombre, una referencia ni un correo de
  ningún cliente, pida lo que pida;
- la emisión de códigos por la consola (``/console/lite/phone-codes``) ya no
  existe: el código del teléfono solo sale de la vuelta de Google.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from nexus_api.main import app
from tests.conftest import add_client_member

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

#: Lo que puede llamarse sin sesión. Ampliarla es una decisión, no un efecto.
PUBLIC_APP_ROUTES = {
    ("POST", "/app/sign-in/password"),
    ("GET", "/app/sign-in/google"),
    ("GET", "/app/sign-in/google/callback"),
    ("POST", "/app/sign-in/google"),
    ("POST", "/app/password-reset"),
    ("POST", "/app/phones/refresh"),
    ("GET", "/app/config"),
}


def _mounted_app_routes() -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/app/"):
            continue
        for method in getattr(route, "methods", set()) or set():
            if method not in ("HEAD", "OPTIONS"):
                out.add((method, path))
    return out


def test_the_public_app_routes_are_exactly_the_written_ones() -> None:
    assert _mounted_app_routes() == PUBLIC_APP_ROUTES


def test_the_console_no_longer_mints_phone_codes() -> None:
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/console/lite/phone-codes" not in paths


_PROBES: dict[tuple[str, str], dict[str, Any]] = {
    ("POST", "/app/sign-in/password"): {
        "json": {
            "email": "{email}",
            "password": "no-es-la-contraseña",
            "platform": "ios",
            "display_name": "Sonda",
            "install_id": uuid.uuid4().hex,
            "app_version": "1.0.0",
        }
    },
    ("GET", "/app/sign-in/google"): {"params": {"state": "x" * 20, "code_challenge": "A" * 43}},
    ("GET", "/app/sign-in/google/callback"): {"params": {"code": "c", "state": "inventado"}},
    ("POST", "/app/sign-in/google"): {
        "json": {
            "code": "AB12CD34",
            "code_verifier": "v" * 43,
            "platform": "android",
            "display_name": "Sonda",
            "install_id": uuid.uuid4().hex,
            "app_version": "1.0.0",
        }
    },
    ("POST", "/app/password-reset"): {"json": {"email": "{email}"}},
    ("POST", "/app/phones/refresh"): {"json": {"refresh_token": "r" * 43}},
    ("GET", "/app/config"): {},
}


def test_every_public_route_has_a_probe() -> None:
    assert set(_PROBES) == PUBLIC_APP_ROUTES


@pytest.mark.parametrize("route", sorted(PUBLIC_APP_ROUTES))
async def test_without_credentials_nothing_of_a_client_comes_back(
    client, db_session, console_world, route: tuple[str, str], monkeypatch
) -> None:
    async def _no_mail(*_: Any, **__: Any) -> bool:
        return True

    monkeypatch.setattr("nexus_api.services.email.send_template", _no_mail)
    w = console_world["a"]
    email = f"sonda-{uuid.uuid4().hex[:6]}@cliente.test"
    await add_client_member(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"], email=email
    )
    method, path = route
    probe = _PROBES[route]
    kwargs: dict[str, Any] = {}
    if "json" in probe:
        kwargs["json"] = {
            k: (v.replace("{email}", email) if isinstance(v, str) else v)
            for k, v in probe["json"].items()
        }
    if "params" in probe:
        kwargs["params"] = probe["params"]

    resp = await client.request(method, path, **kwargs)

    body = resp.text + " ".join(f"{k}={v}" for k, v in resp.headers.items())
    for secret in (w["ref"], w["slug"], str(w["tenant_id"]), "Client A One", email):
        assert secret not in body, f"{method} {path} devuelve {secret!r} sin credenciales"
    assert resp.status_code not in (500, 501, 502, 503), resp.text
