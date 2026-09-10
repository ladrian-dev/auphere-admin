"""Garantía 1 — el hilo es de un teammate **y** de una persona (spec 003, R3.1, R5.1).

La RLS por ``principal_id`` de la migración 0090 sigue mandando: ``teammate_id``
es una columna más, no una puerta. Dos personas del mismo partner con el mismo
teammate no se ven; sus acciones tampoco; y un ``teammate_id`` de otro partner
no se puede colgar de un hilo por la API.

En rojo bloquea el merge.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from nexus_api.core.principal_context import apply_principal_to_session
from nexus_api.db.models import Teammate
from nexus_api.db.models.companion import CompanionAction, CompanionThread

pytestmark = [pytest.mark.isolation, pytest.mark.asyncio]


def _teammate(partner_id: uuid.UUID, name: str) -> Teammate:
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
    )


async def _seed(db_session, console_world):
    a, b = console_world["a"], console_world["b"]
    iris = _teammate(a["partner_id"], "Iris")
    vera = _teammate(b["partner_id"], "Vera")
    db_session.add_all([iris, vera])
    await db_session.flush()
    t1 = CompanionThread(
        id=uuid.uuid4(),
        principal_id=a["user_id"],
        partner_id=a["partner_id"],
        teammate_id=iris.id,
        title="p1",
    )
    t2 = CompanionThread(
        id=uuid.uuid4(),
        principal_id="user_colleague_a",
        partner_id=a["partner_id"],
        teammate_id=iris.id,
        title="p2",
    )
    db_session.add_all([t1, t2])
    await db_session.flush()
    db_session.add_all(
        [
            CompanionAction(id=uuid.uuid4(), thread_id=t1.id, kind="prompt", payload={}),
            CompanionAction(id=uuid.uuid4(), thread_id=t2.id, kind="prompt", payload={}),
        ]
    )
    await db_session.commit()
    return iris, vera, t1, t2


async def test_two_people_with_the_same_teammate_never_see_each_others_thread(
    db_session, console_world
):
    a = console_world["a"]
    iris, _vera, t1, _t2 = await _seed(db_session, console_world)
    await apply_principal_to_session(db_session, a["user_id"])
    ids = (
        (
            await db_session.execute(
                select(CompanionThread.id).where(CompanionThread.teammate_id == iris.id)
            )
        )
        .scalars()
        .all()
    )
    assert ids == [t1.id]


async def test_the_inbox_of_one_person_never_lists_the_other_persons_actions(
    db_session, console_world
):
    a = console_world["a"]
    _iris, _vera, t1, _t2 = await _seed(db_session, console_world)
    await apply_principal_to_session(db_session, a["user_id"])
    thread_ids = (await db_session.execute(select(CompanionAction.thread_id))).scalars().all()
    assert thread_ids == [t1.id]


async def test_a_thread_cannot_hang_from_a_teammate_of_another_partner(
    client, db_session, console_world
):
    a = console_world["a"]
    _iris, vera, _t1, _t2 = await _seed(db_session, console_world)
    response = await client.post(
        "/console/companion/threads",
        headers=a["headers"](),
        json={"title": "x", "mode": "build", "teammate_id": str(vera.id)},
    )
    assert response.status_code == 404, response.text
