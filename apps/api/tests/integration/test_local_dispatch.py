"""Requisitos 3.3, 10.5 y 11.1 — el despacho a la máquina, de punta a punta.

La 001 dejó el puente saliente, el gate, la contención y la auditoría, y dejó
``poll`` devolviendo ``work: []`` con un comentario: «el despachador llega con
la ejecución real». Esto lo recorre entero: un teammate pide ejecutar, la
plataforma decide, la máquina lo recoge **una sola vez**, contesta, y lo que
escribió el programa llega al modelo como dato — sin quedarse en la auditoría.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from nexus_api.core.tenant_context import apply_tenant_to_session, tenant_context
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AuditLog,
    DeviceClientLink,
    LocalExecutable,
    LocalExecution,
    PartnerDevice,
)
from nexus_api.db.models.local_workstation import (
    DENIAL_DISPOSITIVO_AUSENTE,
    DENIAL_EJECUTABLE_NO_PERMITIDO,
    DENIAL_POLITICA_NUNCA,
    EXEC_ALWAYS,
    EXEC_NEVER,
    OUTCOME_PENDIENTE,
)
from nexus_api.services.device_credential import issue_device_token

pytestmark = pytest.mark.asyncio

MAKE = "make"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _machine(
    db_session, world, *, present: bool = True, workdir: str | None = "/tmp/cliente"
):
    device = PartnerDevice(
        id=uuid.uuid4(),
        partner_id=world["partner_id"],
        principal_id=world["user_id"],
        display_name="portátil",
        hostname="portatil.local",
        platform="macos",
        last_heartbeat_at=datetime.now(UTC) if present else datetime.now(UTC) - timedelta(hours=1),
    )
    db_session.add(device)
    await db_session.flush()
    db_session.add(
        DeviceClientLink(
            id=uuid.uuid4(),
            tenant_id=world["tenant_id"],
            device_id=device.id,
            created_by=world["user_id"],
            workdir=workdir,
        )
    )
    db_session.add(
        LocalExecutable(
            id=uuid.uuid4(), tenant_id=world["tenant_id"], executable=MAKE, added_by="auphere"
        )
    )
    await db_session.commit()
    token = issue_device_token(device_id=device.id, partner_id=world["partner_id"], generation=1)
    return device, token


async def _set_pref(client, world, *, mode: str, executable: str | None = None):
    response = await client.put(
        "/console/teammates/local-exec-prefs",
        headers=world["headers"](),
        json={"executable": executable, "mode": mode},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _run(client, world, *, executable: str = MAKE, args: list[str] | None = None):
    return await client.post(
        f"/console/clients/{world['ref']}/workstation/executions",
        headers=world["headers"](),
        json={"executable": executable, "args": args or ["test"]},
    )


async def _machine_answers(
    client, token: str, *, sample: str = "ok\n", outcome: str = "completada"
):
    """Lo que hace la aplicación de escritorio: sondea, ejecuta y contesta."""
    polled = await client.get("/device/poll", headers=_auth(token))
    assert polled.status_code == 200, polled.text
    work = polled.json()["work"]
    for item in work:
        answered = await client.post(
            "/device/result",
            headers=_auth(token),
            json={
                "execution_id": item["execution_id"],
                "outcome": outcome,
                "exit_code": 0,
                "children_reaped": 0,
                "stdout_sample": sample,
            },
        )
        assert answered.status_code == 204, answered.text
    return work


# ── el recorrido entero ────────────────────────────────────────────────


async def test_an_allowed_command_reaches_the_machine_and_its_output_comes_back(
    client, db_session, console_world
):
    a = console_world["a"]
    _device, token = await _machine(db_session, a)
    await _set_pref(client, a, mode=EXEC_ALWAYS)

    running = asyncio.create_task(_run(client, a))
    await asyncio.sleep(0.2)
    work = await _machine_answers(client, token, sample="4 de 4 en verde\n")
    response = await running

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision"] == "permitida"
    assert body["outcome"] == "completada"
    assert body["exit_code"] == 0
    assert body["stdout_sample"] == "4 de 4 en verde\n"
    assert body["untrusted"] is True, "lo que escribe un programa es dato, y hay que decirlo"

    # Y el trabajo llegó con lo que la máquina necesita para ejecutarlo.
    assert len(work) == 1
    assert work[0]["executable"] == MAKE
    assert work[0]["args"] == ["test"]
    assert work[0]["client_ref"] == a["ref"]
    assert work[0]["timeout_ms"] > 0 and work[0]["idle_timeout_ms"] > 0


async def test_the_same_work_is_never_handed_out_twice(client, db_session, console_world):
    a = console_world["a"]
    _device, token = await _machine(db_session, a)
    await _set_pref(client, a, mode=EXEC_ALWAYS)

    running = asyncio.create_task(_run(client, a))
    await asyncio.sleep(0.2)
    first = await client.get("/device/poll", headers=_auth(token))
    second = await client.get("/device/poll", headers=_auth(token))
    assert len(first.json()["work"]) == 1
    assert second.json()["work"] == [], "un sondeo mientras ejecuta no repite el comando"
    # Se contesta lo que dio el PRIMER sondeo: el segundo ya no lo trae, que es
    # justo lo que este test afirma.
    answered = await client.post(
        "/device/result",
        headers=_auth(token),
        json={
            "execution_id": first.json()["work"][0]["execution_id"],
            "outcome": "completada",
            "exit_code": 0,
            "children_reaped": 0,
        },
    )
    assert answered.status_code == 204, answered.text
    await running


async def test_the_output_never_lands_in_the_audit_row(client, db_session, console_world):
    """§III y 001-R8: la auditoría dice qué pasó, no qué dijo el comando."""
    a = console_world["a"]
    _device, token = await _machine(db_session, a)
    await _set_pref(client, a, mode=EXEC_ALWAYS)
    running = asyncio.create_task(_run(client, a))
    await asyncio.sleep(0.2)
    await _machine_answers(client, token, sample="una contraseña que no debe guardarse")
    await running

    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_tenant_to_session(session, a["tenant_id"])
        with tenant_context(a["tenant_id"]):
            row = (
                (
                    await session.execute(
                        sa.select(LocalExecution).order_by(LocalExecution.started_at)
                    )
                )
                .scalars()
                .first()
            )
            assert row is not None
            assert row.outcome == "completada"
            assert row.exit_code == 0
            assert row.principal_id == a["user_id"]
            assert "contraseña" not in str(row.__dict__)


async def test_asking_is_the_default_and_nothing_is_dispatched(client, db_session, console_world):
    a = console_world["a"]
    _device, token = await _machine(db_session, a)

    response = await _run(client, a)
    assert response.status_code == 200, response.text
    assert response.json()["decision"] == "requiere_aprobacion"
    assert response.json()["argv_signature"]

    polled = await client.get("/device/poll", headers=_auth(token))
    assert polled.json()["work"] == [], "pedir permiso no encola nada"


async def test_never_denies_with_its_own_reason_and_leaves_the_audit_row(
    client, db_session, console_world
):
    a = console_world["a"]
    await _machine(db_session, a)
    await _set_pref(client, a, mode=EXEC_NEVER)

    response = await _run(client, a)
    assert response.json()["decision"] == "denegada"
    assert response.json()["denial_code"] == DENIAL_POLITICA_NUNCA

    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_tenant_to_session(session, a["tenant_id"])
        with tenant_context(a["tenant_id"]):
            row = (await session.execute(sa.select(LocalExecution))).scalars().first()
            assert row is not None and row.denial_reason == DENIAL_POLITICA_NUNCA


async def test_an_executable_outside_the_whitelist_is_denied_whatever_the_policy(
    client, db_session, console_world
):
    a = console_world["a"]
    await _machine(db_session, a)
    await _set_pref(client, a, mode=EXEC_ALWAYS)

    response = await _run(client, a, executable="curl", args=["https://evil"])
    assert response.json()["decision"] == "denegada"
    assert response.json()["denial_code"] == DENIAL_EJECUTABLE_NO_PERMITIDO


async def test_without_a_present_machine_it_refuses_without_writing_pending_work(
    client, db_session, console_world
):
    """R3.5: la máquina ausente es una espera diseñada, no un error."""
    a = console_world["a"]
    await _machine(db_session, a, present=False)
    await _set_pref(client, a, mode=EXEC_ALWAYS)

    response = await _run(client, a)
    assert response.json()["decision"] == "denegada"
    assert response.json()["denial_code"] == DENIAL_DISPOSITIVO_AUSENTE

    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_tenant_to_session(session, a["tenant_id"])
        with tenant_context(a["tenant_id"]):
            pending = (
                (
                    await session.execute(
                        sa.select(LocalExecution).where(LocalExecution.outcome == OUTCOME_PENDIENTE)
                    )
                )
                .scalars()
                .all()
            )
            assert pending == []


async def test_a_client_without_a_declared_directory_gets_no_work(
    client, db_session, console_world
):
    """002-R7.5: sin directorio no hay dónde ejecutar."""
    a = console_world["a"]
    _device, token = await _machine(db_session, a, workdir=None)
    await _set_pref(client, a, mode=EXEC_ALWAYS)
    response = await _run(client, a)
    assert response.json()["decision"] == "denegada"
    assert response.json()["denial_code"] == DENIAL_DISPOSITIVO_AUSENTE
    polled = await client.get("/device/poll", headers=_auth(token))
    assert polled.json()["work"] == []


async def test_every_decision_is_audited_with_the_person(client, db_session, console_world):
    a = console_world["a"]
    _device, token = await _machine(db_session, a)
    await _set_pref(client, a, mode=EXEC_ALWAYS)
    running = asyncio.create_task(_run(client, a))
    await asyncio.sleep(0.2)
    await _machine_answers(client, token)
    await running

    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_tenant_to_session(session, a["tenant_id"])
        with tenant_context(a["tenant_id"]):
            rows = (
                (
                    await session.execute(
                        sa.select(AuditLog).where(AuditLog.action.like("local_exec.%"))
                    )
                )
                .scalars()
                .all()
            )
            assert [r.action for r in rows] == ["local_exec.allowed_by_policy"]
            # El actor es la PERSONA de la consola, nunca el teammate
            # (`[[00-revision-del-diseno-v3]]` §5.6).
            assert str(rows[0].actor).startswith("console:")
            assert "teammate" not in str(rows[0].actor)
            assert rows[0].after_json["executable"] == MAKE


# ── la aprobación no se puede falsificar ───────────────────────────────
#
# Aplicar una ejecución confirmada entra por **la misma puerta**. No lleva
# ningún campo que diga «esto ya está aprobado»: la ruta **busca** la acción
# confirmada con esta firma, y una acción confirmada solo existe si una persona
# la confirmó. Estos tres tests son esa frase, comprobada.


async def _confirmed_action(
    db_session, world, *, executable: str, args: list[str], status: str = "confirmed"
):
    """Una acción de máquina ya confirmada por la persona."""
    from nexus_api.db.models.companion import CompanionAction, CompanionThread
    from nexus_api.services.local_exec_gate import argv_signature

    thread = CompanionThread(
        id=uuid.uuid4(),
        principal_id=world["user_id"],
        partner_id=world["partner_id"],
        tenant_id=world["tenant_id"],
        title="t",
    )
    db_session.add(thread)
    await db_session.flush()
    action = CompanionAction(
        id=uuid.uuid4(),
        thread_id=thread.id,
        kind="local_exec",
        status=status,
        level="critico",
        payload={
            "title": "Ejecutar",
            "preview": {
                "executable": executable,
                "args": args,
                "argv_signature": argv_signature(args),
            },
        },
        proposed_at=datetime.now(UTC),
        decided_at=datetime.now(UTC),
        decided_by=world["user_id"],
    )
    db_session.add(action)
    await db_session.commit()
    return action


async def test_a_confirmed_action_lets_the_same_command_through_and_leaves_a_grant(
    client, db_session, console_world
):
    from nexus_api.core.tenant_context import apply_tenant_to_session
    from nexus_api.db.models import LocalArgumentGrant

    a = console_world["a"]
    _device, token = await _machine(db_session, a)
    await _confirmed_action(db_session, a, executable=MAKE, args=["test"])

    running = asyncio.create_task(_run(client, a))
    await asyncio.sleep(0.2)
    await _machine_answers(client, token)
    response = await running
    assert response.json()["decision"] == "permitida"

    # Y queda el permiso durable de esos argumentos, con la acción que lo dio
    # (001-R2.5): el mismo comando exacto no vuelve a preguntar.
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_tenant_to_session(session, a["tenant_id"])
        with tenant_context(a["tenant_id"]):
            grants = (await session.execute(sa.select(LocalArgumentGrant))).scalars().all()
            assert len(grants) == 1
            assert grants[0].action_id is not None


async def test_a_confirmed_action_for_other_arguments_does_not_let_this_one_through(
    client, db_session, console_world
):
    a = console_world["a"]
    await _machine(db_session, a)
    await _confirmed_action(db_session, a, executable=MAKE, args=["deploy"])

    response = await _run(client, a, args=["test"])
    assert response.json()["decision"] == "requiere_aprobacion", (
        "un sí a `make deploy` no es un sí a `make test`"
    )


async def test_a_proposed_action_is_not_an_approval(client, db_session, console_world):
    """Lo que el modelo puede crear es una acción **propuesta**. No basta."""
    a = console_world["a"]
    await _machine(db_session, a)
    await _confirmed_action(db_session, a, executable=MAKE, args=["test"], status="proposed")

    response = await _run(client, a, args=["test"])
    assert response.json()["decision"] == "requiere_aprobacion"
