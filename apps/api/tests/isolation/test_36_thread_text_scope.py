"""Por el resumen de un run viaja texto, y el texto tiene dueño — spec 013.

**Esta no es ninguna de las ocho garantías**, y decirlo importa: la 013 no toca
ninguna. Lo que hace es cambiar de naturaleza una respuesta que ya existía.
Hasta ahora `GET …/threads/{id}/runs` devolvía cuatro campos de metadatos —id,
estado y dos fechas—; desde la 013 devuelve **lo que una persona escribió**.

Una frontera por la que antes pasaban identificadores y ahora pasa prosa merece
su propio test, aunque el mecanismo que la sostiene —la RLS por `principal_id`
de la migración 0090— no haya cambiado ni una línea. El riesgo no es que la
política falle: es que alguien añada un camino nuevo a los mismos datos y nadie
se acuerde de que ahora llevan texto dentro.

El 404 es **opaco a propósito**: un hilo de otra persona no se distingue de uno
que no existe. Decir «prohibido» ya confirmaría que existe.

En rojo bloquea el merge.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from nexus_api.core.principal_context import apply_principal_to_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models.companion import CompanionMessage, CompanionRun, CompanionThread
from tests.conftest import add_console_member

pytestmark = [pytest.mark.isolation, pytest.mark.asyncio]

SECRETO = "el precio que le cerré a la clínica Boreal"


async def _thread_of(world, text: str) -> uuid.UUID:
    """Un hilo de **esta** persona, con una frase que nadie más debería leer."""
    sm = get_sessionmaker()
    thread_id, run_id = uuid.uuid4(), uuid.uuid4()
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
        session.add(
            CompanionRun(
                id=run_id,
                thread_id=thread_id,
                principal_id=world["user_id"],
                status="completed",
                started_at=datetime.now(UTC) - timedelta(minutes=5),
            )
        )
        await session.flush()
        session.add(
            CompanionMessage(thread_id=thread_id, run_id=run_id, seq=1, role="user", content=text)
        )
    return thread_id


async def test_the_owner_reads_their_own_text(client, console_world):
    """La otra mitad del test: sin esto, un 404 para todos también pasaría."""
    a = console_world["a"]
    thread_id = await _thread_of(a, SECRETO)

    listed = await client.get(
        f"/console/companion/threads/{thread_id}/runs", headers=a["headers"]()
    )

    assert listed.status_code == 200, listed.text
    assert listed.json()["runs"][0]["prompt"] == SECRETO


async def test_another_person_of_the_same_partner_gets_nothing(client, db_session, console_world):
    """El caso que importa: **mismo partner**, otra persona.

    Aquí la RLS no es por tenant —los dos son del mismo— sino por persona. Es
    el eje que la migración 0090 defiende, y por el que ahora viaja prosa.
    """
    a = console_world["a"]
    thread_id = await _thread_of(a, SECRETO)

    # Un colega **de verdad**: con su membresía activa en el mismo partner.
    # Sin ella el rechazo vendría de la autenticación (403) y este test no
    # probaría la RLS por persona, que es lo que aquí se defiende.
    colega = await add_console_member(db_session, partner_id=a["partner_id"], role="owner")

    listed = await client.get(
        f"/console/companion/threads/{thread_id}/runs", headers=colega["headers"]()
    )

    assert listed.status_code == 404, (
        f"el hilo de otra persona tiene que no existir: {listed.status_code}"
    )
    assert SECRETO not in listed.text


async def test_another_partner_gets_the_opaque_404(client, console_world):
    """Y desde otro partner, lo mismo y por partida doble."""
    a, b = console_world["a"], console_world["b"]
    thread_id = await _thread_of(a, SECRETO)

    listed = await client.get(
        f"/console/companion/threads/{thread_id}/runs", headers=b["headers"]()
    )

    assert listed.status_code == 404, (
        f"un hilo ajeno tiene que no existir, no estar prohibido: {listed.status_code}"
    )
    assert SECRETO not in listed.text
