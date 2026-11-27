"""Las rutas de rutinas en la consola — spec 082, T012 (requisitos 1.2, 1.3,
2, 3.6, 11 y 14).

El servicio ya está probado aparte (``test_crud.py``). Aquí se prueba lo que
solo se ve desde fuera: que el ámbito del cliente es de verdad, que los
permisos cierran, que la lista cuenta y filtra, y que **no hay por dónde
borrar**.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import add_console_member

from .conftest import body as _body
from .conftest import make_agent as _agent
from .conftest import url as _url

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


# ── el alta y la lista ──────────────────────────────────────────────────────


async def test_create_and_list(client: Any, world: dict[str, Any]) -> None:
    made = await client.post(_url(world), json=_body(world["agent_id"]), headers=world["headers"]())
    assert made.status_code == 201, made.text
    body = made.json()
    assert body["name"] == "Altas de ayer en Notion"
    assert body["state"] == "active"
    assert body["next_run_at"] is not None
    assert body["agent"]["name"] == "Soporte"

    listed = await client.get(_url(world), headers=world["headers"]())
    assert listed.status_code == 200, listed.text
    page = listed.json()
    assert page["timezone"]
    assert page["counts"] == {"all": 1, "active": 1, "paused": 0, "archived": 0}
    assert [s["id"] for s in page["schedules"]] == [body["id"]]


async def test_the_list_filters_by_state_and_by_agent(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    other = await _agent(db_session, world["tenant_id"], name="Ventas")
    first = (
        await client.post(_url(world), json=_body(world["agent_id"]), headers=world["headers"]())
    ).json()
    await client.post(
        _url(world), json=_body(other, name="La de Ventas"), headers=world["headers"]()
    )
    await client.post(_url(world, f"/{first['id']}/pause"), headers=world["headers"]())

    page = (await client.get(_url(world), headers=world["headers"]())).json()
    assert page["counts"] == {"all": 2, "active": 1, "paused": 1, "archived": 0}

    only_paused = (
        await client.get(_url(world) + "?state=paused", headers=world["headers"]())
    ).json()
    assert [s["id"] for s in only_paused["schedules"]] == [first["id"]]

    by_agent = (
        await client.get(_url(world) + f"?agent={other}", headers=world["headers"]())
    ).json()
    assert [s["name"] for s in by_agent["schedules"]] == ["La de Ventas"]


async def test_a_bad_alta_says_which_field(client: Any, world: dict[str, Any]) -> None:
    resp = await client.post(
        _url(world),
        json=_body(world["agent_id"], cadence="weekly", weekdays=[]),
        headers=world["headers"](),
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "weekdays_required"


# ── el detalle y los cambios ────────────────────────────────────────────────


async def test_detail_and_patch(client: Any, world: dict[str, Any]) -> None:
    made = (
        await client.post(_url(world), json=_body(world["agent_id"]), headers=world["headers"]())
    ).json()

    got = await client.get(_url(world, f"/{made['id']}"), headers=world["headers"]())
    assert got.status_code == 200
    assert got.json()["instruction"].startswith("Revisa")

    changed = await client.patch(
        _url(world, f"/{made['id']}"),
        json={"name": "Otro nombre"},
        headers=world["headers"](),
    )
    assert changed.status_code == 200
    assert changed.json()["name"] == "Otro nombre"
    # Cambiar el nombre no mueve la próxima ejecución.
    assert changed.json()["next_run_at"] == made["next_run_at"]


async def test_pause_resume_archive_restore(client: Any, world: dict[str, Any]) -> None:
    made = (
        await client.post(_url(world), json=_body(world["agent_id"]), headers=world["headers"]())
    ).json()
    at = lambda tail: _url(world, f"/{made['id']}{tail}")  # noqa: E731

    paused = (await client.post(at("/pause"), headers=world["headers"]())).json()
    assert (paused["state"], paused["pause_reason"], paused["next_run_at"]) == (
        "paused",
        "manual",
        None,
    )

    back = (await client.post(at("/resume"), headers=world["headers"]())).json()
    assert back["state"] == "active" and back["next_run_at"] is not None

    archived = (await client.post(at("/archive"), headers=world["headers"]())).json()
    assert archived["state"] == "archived"

    restored = (await client.post(at("/restore"), headers=world["headers"]())).json()
    assert (restored["state"], restored["pause_reason"]) == ("paused", "manual")


async def test_there_is_no_way_to_delete(client: Any, world: dict[str, Any]) -> None:
    """Constitución §IV: borrar no existe, se archiva."""
    made = (
        await client.post(_url(world), json=_body(world["agent_id"]), headers=world["headers"]())
    ).json()
    gone = await client.delete(_url(world, f"/{made['id']}"), headers=world["headers"]())
    assert gone.status_code == 405


# ── las próximas, antes de guardar ──────────────────────────────────────────


async def test_preview_does_not_write(client: Any, world: dict[str, Any]) -> None:
    resp = await client.post(
        _url(world, "/preview"),
        json={"cadence": "weekly", "local_time": "08:00", "weekdays": [0, 3]},
        headers=world["headers"](),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["next"]) == 3
    assert body["timezone"]

    page = (await client.get(_url(world), headers=world["headers"]())).json()
    assert page["counts"]["all"] == 0


# ── el ámbito y los permisos ────────────────────────────────────────────────


async def test_another_partners_client_does_not_exist(client: Any, world: dict[str, Any]) -> None:
    resp = await client.get(
        f"/console/clients/{world['other_ref']}/schedules", headers=world["headers"]()
    )
    assert resp.status_code == 404


async def test_an_analyst_may_read_but_not_write(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    analyst = await add_console_member(db_session, partner_id=world["partner_id"], role="analyst")

    assert (await client.get(_url(world), headers=analyst["headers"]())).status_code == 200
    refused = await client.post(
        _url(world), json=_body(world["agent_id"]), headers=analyst["headers"]()
    )
    assert refused.status_code == 403


async def test_billing_sees_nothing(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    billing = await add_console_member(db_session, partner_id=world["partner_id"], role="billing")
    assert (await client.get(_url(world), headers=billing["headers"]())).status_code == 403
