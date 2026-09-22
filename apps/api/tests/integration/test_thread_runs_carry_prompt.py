"""El resumen de un run lleva el texto que lo originó — spec 013, Requisito 1.

**El dato ya se guardaba.** Cada turno inserta
``CompanionMessage(role="user", content=body.prompt)`` y ``_thread_history`` lo
lee para armar el contexto del modelo. Lo que no lo devolvía era el listado de
runs, que daba cuatro campos: id, estado y las dos fechas.

Consecuencia en pantalla: la aplicación reconstruye un hilo listando runs y
pidiendo los **eventos** de cada uno, y el mensaje de la persona no es un
evento. Así que al reabrir un hilo se veían las respuestas **sin las preguntas**,
que es una conversación ininteligible.

Un run tiene **exactamente un** mensaje de persona —el que lo disparó—, así que
un campo por run es completo, no una aproximación: por eso es un `JOIN` y no una
segunda lista que la pantalla tendría que casar por `run_id`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from nexus_api.core.principal_context import apply_principal_to_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models.companion import CompanionMessage, CompanionRun, CompanionThread

pytestmark = pytest.mark.asyncio


async def _thread_with_runs(world, prompts: list[str], *, last_running: bool = False) -> uuid.UUID:
    """Un hilo con un run por cada texto, en el orden en que se escribieron."""
    sm = get_sessionmaker()
    thread_id = uuid.uuid4()
    async with sm() as session, session.begin():
        await apply_principal_to_session(session, world["user_id"])
        session.add(
            CompanionThread(
                id=thread_id,
                principal_id=world["user_id"],
                partner_id=world["partner_id"],
                title="t",
                mode="build",
            )
        )
        await session.flush()
        # Sellos distintos y explícitos: `now()` en Postgres es el de la
        # TRANSACCIÓN, así que tres runs creados aquí compartirían
        # `started_at` y el orden quedaría indefinido — cosa que en producción
        # no pasa, porque cada run nace en su propia petición.
        base = datetime.now(UTC) - timedelta(hours=1)
        for i, text in enumerate(prompts):
            run_id = uuid.uuid4()
            running = last_running and i == len(prompts) - 1
            session.add(
                CompanionRun(
                    id=run_id,
                    thread_id=thread_id,
                    principal_id=world["user_id"],
                    status="running" if running else "completed",
                    started_at=base + timedelta(minutes=i),
                )
            )
            await session.flush()
            session.add(
                CompanionMessage(
                    thread_id=thread_id,
                    run_id=run_id,
                    seq=i + 1,
                    role="user",
                    content=text,
                )
            )
    return thread_id


async def test_the_run_summary_carries_what_the_person_wrote(client, console_world):
    a = console_world["a"]
    thread_id = await _thread_with_runs(
        a, ["analiza las ventas de agosto", "y compáralas con julio"]
    )

    listed = await client.get(
        f"/console/companion/threads/{thread_id}/runs", headers=a["headers"]()
    )

    assert listed.status_code == 200, listed.text
    prompts = [r["prompt"] for r in listed.json()["runs"]]
    assert prompts == ["analiza las ventas de agosto", "y compáralas con julio"], (
        "sin esto el hilo devuelve respuestas sin sus preguntas"
    )


async def test_a_live_run_already_carries_it(client, console_world):
    """R1.4 — recargar a mitad de respuesta no puede tragarse lo escrito."""
    a = console_world["a"]
    thread_id = await _thread_with_runs(a, ["lo que acabo de escribir"], last_running=True)

    listed = await client.get(
        f"/console/companion/threads/{thread_id}/runs", headers=a["headers"]()
    )

    assert listed.status_code == 200, listed.text
    run = listed.json()["runs"][0]
    assert run["status"] == "running"
    assert run["prompt"] == "lo que acabo de escribir"


async def test_a_run_without_a_message_row_says_nothing_rather_than_empty(client, console_world):
    """`null` es la anomalía, y se dice como ausencia y no como cadena vacía:
    una burbuja en blanco afirmaría que alguien escribió algo."""
    a = console_world["a"]
    sm = get_sessionmaker()
    thread_id = uuid.uuid4()
    async with sm() as session, session.begin():
        await apply_principal_to_session(session, a["user_id"])
        session.add(
            CompanionThread(
                id=thread_id,
                principal_id=a["user_id"],
                partner_id=a["partner_id"],
                title="t",
                mode="build",
            )
        )
        await session.flush()
        session.add(
            CompanionRun(
                id=uuid.uuid4(),
                thread_id=thread_id,
                principal_id=a["user_id"],
                status="completed",
                started_at=sa.func.now(),
            )
        )

    listed = await client.get(
        f"/console/companion/threads/{thread_id}/runs", headers=a["headers"]()
    )

    assert listed.status_code == 200, listed.text
    assert listed.json()["runs"][0]["prompt"] is None


async def test_the_order_is_the_one_things_happened_in(client, console_world):
    a = console_world["a"]
    thread_id = await _thread_with_runs(a, ["primero", "segundo", "tercero"])

    listed = await client.get(
        f"/console/companion/threads/{thread_id}/runs", headers=a["headers"]()
    )

    assert [r["prompt"] for r in listed.json()["runs"]] == ["primero", "segundo", "tercero"]
