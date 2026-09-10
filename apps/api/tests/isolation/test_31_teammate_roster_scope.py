"""Garantías 1 y 6 — el roster es del partner (spec 003, Requisito 1).

Un teammate es un dato del **partner**: todos sus miembros ven los mismos
(decisión 8) y ningún otro partner ve ninguno. Este fichero prueba lo que eso
obliga:

* la fila se ve por ``app.partner_id`` y **solo** por él; sin GUC, nada;
* un ``UPDATE`` desde otro partner no toca ninguna fila;
* ``DELETE`` no existe para ``nexus_app`` (R2.6: se archiva, nunca se borra);
* crear teammates es de ``teammates:use`` (owner, admin, builder); el techo
  de la política local es de ``teammates:policy`` (owner, admin).

En rojo bloquea el merge.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError

from nexus_api.core.console_auth import permissions_for
from nexus_api.db.models import Teammate

from .conftest import set_partner

pytestmark = [pytest.mark.isolation, pytest.mark.asyncio]


def _teammate(partner_id: uuid.UUID, name: str, *, created_by: str) -> Teammate:
    return Teammate(
        id=uuid.uuid4(),
        partner_id=partner_id,
        name=name,
        job="Atención al cliente",
        model="auphere-sonnet",
        tool_names=["console.whoami", "console.list_clients"],
        permissions={
            "read": True,
            "write": False,
            "spend": False,
            "publish": False,
            "contact": False,
        },
        local_exec=False,
        created_by=created_by,
    )


async def _seed(db_session, console_world):
    a, b = console_world["a"], console_world["b"]
    rows = [
        _teammate(a["partner_id"], "Sofía", created_by=a["user_id"]),
        _teammate(a["partner_id"], "Nilo", created_by="user_colleague_a"),
        _teammate(b["partner_id"], "Vera", created_by=b["user_id"]),
    ]
    db_session.add_all(rows)
    await db_session.commit()
    return rows


async def _no_guc(session) -> None:
    await session.execute(
        text(
            "SELECT set_config('app.partner_id', '', true), "
            "set_config('app.principal_id', '', true), set_config('role', 'nexus_app', true)"
        )
    )


# ── garantía 1: RLS por partner, y todos los miembros ven lo mismo ─────


async def test_every_member_of_the_partner_sees_the_whole_roster_and_nothing_else(
    db_session, console_world
):
    a = console_world["a"]
    await _seed(db_session, console_world)
    await set_partner(db_session, a["partner_id"], principal_id="user_colleague_a")
    names = (await db_session.execute(select(Teammate.name))).scalars().all()
    assert set(names) == {"Sofía", "Nilo"}


async def test_without_partner_there_are_no_rows(db_session, console_world):
    await _seed(db_session, console_world)
    await _no_guc(db_session)
    assert (await db_session.execute(select(Teammate.id))).scalars().all() == []


async def test_another_partner_cannot_touch_the_roster(db_session, console_world):
    a, b = console_world["a"], console_world["b"]
    rows = await _seed(db_session, console_world)
    vera = rows[2]
    await set_partner(db_session, a["partner_id"], principal_id=a["user_id"])
    result = await db_session.execute(
        update(Teammate).where(Teammate.id == vera.id).values(name="x")
    )
    assert result.rowcount == 0
    assert (
        await db_session.execute(select(Teammate.id).where(Teammate.id == vera.id))
    ).scalar() is None
    await db_session.rollback()
    await set_partner(db_session, b["partner_id"], principal_id=b["user_id"])
    assert (await db_session.execute(select(Teammate.name))).scalars().all() == ["Vera"]


# ── R2.6: borrar no existe ───────────────────────────────────────────────


async def test_delete_is_not_granted_to_the_application_role(db_session, console_world):
    a = console_world["a"]
    rows = await _seed(db_session, console_world)
    await set_partner(db_session, a["partner_id"], principal_id=a["user_id"])
    with pytest.raises(DBAPIError):
        await db_session.execute(delete(Teammate).where(Teammate.id == rows[0].id))
    await db_session.rollback()


# ── garantía 6 / R2.2: quién puede crear y quién pone el techo ─────────


async def test_only_owner_admin_and_builder_use_teammates_and_only_owner_admin_set_the_ceiling():
    assert "teammates:use" in permissions_for("owner")
    assert "teammates:use" in permissions_for("admin")
    assert "teammates:use" in permissions_for("builder")
    assert "teammates:use" not in permissions_for("analyst")
    assert "teammates:use" not in permissions_for("billing")
    assert "teammates:policy" in permissions_for("owner")
    assert "teammates:policy" in permissions_for("admin")
    assert "teammates:policy" not in permissions_for("builder")
