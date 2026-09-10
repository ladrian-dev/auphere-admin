"""Requisitos 3.2 y 6 — la tarea sobrevive al turno, y la aprobación la espera.

Un run del Companion muere a los 300 s y un aparcado más viejo se da por
muerto. Una aprobación de teammate que caducara por eso sería una pantalla que
miente: aquí se prueba lo contrario — el run cierra en ``waiting``, la **tarea**
queda ``esperandote``, la acción no caduca por reloj, y decidir abre un run
nuevo en la misma tarea.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from nexus_worker.runtime.llm import InMemoryProvider, ToolCall

from nexus_api.api.console import companion as companion_api
from nexus_api.core.principal_context import apply_principal_to_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Teammate
from nexus_api.db.models.companion import (
    RUN_WAITING,
    CompanionAction,
    CompanionRun,
    TeammateTask,
)

pytestmark = pytest.mark.asyncio

NEW_PROMPT = "Responde en el idioma del cliente y nunca des precios por WhatsApp."


@pytest.fixture
def teammate_provider():
    """Un proveedor que propone un cambio en el primer turno y calla después."""

    def _install(*rounds: list[tuple[str, dict]]) -> InMemoryProvider:
        seen = {"n": 0}

        def _caller(_call):
            i = seen["n"]
            seen["n"] += 1
            if i >= len(rounds):
                return []
            return [ToolCall(id=f"t{i}", name=name, arguments=args) for name, args in rounds[i]]

        provider = InMemoryProvider(responder=lambda _c: "Preparado.", tool_caller=_caller)
        companion_api.set_provider_for_tests(provider)
        return provider

    yield _install
    companion_api.reset_graph_cache_for_tests()


async def _teammate(db_session, world, *, name: str = "Sofía") -> uuid.UUID:
    row = Teammate(
        id=uuid.uuid4(),
        partner_id=world["partner_id"],
        name=name,
        job="Atención al cliente",
        model="anthropic/claude-sonnet-4-6",
        tool_names=[
            "console.whoami",
            "console.list_clients",
            "console.propose_prompt",
            "console.apply",
        ],
        permissions={
            "read": True,
            "write": True,
            "spend": False,
            "publish": False,
            "contact": False,
        },
        local_exec=False,
        created_by=world["user_id"],
    )
    db_session.add(row)
    await db_session.commit()
    return row.id


async def _thread(client, world, teammate_id: uuid.UUID) -> str:
    created = await client.post(
        "/console/companion/threads",
        headers=world["headers"](),
        json={"title": "t", "mode": "build", "teammate_id": str(teammate_id)},
    )
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


async def _turn(client, world, thread_id: str, prompt: str = "cambia el prompt") -> str:
    started = await client.post(
        f"/console/companion/threads/{thread_id}/runs",
        headers=world["headers"](),
        json={"prompt": prompt},
    )
    assert started.status_code == 202, started.text
    return str(started.json()["run_id"])


async def _wait(query, principal_id: str, *, timeout: float = 10.0):
    """Espera a que una consulta devuelva algo. El POST es 202 y el trabajo sigue."""
    sm = get_sessionmaker()
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        async with sm() as session, session.begin():
            await apply_principal_to_session(session, principal_id)
            row = (await session.execute(query)).scalars().first()
            if row is not None:
                await session.refresh(row)
                return row
        await asyncio.sleep(0.05)
    raise AssertionError("no llegó a tiempo")


async def _task_of(thread_id: str, principal_id: str) -> TeammateTask:
    return await _wait(
        sa.select(TeammateTask).where(TeammateTask.thread_id == uuid.UUID(thread_id)), principal_id
    )


async def _waiting_run(run_id: str, principal_id: str) -> CompanionRun:
    return await _wait(
        sa.select(CompanionRun).where(
            CompanionRun.id == uuid.UUID(run_id), CompanionRun.status == RUN_WAITING
        ),
        principal_id,
    )


async def _propose(
    client, db_session, world, teammate_provider
) -> tuple[str, str, CompanionAction]:
    teammate_provider(
        [("console.propose_prompt", {"client_ref": world["ref"], "system_prompt": NEW_PROMPT})]
    )
    teammate_id = await _teammate(db_session, world)
    thread_id = await _thread(client, world, teammate_id)
    run_id = await _turn(client, world, thread_id)
    action = await _wait(
        sa.select(CompanionAction).order_by(CompanionAction.proposed_at.desc()), world["user_id"]
    )
    return thread_id, run_id, action


# ── la tarea nace con el turno y sobrevive al run ──────────────────────


async def test_a_teammate_turn_opens_a_task_and_the_run_belongs_to_it(
    client, db_session, console_world, teammate_provider
):
    a = console_world["a"]
    teammate_provider()
    teammate_id = await _teammate(db_session, a)
    thread_id = await _thread(client, a, teammate_id)
    run_id = await _turn(client, a, thread_id, "hola")
    task = await _task_of(thread_id, a["user_id"])
    assert task.teammate_id == teammate_id
    assert task.principal_id == a["user_id"]
    assert task.title
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_principal_to_session(session, a["user_id"])
        run = await session.get(CompanionRun, uuid.UUID(run_id))
        assert run is not None and run.task_id == task.id


async def test_parking_closes_the_run_as_waiting_and_the_task_waits_for_the_person(
    client, db_session, console_world, teammate_provider
):
    a = console_world["a"]
    thread_id, run_id, action = await _propose(client, db_session, a, teammate_provider)
    run = await _waiting_run(run_id, a["user_id"])
    assert run.ended_at is not None, "un run que espera está cerrado: la tarea es la que sigue viva"
    task = await _task_of(thread_id, a["user_id"])
    assert task.state == "esperandote"
    assert task.pending_action_id == action.id
    assert action.task_id == task.id


async def test_a_teammate_action_does_not_expire_by_the_clock(
    client, db_session, console_world, teammate_provider
):
    """Es la enmienda acotada de §IV: la espera la marca la tarea, no un reloj."""
    a = console_world["a"]
    _thread_id, run_id, action = await _propose(client, db_session, a, teammate_provider)
    await _waiting_run(run_id, a["user_id"])
    # Muy por encima del TTL de las acciones del Companion (15 min).
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_principal_to_session(session, a["user_id"])
        await session.execute(
            sa.update(CompanionAction)
            .where(CompanionAction.id == action.id)
            .values(proposed_at=datetime.now(UTC) - timedelta(hours=6))
        )
    card = await client.get(f"/console/companion/actions/{action.id}", headers=a["headers"]())
    assert card.status_code == 200, card.text
    assert card.json()["status"] == "proposed"
    assert card.json()["expires_at"] is None, "sin caducidad por reloj: espera a la tarea"


async def test_deciding_opens_a_new_run_in_the_same_task(
    client, db_session, console_world, teammate_provider
):
    a = console_world["a"]
    thread_id, run_id, action = await _propose(client, db_session, a, teammate_provider)
    await _waiting_run(run_id, a["user_id"])
    task_before = await _task_of(thread_id, a["user_id"])

    resumed = await client.post(
        f"/console/companion/runs/{run_id}/resume",
        headers=a["headers"](),
        json={"action_id": str(action.id), "decision": "cancel", "note": "ahora no"},
    )
    assert resumed.status_code == 202, resumed.text
    new_run_id = resumed.json()["run_id"]
    assert new_run_id != run_id

    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_principal_to_session(session, a["user_id"])
        new_run = await session.get(CompanionRun, uuid.UUID(new_run_id))
        assert new_run is not None and new_run.task_id == task_before.id
        task = await session.get(TeammateTask, task_before.id)
        assert task is not None
        assert task.pending_action_id is None
        assert task.state in {"en_marcha", "terminada"}


# ── el final de una tarea ──────────────────────────────────────────────


async def test_an_expired_task_closes_its_action_with_a_cause(
    client, db_session, console_world, teammate_provider
):
    a = console_world["a"]
    thread_id, run_id, action = await _propose(client, db_session, a, teammate_provider)
    await _waiting_run(run_id, a["user_id"])
    task = await _task_of(thread_id, a["user_id"])

    from nexus_api.repositories.teammate_tasks import TeammateTaskRepository

    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_principal_to_session(session, a["user_id"])
        await session.execute(
            sa.update(TeammateTask)
            .where(TeammateTask.id == task.id)
            .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )
    async with sm() as session, session.begin():
        swept = await TeammateTaskRepository(session).expire_due()
    assert swept == 1

    async with sm() as session, session.begin():
        await apply_principal_to_session(session, a["user_id"])
        fresh_task = await session.get(TeammateTask, task.id)
        fresh_action = await session.get(CompanionAction, action.id)
        assert fresh_task is not None and fresh_task.state == "caducada"
        assert fresh_action is not None and fresh_action.status == "expired"
        assert (fresh_action.result or {}).get("cause") == "task_expired"


async def test_archiving_a_teammate_cancels_what_was_waiting(
    client, db_session, console_world, teammate_provider
):
    a = console_world["a"]
    thread_id, run_id, action = await _propose(client, db_session, a, teammate_provider)
    await _waiting_run(run_id, a["user_id"])
    task = await _task_of(thread_id, a["user_id"])

    archived = await client.delete(f"/console/teammates/{task.teammate_id}", headers=a["headers"]())
    assert archived.status_code == 204, archived.text

    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_principal_to_session(session, a["user_id"])
        fresh_task = await session.get(TeammateTask, task.id)
        fresh_action = await session.get(CompanionAction, action.id)
        assert fresh_task is not None and fresh_task.state == "cancelada"
        assert fresh_action is not None and fresh_action.status == "expired"
        assert (fresh_action.result or {}).get("cause") == "teammate_archived"


async def test_a_person_can_cancel_her_own_task(
    client, db_session, console_world, teammate_provider
):
    a = console_world["a"]
    thread_id, run_id, _action = await _propose(client, db_session, a, teammate_provider)
    await _waiting_run(run_id, a["user_id"])
    task = await _task_of(thread_id, a["user_id"])

    listed = await client.get("/console/teammates/tasks", headers=a["headers"]())
    assert listed.status_code == 200, listed.text
    assert [t["id"] for t in listed.json()] == [str(task.id)]

    cancelled = await client.post(
        f"/console/teammates/tasks/{task.id}/cancel", headers=a["headers"]()
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["state"] == "cancelada"
    again = await client.post(f"/console/teammates/tasks/{task.id}/cancel", headers=a["headers"]())
    assert again.status_code == 409
