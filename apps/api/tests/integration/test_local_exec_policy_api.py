"""Requisitos 10.1, 10.3, 10.4 y 13 — las dos capas, por HTTP.

El **techo** es del partner y una decisión de seguridad: lo pone owner o admin
desde la página de equipo. La **preferencia** es de cada persona y solo puede
restringir dentro de ese techo. Aquí se comprueban las dos, la frontera de
permisos entre ellas, y que la pantalla recibe lo que necesita para no mentir:
lo que la persona guardó **y** lo que de verdad se aplica.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import AuditLog
from tests.conftest import add_console_member

pytestmark = pytest.mark.asyncio


async def _ceiling(client, world, **kw):
    return await client.get("/console/team/local-exec-ceiling", headers=world["headers"](**kw))


async def _set_ceiling(client, world, ceiling: str, **kw):
    return await client.put(
        "/console/team/local-exec-ceiling",
        headers=world["headers"](**kw),
        json={"ceiling": ceiling},
    )


async def _prefs(client, world):
    return await client.get("/console/teammates/local-exec-prefs", headers=world["headers"]())


async def _set_pref(client, world, *, executable, mode):
    return await client.put(
        "/console/teammates/local-exec-prefs",
        headers=world["headers"](),
        json={"executable": executable, "mode": mode},
    )


# ── el techo ───────────────────────────────────────────────────────────


async def test_an_absent_ceiling_reads_as_no_restriction(client, console_world):
    response = await _ceiling(client, console_world["a"])
    assert response.status_code == 200, response.text
    assert response.json() == {"ceiling": "always", "updated_by": None}


async def test_only_owner_and_admin_move_the_ceiling(client, db_session, console_world):
    a = console_world["a"]
    builder = await add_console_member(db_session, partner_id=a["partner_id"], role="builder")
    denied = await client.put(
        "/console/team/local-exec-ceiling", headers=builder["headers"](), json={"ceiling": "never"}
    )
    assert denied.status_code == 403
    # Pero sí puede LEERLO: no saber qué techo hay puesto solo hace que no se
    # entienda por qué te siguen preguntando.
    seen = await client.get("/console/team/local-exec-ceiling", headers=builder["headers"]())
    assert seen.status_code == 200

    allowed = await _set_ceiling(client, a, "ask")
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["ceiling"] == "ask"
    assert (await _ceiling(client, a)).json()["ceiling"] == "ask"


async def test_moving_the_ceiling_is_audited_with_the_person(client, console_world):
    a = console_world["a"]
    await _set_ceiling(client, a, "never")
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_partner_to_session(session, a["partner_id"], principal_id=a["user_id"])
        rows = (
            (
                await session.execute(
                    sa.select(AuditLog).where(AuditLog.action == "local_policy.ceiling_changed")
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 1
    assert rows[0].after_json == {"ceiling": "never"}
    assert str(rows[0].actor).startswith("console:")


async def test_a_ceiling_never_belongs_to_one_partner_only(client, console_world):
    a, b = console_world["a"], console_world["b"]
    await _set_ceiling(client, a, "never")
    assert (await _ceiling(client, b)).json()["ceiling"] == "always"


# ── la preferencia ─────────────────────────────────────────────────────


async def test_the_preference_is_kept_as_asked_and_the_effect_is_reported(client, console_world):
    """R10.4: guardar «permitir siempre» con techo `ask` conserva la elección y
    dice que el techo manda. Bajarla al guardar perdería lo que quiso."""
    a = console_world["a"]
    await _set_ceiling(client, a, "ask")
    saved = await _set_pref(client, a, executable=None, mode="always")
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["global_mode"] == "always", "lo que la persona eligió se conserva"
    assert body["effective"] == "ask"
    assert body["capped"] is True
    assert body["ceiling"] == "ask"


async def test_a_preference_for_one_executable_is_listed_with_its_effect(client, console_world):
    a = console_world["a"]
    await _set_pref(client, a, executable=None, mode="ask")
    await _set_pref(client, a, executable="make", mode="always")
    listed = (await _prefs(client, a)).json()
    assert listed["global_mode"] == "ask"
    assert listed["per_executable"] == [
        {"executable": "make", "mode": "always", "effective": "always", "capped": False}
    ]


async def test_the_same_preference_twice_updates_and_does_not_duplicate(client, console_world):
    a = console_world["a"]
    await _set_pref(client, a, executable="make", mode="always")
    await _set_pref(client, a, executable="make", mode="never")
    listed = (await _prefs(client, a)).json()
    assert [p["mode"] for p in listed["per_executable"]] == ["never"]


async def test_one_persons_preference_is_invisible_to_another(client, db_session, console_world):
    a = console_world["a"]
    other = await add_console_member(db_session, partner_id=a["partner_id"], role="builder")
    await _set_pref(client, a, executable="make", mode="always")
    listed = await client.get("/console/teammates/local-exec-prefs", headers=other["headers"]())
    assert listed.status_code == 200
    assert listed.json()["per_executable"] == []
    assert listed.json()["global_mode"] == "ask"


async def test_the_preference_change_is_audited(client, console_world):
    a = console_world["a"]
    await _set_pref(client, a, executable="make", mode="never")
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_partner_to_session(session, a["partner_id"], principal_id=a["user_id"])
        rows = (
            (
                await session.execute(
                    sa.select(AuditLog).where(AuditLog.action == "local_policy.pref_changed")
                )
            )
            .scalars()
            .all()
        )
    assert [r.after_json for r in rows] == [{"executable": "make", "mode": "never"}]


async def test_a_bad_mode_or_executable_is_refused(client, console_world):
    a = console_world["a"]
    assert (await _set_pref(client, a, executable=None, mode="sometimes")).status_code == 422
    assert (
        await _set_pref(client, a, executable="make; rm -rf /", mode="never")
    ).status_code == 422
    assert (await _set_ceiling(client, a, "maybe")).status_code == 422
