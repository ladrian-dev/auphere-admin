"""El historial de una rutina — spec 082, T026 (requisitos 14.1, 14.2 y 15.2).

El hilo es lo que el partner lee: una ejecución por tarjeta, la más reciente
arriba, paginada por cursor.

Lo que más duele si falla es lo último: **editar la rutina no toca lo ya
hecho**. Cada ejecución guarda la instrucción con la que corrió, así que una
respuesta vieja sigue contestando a la pregunta que se le hizo, y no a la de
ahora. Sin eso, cambiar una palabra reescribiría el pasado entero.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Schedule, ScheduleRun
from nexus_api.services.schedules import runs as runs_service

from .conftest import body as _body
from .conftest import url as _url

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _run(
    tenant_id: uuid.UUID,
    schedule_id: uuid.UUID,
    *,
    minutes_ago: int,
    answer: str,
    instruction: str | None = None,
) -> uuid.UUID:
    """Una ejecución ya cerrada, con la hora que se le diga."""
    when = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        schedule = await session.get(Schedule, schedule_id)
        assert schedule is not None
        if instruction is not None:
            schedule.instruction = instruction
        run = await runs_service.open_run(session, schedule=schedule, scheduled_for=when)
        await runs_service.close(session, run, answer=answer, duration_ms=1200)
        await session.commit()
        return run.id


async def _made(client: Any, world: dict[str, Any]) -> dict[str, Any]:
    resp = await client.post(_url(world), json=_body(world["agent_id"]), headers=world["headers"]())
    assert resp.status_code == 201, resp.text
    return dict(resp.json())


async def test_the_thread_is_newest_first_and_pages_by_cursor(
    client: Any, world: dict[str, Any]
) -> None:
    made = await _made(client, world)
    for i in range(3):
        await _run(world["tenant_id"], uuid.UUID(made["id"]), minutes_ago=i * 10, answer=f"{i}")

    first = await client.get(_url(world, f"/{made['id']}/runs?limit=2"), headers=world["headers"]())
    assert first.status_code == 200, first.text
    page = first.json()
    assert [r["answer"] for r in page["runs"]] == ["0", "1"], "la más reciente arriba"
    assert page["next_cursor"]

    second = await client.get(
        _url(world, f"/{made['id']}/runs?limit=2&cursor={page['next_cursor']}"),
        headers=world["headers"](),
    )
    assert [r["answer"] for r in second.json()["runs"]] == ["2"]
    assert second.json()["next_cursor"] is None


async def test_each_run_keeps_the_instruction_it_ran_with(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    """Requisito 15.2: editar la rutina no reescribe lo ya contestado."""
    made = await _made(client, world)
    await _run(world["tenant_id"], uuid.UUID(made["id"]), minutes_ago=10, answer="catorce")

    changed = await client.patch(
        _url(world, f"/{made['id']}"),
        json={"instruction": "Ahora dime los de la semana."},
        headers=world["headers"](),
    )
    assert changed.status_code == 200, changed.text

    page = (await client.get(_url(world, f"/{made['id']}/runs"), headers=world["headers"]())).json()
    assert page["runs"][0]["instruction"] == made["instruction"]
    assert page["runs"][0]["answer"] == "catorce"


async def test_a_run_carries_its_status_attempts_and_tools(
    client: Any, world: dict[str, Any]
) -> None:
    made = await _made(client, world)
    run_id = await _run(world["tenant_id"], uuid.UUID(made["id"]), minutes_ago=5, answer="hecho")

    page = (await client.get(_url(world, f"/{made['id']}/runs"), headers=world["headers"]())).json()
    row = page["runs"][0]
    assert row["id"] == str(run_id)
    assert (row["status"], row["attempts"], row["trigger"]) == ("done", 1, "schedule")
    assert row["duration_ms"] == 1200
    assert row["tools_used"] == [] and row["withheld"] is None
    assert row["error_code"] is None
    # Todavía no se ha cobrado nada: ``null`` antes que mentir con un cero.
    assert row["spend"] is None


async def test_the_history_of_another_client_is_not_reachable(
    client: Any, world: dict[str, Any]
) -> None:
    made = await _made(client, world)
    sneaked = await client.get(
        f"/console/clients/{world['other_ref']}/schedules/{made['id']}/runs",
        headers=world["headers"](),
    )
    assert sneaked.status_code == 404


async def test_a_routine_without_runs_has_an_empty_thread(
    client: Any, world: dict[str, Any]
) -> None:
    made = await _made(client, world)
    page = (await client.get(_url(world, f"/{made['id']}/runs"), headers=world["headers"]())).json()
    assert page == {"runs": [], "next_cursor": None}


async def test_a_bad_cursor_is_refused_and_does_not_empty_the_thread(
    client: Any, world: dict[str, Any]
) -> None:
    made = await _made(client, world)
    await _run(world["tenant_id"], uuid.UUID(made["id"]), minutes_ago=1, answer="ahí está")
    bad = await client.get(
        _url(world, f"/{made['id']}/runs?cursor=no-es-un-cursor"), headers=world["headers"]()
    )
    assert bad.status_code == 422, "se dice que el cursor está mal, no se devuelve vacío"


async def test_the_runs_are_only_this_routines(client: Any, world: dict[str, Any]) -> None:
    mine = await _made(client, world)
    other = (
        await client.post(
            _url(world),
            json=_body(world["agent_id"], name="Otra cosa", local_time="10:30"),
            headers=world["headers"](),
        )
    ).json()
    await _run(world["tenant_id"], uuid.UUID(other["id"]), minutes_ago=2, answer="de la otra")

    page = (await client.get(_url(world, f"/{mine['id']}/runs"), headers=world["headers"]())).json()
    assert page["runs"] == []


async def test_the_count_of_the_month_sees_the_same_runs(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    """La cifra de la lista y el hilo cuentan lo mismo: si no, el partner ve un
    «3 este mes» y abre tres tarjetas que no son tres."""
    made = await _made(client, world)
    for i in range(2):
        await _run(world["tenant_id"], uuid.UUID(made["id"]), minutes_ago=i + 1, answer=f"{i}")

    listed = (await client.get(_url(world), headers=world["headers"]())).json()
    assert listed["schedules"][0]["month"]["runs"] == 2
    page = (await client.get(_url(world, f"/{made['id']}/runs"), headers=world["headers"]())).json()
    assert len(page["runs"]) == 2
    assert await db_session.scalar(sa.select(sa.func.count()).select_from(ScheduleRun)) >= 2


async def test_what_the_bag_paid_shows_on_its_card(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    """Requisito 14.2: cada tarjeta dice lo que costó, y lo dice **del libro**.

    El cobro en sí está probado en ``test_charge.py``; lo que se mira aquí es
    que el hilo encuentre ese asiento por su referencia. Las dos puntas de esa
    referencia las escribe ``usage_ref_for``, y si una de ellas cambiara sola,
    la tarjeta diría «sin cobrar» para siempre sin que nada fallara.
    """
    from nexus_api.services.wallet.schedules import ENTRY_KIND, usage_ref_for

    made = await _made(client, world)
    run_id = await _run(world["tenant_id"], uuid.UUID(made["id"]), minutes_ago=3, answer="14")

    async with get_sessionmaker()() as session, tenant_scoped_session(session, world["tenant_id"]):
        await session.execute(
            sa.text(
                "INSERT INTO client_wallets (tenant_id, partner_id, currency, balance_micros, "
                "month) VALUES (:t, :p, 'USD', 1000000, date_trunc('month', now())::date) "
                "ON CONFLICT (tenant_id) DO NOTHING"
            ),
            {"t": str(world["tenant_id"]), "p": str(world["partner_id"])},
        )
        await session.execute(
            sa.text(
                "INSERT INTO client_wallet_entries (tenant_id, partner_id, kind, amount_micros, "
                "balance_after_micros, currency, usage_ref) "
                "VALUES (:t, :p, :k, -2000, 998000, 'USD', :ref)"
            ),
            {
                "t": str(world["tenant_id"]),
                "p": str(world["partner_id"]),
                "k": ENTRY_KIND,
                "ref": usage_ref_for(run_id),
            },
        )
        await session.commit()

    page = (await client.get(_url(world, f"/{made['id']}/runs"), headers=world["headers"]())).json()
    assert page["runs"][0]["spend"] == {"amount_micros": 2000, "currency": "USD"}
