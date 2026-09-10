"""Requisito 1 — el roster, leído por persona con su estado (spec 003, US1).

``GET /console/teammates`` devuelve el roster del partner y, por cada teammate,
lo que **esta persona** tiene con él: ``my_state`` (derivado de su último run),
``my_unread`` (el teammate contestó y ella no ha vuelto a escribir) y
``last_done`` (la última tarea terminada — llega con la US2; hasta entonces
``null``). Los archivados quedan fuera salvo ``include_archived``. Sin
``teammates:use`` no hay roster.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from nexus_api.db.models import Teammate
from nexus_api.db.models.companion import CompanionMessage, CompanionRun, CompanionThread
from tests.conftest import add_console_member

pytestmark = pytest.mark.asyncio


def _teammate(partner_id: uuid.UUID, name: str, *, archived: bool = False) -> Teammate:
    now = datetime.now(UTC)
    return Teammate(
        id=uuid.uuid4(),
        partner_id=partner_id,
        name=name,
        job="Investigación",
        model="auphere-sonnet",
        tool_names=["console.whoami"],
        permissions={
            "read": True,
            "write": False,
            "spend": False,
            "publish": False,
            "contact": False,
        },
        local_exec=False,
        created_by="seed",
        status="archived" if archived else "active",
        archived_at=now if archived else None,
    )


async def test_the_roster_lists_active_teammates_with_the_persons_state(
    client, db_session, console_world
):
    a = console_world["a"]
    iris = _teammate(a["partner_id"], "Iris")
    vera = _teammate(a["partner_id"], "Vera")
    old = _teammate(a["partner_id"], "Antigua", archived=True)
    db_session.add_all([iris, vera, old])
    await db_session.flush()
    # Mi hilo con Iris: un run en marcha. Con Vera: uno terminado y sin respuesta mía.
    t_iris = CompanionThread(
        id=uuid.uuid4(),
        principal_id=a["user_id"],
        partner_id=a["partner_id"],
        teammate_id=iris.id,
        title="x",
    )
    t_vera = CompanionThread(
        id=uuid.uuid4(),
        principal_id=a["user_id"],
        partner_id=a["partner_id"],
        teammate_id=vera.id,
        title="y",
    )
    db_session.add_all([t_iris, t_vera])
    await db_session.flush()
    running = CompanionRun(
        thread_id=t_iris.id, principal_id=a["user_id"], teammate_id=iris.id, status="running"
    )
    done = CompanionRun(
        thread_id=t_vera.id,
        principal_id=a["user_id"],
        teammate_id=vera.id,
        status="completed",
        ended_at=datetime.now(UTC),
    )
    db_session.add_all([running, done])
    await db_session.flush()
    db_session.add(
        CompanionMessage(
            thread_id=t_vera.id,
            run_id=done.id,
            seq=1,
            role="user",
            content="hola",
            created_at=datetime.now(UTC) - timedelta(minutes=5),
        )
    )
    await db_session.commit()

    response = await client.get("/console/teammates", headers=a["headers"]())
    assert response.status_code == 200, response.text
    by_name = {t["name"]: t for t in response.json()}
    assert set(by_name) == {"Iris", "Vera"}
    assert by_name["Iris"]["my_state"] == "en_marcha"
    assert by_name["Vera"]["my_state"] == "en_espera"
    assert by_name["Vera"]["my_unread"] is True
    assert by_name["Iris"]["last_done"] is None
    for row in by_name.values():
        assert "partner_id" not in row and "tenant_id" not in row

    archived = await client.get("/console/teammates?include_archived=true", headers=a["headers"]())
    assert {t["name"] for t in archived.json()} == {"Iris", "Vera", "Antigua"}


async def test_another_persons_thread_does_not_colour_my_roster(client, db_session, console_world):
    a = console_world["a"]
    iris = _teammate(a["partner_id"], "Iris")
    db_session.add(iris)
    await db_session.flush()
    other = CompanionThread(
        id=uuid.uuid4(),
        principal_id="user_colleague_a",
        partner_id=a["partner_id"],
        teammate_id=iris.id,
        title="x",
    )
    db_session.add(other)
    await db_session.flush()
    db_session.add(
        CompanionRun(
            thread_id=other.id,
            principal_id="user_colleague_a",
            teammate_id=iris.id,
            status="running",
        )
    )
    await db_session.commit()
    response = await client.get("/console/teammates", headers=a["headers"]())
    assert response.json()[0]["my_state"] == "en_espera"


async def test_an_analyst_has_no_roster(client, db_session, console_world):
    a = console_world["a"]
    analyst = await add_console_member(db_session, partner_id=a["partner_id"], role="analyst")
    response = await client.get("/console/teammates", headers=analyst["headers"]())
    assert response.status_code == 403


async def test_the_jobs_endpoint_offers_the_seed_and_the_models(client, console_world):
    a = console_world["a"]
    response = await client.get("/console/teammates/jobs", headers=a["headers"]())
    assert response.status_code == 200, response.text
    body = response.json()
    assert "Atención al cliente" in body["jobs"] and len(body["jobs"]) == 8
    assert isinstance(body["models"], list)
    for m in body["models"]:
        assert set(m) >= {"id", "note", "cost_label"}
