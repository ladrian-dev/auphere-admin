"""Encontrar lo que se dijo — spec 013, Requisito 7.

⌘K solo navegaba entre secciones. Con meses de conversaciones, «Boreal» no
encontraba nada, y la memoria de la persona era el único índice.

**Sin índice nuevo.** R7 es P3 y se resuelve con lo que hay; si algún día
hiciera falta uno, es otra decisión y otro coste (data-model). Lo que esta
búsqueda **no** puede hacer, ni por descuido ni por optimizar, es cruzar la
frontera de la persona: por aquí sale texto de conversaciones.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from nexus_api.core.principal_context import apply_principal_to_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models.companion import CompanionMessage, CompanionRun, CompanionThread
from tests.conftest import add_console_member

pytestmark = pytest.mark.asyncio


async def _thread_saying(world, title: str, *frases: str) -> uuid.UUID:
    sm = get_sessionmaker()
    thread_id = uuid.uuid4()
    async with sm() as session, session.begin():
        await apply_principal_to_session(session, world["user_id"])
        session.add(
            CompanionThread(
                id=thread_id,
                principal_id=world["user_id"],
                partner_id=world["partner_id"],
                title=title,
                mode="build",
            )
        )
        await session.flush()
        base = datetime.now(UTC) - timedelta(hours=2)
        for i, frase in enumerate(frases):
            run_id = uuid.uuid4()
            session.add(
                CompanionRun(
                    id=run_id,
                    thread_id=thread_id,
                    principal_id=world["user_id"],
                    status="completed",
                    started_at=base + timedelta(minutes=i),
                )
            )
            await session.flush()
            session.add(
                CompanionMessage(
                    thread_id=thread_id, run_id=run_id, seq=i + 1, role="user", content=frase
                )
            )
    return thread_id


async def test_finds_the_conversation_a_term_appears_in(client, console_world):
    a = console_world["a"]
    boreal = await _thread_saying(a, "Clínica Boreal", "revisa la agenda de la clínica Boreal")
    await _thread_saying(a, "Otra cosa", "nada que ver")

    found = await client.get("/console/companion/search?q=Boreal", headers=a["headers"]())

    assert found.status_code == 200, found.text
    ids = [r["thread_id"] for r in found.json()["results"]]
    assert str(boreal) in ids
    assert len(ids) == 1, "solo la que lo dice"


async def test_it_never_returns_another_persons_text(client, db_session, console_world):
    """La frontera. Un colega **del mismo partner**, con su membresía activa."""
    a = console_world["a"]
    await _thread_saying(a, "Privada", "el precio que le cerré a Boreal")

    colega = await add_console_member(db_session, partner_id=a["partner_id"], role="owner")

    found = await client.get("/console/companion/search?q=Boreal", headers=colega["headers"]())

    assert found.status_code == 200, found.text
    assert found.json()["results"] == []
    assert "precio" not in found.text


async def test_no_matches_is_not_an_error(client, console_world):
    """R7.3 — «no hay» tiene que poder distinguirse de «todavía cargando»."""
    a = console_world["a"]
    await _thread_saying(a, "Algo", "hola")

    found = await client.get("/console/companion/search?q=zzzznoexiste", headers=a["headers"]())

    assert found.status_code == 200
    assert found.json()["results"] == []


async def test_it_says_where_the_term_appeared(client, console_world):
    """Un resultado sin contexto obliga a abrir la conversación para saber si
    era la que se buscaba."""
    a = console_world["a"]
    await _thread_saying(a, "Clínica Boreal", "revisa la agenda de la clínica Boreal el martes")

    found = await client.get("/console/companion/search?q=agenda", headers=a["headers"]())

    fila = found.json()["results"][0]
    assert fila["title"] == "Clínica Boreal"
    assert "agenda" in fila["excerpt"].lower()


async def test_an_empty_query_asks_for_something_instead_of_returning_everything(
    client, console_world
):
    a = console_world["a"]
    await _thread_saying(a, "Algo", "hola")

    found = await client.get("/console/companion/search?q=", headers=a["headers"]())

    # Devolver el hilo entero ante una búsqueda vacía sería confundir «no has
    # escrito nada» con «quiero verlo todo».
    assert found.status_code in (200, 422)
    if found.status_code == 200:
        assert found.json()["results"] == []
