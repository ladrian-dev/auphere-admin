"""Requisito 2 — crear, cambiar y archivar un teammate desde la aplicación.

Tres actos y una regla que los cruza: **la aplicación no puede ampliar lo que
la plataforma publica** (garantía 2). El formulario manda cinco interruptores;
el catálogo lo deriva la API y nadie más. Por eso aquí no se comprueba «el
endpoint contesta 201», se comprueba *qué acaba viendo el modelo*.

Archivar ya vive en la US2 (lo necesitaba para cerrar lo que esperaba); lo que
esta suite añade sobre él es que un archivado **no se puede cambiar** y que los
tres actos dejan asiento con la persona delante.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import AuditLog, Teammate
from nexus_api.db.models.companion import CompanionThread
from nexus_api.services.teammate_catalog import for_teammate, permissions_to_tool_names
from tests.conftest import add_console_member

pytestmark = pytest.mark.asyncio

ALL_ON = {"read": True, "write": True, "spend": True, "publish": True, "contact": True}
READ_ONLY = {"read": True, "write": False, "spend": False, "publish": False, "contact": False}
SOL = "openai/gpt-5.6-sol"


async def _only_models(db_session, partner_id: uuid.UUID, *model_ids: str) -> None:
    """Deja en la lista del partner **exactamente** estos modelos.

    Se reemplaza en vez de añadir porque el mundo de pruebas ya trae los tres
    de la oferta, y un test que solo añadiera no podría distinguir «este no
    está permitido» de «están todos permitidos».
    """
    await db_session.execute(
        sa.text("DELETE FROM partner_model_allowlist WHERE partner_id = :p"), {"p": partner_id}
    )
    for model_id in model_ids:
        await db_session.execute(
            sa.text(
                "INSERT INTO partner_model_allowlist (partner_id, model_id) "
                "VALUES (:p, :m) ON CONFLICT DO NOTHING"
            ),
            {"p": partner_id, "m": model_id},
        )
    await db_session.commit()


async def _create(client, world, **body):
    payload = {
        "name": "Sofía",
        "job": "Atención al cliente",
        "model": SOL,
        "permissions": READ_ONLY,
        **body,
    }
    return await client.post("/console/teammates", headers=world["headers"](), json=payload)


async def _audits(action: str) -> list[AuditLog]:
    async with get_sessionmaker()() as session:
        rows = (
            (await session.execute(sa.select(AuditLog).where(AuditLog.action == action)))
            .scalars()
            .all()
        )
    return list(rows)


# ── crear ──────────────────────────────────────────────────────────────


async def test_creating_a_teammate_turns_the_switches_into_a_catalogue(
    client, db_session, console_world
):
    a = console_world["a"]
    await _only_models(db_session, a["partner_id"], SOL)

    response = await _create(client, a, permissions={**READ_ONLY, "write": True})

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Sofía" and body["status"] == "active"
    assert body["tool_names"] == permissions_to_tool_names({**READ_ONLY, "write": True})
    # Lo que el interruptor de escritura NO trae: publicar, gastar ni invitar.
    assert "console.propose_publish" not in body["tool_names"]
    assert "console.propose_allocation" not in body["tool_names"]
    assert "console.propose_invite" not in body["tool_names"]
    # Y el estado de la persona que acaba de crearlo: aún no hay hilo.
    assert body["my_state"] == "en_espera" and body["my_thread_id"] is None


async def test_the_new_teammate_belongs_to_the_partner_and_the_thread_does_not(
    client, db_session, console_world
):
    """R2.2 y garantía 1: el roster es del partner, el hilo es de la persona."""
    a = console_world["a"]
    await _only_models(db_session, a["partner_id"], SOL)
    other = await add_console_member(db_session, partner_id=a["partner_id"], role="builder")

    created = await _create(client, a)
    assert created.status_code == 201, created.text

    roster = await client.get("/console/teammates", headers=other["headers"]())
    assert roster.status_code == 200, roster.text
    mine = [t for t in roster.json() if t["id"] == created.json()["id"]]
    assert len(mine) == 1
    assert mine[0]["my_thread_id"] is None, "el teammate se comparte; el hilo, no"


async def test_the_machine_is_never_part_of_the_catalogue(client, db_session, console_world):
    """R4.2 — ``shell_local`` no lo trae ningún interruptor: depende de
    ``local_exec`` **y** de que haya máquina, y eso se decide en el turno."""
    a = console_world["a"]
    await _only_models(db_session, a["partner_id"], SOL)

    response = await _create(client, a, permissions=ALL_ON, local_exec=True)

    assert response.status_code == 201, response.text
    assert "shell_local" not in response.json()["tool_names"]


async def test_a_model_outside_the_partners_list_is_refused(client, db_session, console_world):
    a = console_world["a"]
    await _only_models(db_session, a["partner_id"], SOL)

    response = await _create(client, a, model="openai/gpt-5.6-luna")

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "model_not_allowed"


async def test_the_form_cannot_smuggle_a_tool_the_switches_do_not_give(
    client, db_session, console_world
):
    """La aplicación no elige el catálogo. Aunque el cuerpo traiga
    ``tool_names``, lo que se guarda es lo que los interruptores dan."""
    a = console_world["a"]
    await _only_models(db_session, a["partner_id"], SOL)

    response = await client.post(
        "/console/teammates",
        headers=a["headers"](),
        json={
            "name": "Colada",
            "job": "Desarrollo",
            "model": SOL,
            "permissions": READ_ONLY,
            "tool_names": ["console.apply", "shell_local"],
        },
    )

    assert response.status_code in (201, 422), response.text
    if response.status_code == 201:
        assert response.json()["tool_names"] == permissions_to_tool_names(READ_ONLY)


async def test_a_name_outside_the_catalogue_is_refused_not_ignored(
    client, db_session, console_world, monkeypatch
):
    """La guardia de ``validate_tool_names`` está **puesta**, no decorando.

    Desde el formulario no se puede llegar aquí —los interruptores solo dan
    nombres del catálogo—, así que se fuerza el único camino que quedaría si
    alguien cambiara el mapeo: un nombre que no existe. Ignorarlo sería peor
    que el error, porque el teammate quedaría con menos herramientas de las que
    la pantalla dice.
    """
    a = console_world["a"]
    await _only_models(db_session, a["partner_id"], SOL)
    monkeypatch.setattr(
        "nexus_api.api.console.teammates.permissions_to_tool_names",
        lambda perms: ["console.whoami", "console.inventar_algo"],
    )

    response = await _create(client, a)

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "tool_not_in_catalog"


async def test_a_name_longer_than_eighty_is_refused(client, db_session, console_world):
    a = console_world["a"]
    await _only_models(db_session, a["partner_id"], SOL)
    response = await _create(client, a, name="x" * 81)
    assert response.status_code == 422


# ── cambiar ────────────────────────────────────────────────────────────


async def _seed(db_session, partner_id: uuid.UUID, **over) -> Teammate:
    row = Teammate(
        id=uuid.uuid4(),
        partner_id=partner_id,
        name="Nilo",
        job="Desarrollo",
        model=SOL,
        tool_names=permissions_to_tool_names(READ_ONLY),
        permissions=dict(READ_ONLY),
        local_exec=False,
        created_by="seed",
        status=over.pop("status", "active"),
        **over,
    )
    db_session.add(row)
    await db_session.commit()
    return row


async def test_changing_the_permissions_changes_what_the_model_sees_next_turn(
    client, db_session, console_world
):
    a = console_world["a"]
    await _only_models(db_session, a["partner_id"], SOL)
    nilo = await _seed(db_session, a["partner_id"])
    before = for_teammate(nilo, mode="build", machine_present=False)

    response = await client.patch(
        f"/console/teammates/{nilo.id}",
        headers=a["headers"](),
        json={"permissions": {**READ_ONLY, "write": True}},
    )

    assert response.status_code == 200, response.text
    after = response.json()["tool_names"]
    assert set(after) > set(before), "escribir añade herramientas, no las cambia de sitio"
    await db_session.refresh(nilo)
    assert for_teammate(nilo, mode="build", machine_present=False) == after


async def test_changing_the_job_leaves_a_note_in_the_thread_of_each_person(
    client, db_session, console_world
):
    """R2.4 — el cambio se anota, y se ve **en el hilo de cada persona**,
    incluido el de quien no lo hizo."""
    a = console_world["a"]
    other = await add_console_member(db_session, partner_id=a["partner_id"], role="builder")
    nilo = await _seed(db_session, a["partner_id"])
    thread = CompanionThread(
        id=uuid.uuid4(),
        principal_id=other["user_id"],
        partner_id=a["partner_id"],
        teammate_id=nilo.id,
        title="lo mío con Nilo",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(thread)
    await db_session.commit()

    changed = await client.patch(
        f"/console/teammates/{nilo.id}", headers=a["headers"](), json={"job": "Finanzas"}
    )
    assert changed.status_code == 200, changed.text

    notes = await client.get(f"/console/teammates/{nilo.id}/changes", headers=other["headers"]())
    assert notes.status_code == 200, notes.text
    body = notes.json()
    assert len(body) == 1
    assert body[0]["fields"] == ["job"]
    assert "content" not in body[0] and "text" not in body[0]


async def test_renaming_does_not_pretend_the_catalogue_changed(client, db_session, console_world):
    a = console_world["a"]
    nilo = await _seed(db_session, a["partner_id"])

    renamed = await client.patch(
        f"/console/teammates/{nilo.id}", headers=a["headers"](), json={"name": "Nilo B."}
    )

    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Nilo B."
    notes = await client.get(f"/console/teammates/{nilo.id}/changes", headers=a["headers"]())
    assert notes.json() == [], "cambiar el nombre no cambia lo que el teammate puede hacer"


async def test_an_archived_teammate_cannot_be_changed(client, db_session, console_world):
    a = console_world["a"]
    nilo = await _seed(
        db_session, a["partner_id"], status="archived", archived_at=datetime.now(UTC)
    )

    response = await client.patch(
        f"/console/teammates/{nilo.id}", headers=a["headers"](), json={"name": "otro"}
    )

    assert response.status_code == 404


async def test_a_teammate_of_another_partner_does_not_exist(client, db_session, console_world):
    a, b = console_world["a"], console_world["b"]
    theirs = await _seed(db_session, b["partner_id"])

    patched = await client.patch(
        f"/console/teammates/{theirs.id}", headers=a["headers"](), json={"name": "mío"}
    )
    archived = await client.delete(f"/console/teammates/{theirs.id}", headers=a["headers"]())

    assert patched.status_code == 404, "404 opaco: ni «no puedes», ni el nombre ajeno"
    assert archived.status_code == 404
    async with get_sessionmaker()() as session:
        await apply_partner_to_session(session, b["partner_id"])
        still = await session.get(Teammate, theirs.id)
        assert still is not None and still.status == "active"


# ── el asiento ─────────────────────────────────────────────────────────


async def test_the_three_acts_are_audited_with_the_person(client, db_session, console_world):
    a = console_world["a"]
    await _only_models(db_session, a["partner_id"], SOL)

    created = await _create(client, a)
    assert created.status_code == 201, created.text
    teammate_id = created.json()["id"]
    await client.patch(
        f"/console/teammates/{teammate_id}", headers=a["headers"](), json={"job": "Finanzas"}
    )
    await client.delete(f"/console/teammates/{teammate_id}", headers=a["headers"]())

    for action in ("teammate.created", "teammate.updated", "teammate.archived"):
        rows = await _audits(action)
        assert len(rows) == 1, action
        assert str(rows[0].actor).startswith("console:"), action
        # Un teammate nunca es el actor, y el asiento no lleva cuerpos.
        assert "content" not in (rows[0].after_json or {})


# ── la lista de oficios y modelos ──────────────────────────────────────


async def test_the_jobs_endpoint_says_what_each_model_costs(client, db_session, console_world):
    a = console_world["a"]
    await _only_models(db_session, a["partner_id"], SOL, "openai/gpt-5.6-terra")

    response = await client.get("/console/teammates/jobs", headers=a["headers"]())

    assert response.status_code == 200, response.text
    models = {m["id"]: m for m in response.json()["models"]}
    assert set(models) == {SOL, "openai/gpt-5.6-terra"}
    for model in models.values():
        assert model["note"], "un modelo sin nota es una fila que no ayuda a elegir"
        assert model["cost_label"] in ("bajo", "medio", "alto", "desconocido")
