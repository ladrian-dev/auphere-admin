"""Ejecutar una rutina desde la consola — spec 082, T020 (requisito 6).

Lo que se prueba aquí es lo que la ruta deja escrito antes de que el worker
toque nada: la ejecución abierta, el trabajo encolado con lo justo dentro, y
las dos puertas que cierran antes de gastar.

«Probar ahora» no crea rutina **ni ejecución**: el historial es de las rutinas
que existen, y una prueba no es una de ellas.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import Job, ScheduleRun
from tests.conftest import add_console_member

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _agent(db_session: AsyncSession, tenant_id: uuid.UUID) -> str:
    agent_id = uuid.uuid4()
    await db_session.execute(
        sa.text(
            "INSERT INTO agents (id, tenant_id, name, lifecycle) "
            "VALUES (:a, :t, 'Soporte', 'published')"
        ),
        {"a": str(agent_id), "t": str(tenant_id)},
    )
    await db_session.commit()
    return str(agent_id)


async def _bag(db_session: AsyncSession, tenant_id: uuid.UUID, partner_id: uuid.UUID) -> None:
    """Una bolsa con saldo: sin ella la ruta cierra antes de gastar."""
    await db_session.execute(
        sa.text(
            "INSERT INTO client_wallets "
            "(tenant_id, partner_id, currency, balance_micros, month) "
            "VALUES (:t, :p, 'USD', 1000000, date_trunc('month', now())::date) "
            "ON CONFLICT (tenant_id) DO UPDATE SET balance_micros = 1000000"
        ),
        {"t": str(tenant_id), "p": str(partner_id)},
    )
    await db_session.commit()


@pytest.fixture
async def world(db_session: AsyncSession, console_world: dict[str, Any]) -> dict[str, Any]:
    a = console_world["a"]
    await _bag(db_session, a["tenant_id"], a["partner_id"])
    return {
        "ref": a["ref"],
        "tenant_id": a["tenant_id"],
        "partner_id": a["partner_id"],
        "headers": a["headers"],
        "agent_id": await _agent(db_session, a["tenant_id"]),
    }


def _url(world: dict[str, Any], tail: str = "") -> str:
    return f"/console/clients/{world['ref']}/schedules{tail}"


async def _make(client: Any, world: dict[str, Any]) -> dict[str, Any]:
    body = {
        "agent_id": world["agent_id"],
        "name": "Altas de ayer",
        "instruction": "Dime cuántos pedidos entraron ayer.",
        "cadence": "daily",
        "local_time": "09:00",
    }
    resp = await client.post(_url(world), json=body, headers=world["headers"]())
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_running_now_opens_a_run_and_queues_a_job(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    made = await _make(client, world)
    resp = await client.post(_url(world, f"/{made['id']}/run"), headers=world["headers"]())
    assert resp.status_code == 202, resp.text
    body = resp.json()

    run = await db_session.scalar(
        sa.select(ScheduleRun).where(ScheduleRun.id == uuid.UUID(body["run_id"]))
    )
    assert run is not None
    assert run.trigger == "manual"
    assert run.status == "running"
    # La instrucción queda congelada en la ejecución, no se lee del trabajo.
    assert run.instruction == "Dime cuántos pedidos entraron ayer."

    job = await db_session.scalar(sa.select(Job).where(Job.id == uuid.UUID(body["job_id"])))
    assert job is not None
    assert job.kind == "schedule_run"
    assert job.progress["input"] == {
        "schedule_id": made["id"],
        "run_id": body["run_id"],
    }


async def test_running_twice_in_the_same_instant_opens_one_run(
    client: Any, world: dict[str, Any]
) -> None:
    """La clave única de la ranura: dos peticiones a la vez no abren dos."""
    made = await _make(client, world)
    first = await client.post(_url(world, f"/{made['id']}/run"), headers=world["headers"]())
    second = await client.post(_url(world, f"/{made['id']}/run"), headers=world["headers"]())
    assert first.status_code == second.status_code == 202
    # Instantes distintos: son dos ejecuciones distintas y eso está bien.
    assert first.json()["run_id"] != second.json()["run_id"]


async def test_an_empty_bag_stops_it_before_spending(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    made = await _make(client, world)
    await db_session.execute(
        sa.text("UPDATE client_wallets SET balance_micros = 0 WHERE tenant_id = :t"),
        {"t": str(world["tenant_id"])},
    )
    await db_session.commit()

    resp = await client.post(_url(world, f"/{made['id']}/run"), headers=world["headers"]())
    assert resp.status_code == 409
    assert resp.json()["detail"] == "bag_empty"


async def test_trying_creates_neither_a_routine_nor_a_run(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    resp = await client.post(
        f"/console/clients/{world['ref']}/agents/{world['agent_id']}/schedules/try",
        json={"instruction": "Dime qué pasó ayer."},
        headers=world["headers"](),
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["run_id"] is None
    assert body["schedule_id"] is None

    # Ni rutina ni ejecución: la instrucción viaja en el trabajo.
    page = (await client.get(_url(world), headers=world["headers"]())).json()
    assert page["counts"]["all"] == 0
    runs = await db_session.scalar(sa.select(sa.func.count()).select_from(ScheduleRun))
    assert runs == 0

    job = await db_session.scalar(sa.select(Job).where(Job.id == uuid.UUID(body["job_id"])))
    assert job is not None
    assert job.progress["input"]["instruction"] == "Dime qué pasó ayer."


async def test_an_analyst_cannot_run_one(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    made = await _make(client, world)
    analyst = await add_console_member(db_session, partner_id=world["partner_id"], role="analyst")
    resp = await client.post(_url(world, f"/{made['id']}/run"), headers=analyst["headers"]())
    assert resp.status_code == 403
