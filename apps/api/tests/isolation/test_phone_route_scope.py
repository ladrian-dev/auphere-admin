"""Spec 031 · R15.2 — con la credencial de un teléfono, nada de la vecina (T030).

Es el barrido de ``test_lite_client_vs_client`` (spec 030) **con la otra
credencial**. El teléfono entra por una rama nueva de
``require_client_principal``; si esa rama se equivocara de cliente, este
barrido lo vería en cada ruta lite, no en una muestra:

- las ``GET`` sin identificador no devuelven ningún nombre ni ref de la vecina;
- las que llevan el id de un objeto de la vecina responden **byte a byte** igual
  que a un id que no existe;
- lo mismo las escrituras de la Bandeja y el cierre de un teléfono ajeno.

Una ruta lite nueva entra en el barrido el día que se monta.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from tests.conftest import add_client_member, add_client_phone
from tests.isolation.test_console_scope import _console_routes
from tests.isolation.test_lite_client_vs_client import (
    _FOREIGN,
    _INBOX_WRITES,
    _STREAMS,
    NEIGHBOUR_NAME,
    NEIGHBOUR_REF,
    RESERVAS_PREFIX,
    _neighbourhood,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]


async def _with_phones(db_session, console_world) -> dict[str, Any]:
    """El vecindario de la 030, con un teléfono para la persona y otro para
    alguien de la vecina."""
    world = await _neighbourhood(db_session, console_world)
    phone = await add_client_phone(db_session, membership_id=world["member"]["membership_id"])
    neighbour_member = await add_client_member(
        db_session, partner_id=console_world["a"]["partner_id"], tenant_id=world["neighbour"]
    )
    neighbour_phone = await add_client_phone(
        db_session, membership_id=neighbour_member["membership_id"]
    )
    return {**world, "phone": phone, "phone_id": neighbour_phone["phone_id"]}


def _lite_gets() -> list[str]:
    return [
        r.path
        for r in _console_routes()
        if r.path.startswith("/console/lite")
        and "GET" in r.methods
        and r.path not in _STREAMS
        # Spec 043: con la credencial del teléfono también, en su propio barrido.
        and not r.path.startswith(RESERVAS_PREFIX)
    ]


@pytest.mark.parametrize("path", _lite_gets())
async def test_phone_reads_never_show_the_neighbour(
    path: str, client, db_session, console_world
) -> None:
    world = await _with_phones(db_session, console_world)
    headers = world["phone"]["headers"]
    params = [seg[1:-1] for seg in path.split("/") if seg.startswith("{")]
    if not params:
        resp = await client.get(path, headers=headers())
        assert resp.status_code == 200, f"{path}: {resp.status_code} {resp.text[:200]}"
        assert NEIGHBOUR_NAME not in resp.text
        assert NEIGHBOUR_REF not in resp.text
        assert str(world["neighbour"]) not in resp.text
        assert str(world["phone_id"]) not in resp.text
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


_PHONE_WRITES: list[tuple[str, str, dict[str, Any] | None]] = [
    *_INBOX_WRITES,
    ("DELETE", "/console/lite/phones/{phone_id}", None),
]


async def test_every_write_with_an_id_is_probed() -> None:
    """Una escritura lite nueva con id sin entrada arriba: rojo."""
    mounted = {
        (sorted(r.methods)[0], r.path)
        for r in _console_routes()
        if r.path.startswith("/console/lite/")
        and "{" in r.path
        and sorted(r.methods)[0] != "GET"
        and not r.path.endswith("/attachments")
        and not r.path.startswith("/console/lite/notifications/")
        and not r.path.startswith(RESERVAS_PREFIX)
    }
    assert mounted == {(m, p) for m, p, _ in _PHONE_WRITES}


@pytest.mark.parametrize(("method", "path", "body"), _PHONE_WRITES)
async def test_phone_writes_on_a_neighbour_object_are_the_same_404(
    method: str, path: str, body: dict[str, Any] | None, client, db_session, console_world
) -> None:
    world = await _with_phones(db_session, console_world)
    headers = world["phone"]["headers"]
    param = path.split("{", 1)[1].split("}", 1)[0]
    foreign = await client.request(
        method, path.replace("{" + param + "}", str(world[param])), headers=headers(), json=body
    )
    ghost = await client.request(
        method, path.replace("{" + param + "}", str(uuid.uuid4())), headers=headers(), json=body
    )
    assert foreign.status_code == ghost.status_code == 404, (path, foreign.status_code)
    assert foreign.content == ghost.content
