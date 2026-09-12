"""Requisitos 8.1 y 9.1 — el consumo de Cuenta: el mismo número, por teammate.

`GET /console/teammates/usage` no es un contador nuevo (R9.1): su `budget` es
**el mismo objeto** que `/console/companion/budget`, y el desglose por teammate
es una lectura de `companion.runs`, la misma tabla que ya alimenta el medidor.

Lo que aquí se fija con más cuidado es el reparto: el roster es del **partner**,
así que lo que cada teammate consumió incluye lo que gastó con él cualquier
persona del equipo — igual que el tope, que es del partner. La RLS de los runs
cuelga de la persona, así que sumar «lo de todos» exige recorrer las membresías,
y si eso se hiciera mal el número de Cuenta no cuadraría con el del medidor.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from nexus_api.db.models import Teammate
from nexus_api.db.models.companion import CompanionRun, CompanionThread
from tests.conftest import add_console_member

pytestmark = pytest.mark.asyncio


def _teammate(partner_id: uuid.UUID, name: str) -> Teammate:
    return Teammate(
        id=uuid.uuid4(),
        partner_id=partner_id,
        name=name,
        job="Desarrollo",
        model="openai/gpt-5.6-sol",
        tool_names=["console.whoami"],
        permissions={
            "read": True,
            "write": False,
            "spend": False,
            "publish": False,
            "contact": False,
        },
        local_exec=False,
        created_by="seed",
    )


async def _run(
    db_session,
    world,
    *,
    principal_id: str,
    teammate_id: uuid.UUID | None,
    input_tokens: int,
    output_tokens: int,
    started_at: datetime | None = None,
) -> CompanionRun:
    """Un hilo con un run terminado, como los deja la API al cerrar el stream."""
    when = started_at or datetime.now(UTC)
    thread = CompanionThread(
        id=uuid.uuid4(),
        principal_id=principal_id,
        partner_id=world["partner_id"],
        teammate_id=teammate_id,
        title="hilo",
        created_at=when,
        updated_at=when,
    )
    db_session.add(thread)
    await db_session.flush()
    run = CompanionRun(
        id=uuid.uuid4(),
        thread_id=thread.id,
        principal_id=principal_id,
        teammate_id=teammate_id,
        status="completed",
        started_at=when,
        ended_at=when,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    db_session.add(run)
    await db_session.commit()
    return run


async def _usage(client, world):
    return await client.get("/console/teammates/usage", headers=world["headers"]())


async def test_the_budget_is_the_same_object_as_the_companions(client, db_session, console_world):
    """R9.1 — «el mismo medidor» comprobado byte a byte, no de palabra."""
    a = console_world["a"]
    sofia = _teammate(a["partner_id"], "Sofía")
    db_session.add(sofia)
    await db_session.flush()
    await _run(
        db_session,
        a,
        principal_id=a["user_id"],
        teammate_id=sofia.id,
        input_tokens=700,
        output_tokens=300,
    )

    usage = await _usage(client, a)
    companion = await client.get("/console/companion/budget", headers=a["headers"]())

    assert usage.status_code == 200, usage.text
    assert companion.status_code == 200, companion.text
    assert usage.json()["budget"] == companion.json()


async def test_what_each_teammate_spent_includes_what_the_whole_team_spent_with_it(
    client, db_session, console_world
):
    """El roster es del partner: el consumo de un teammate no es «el mío con él»."""
    a = console_world["a"]
    other = await add_console_member(db_session, partner_id=a["partner_id"], role="builder")
    sofia = _teammate(a["partner_id"], "Sofía")
    db_session.add(sofia)
    await db_session.flush()
    await _run(
        db_session,
        a,
        principal_id=a["user_id"],
        teammate_id=sofia.id,
        input_tokens=100,
        output_tokens=50,
    )
    await _run(
        db_session,
        a,
        principal_id=other["user_id"],
        teammate_id=sofia.id,
        input_tokens=400,
        output_tokens=200,
    )

    response = await _usage(client, a)

    assert response.status_code == 200, response.text
    rows = {row["teammate_id"]: row for row in response.json()["by_teammate"]}
    assert rows[str(sofia.id)]["input_tokens"] == 500
    assert rows[str(sofia.id)]["output_tokens"] == 250
    assert rows[str(sofia.id)]["runs"] == 2
    assert rows[str(sofia.id)]["name"] == "Sofía"


async def test_the_breakdown_and_the_meter_tell_the_same_story(client, db_session, console_world):
    """El desglose reparte lo atribuible; el medidor es el libro.

    **Esto cambió con la spec 004 (R4.1/R4.4) y el cambio es el punto.** Antes
    el medidor era la suma de ``companion.runs``, así que desglose y medidor
    cerraban por construcción — y por eso mismo el medidor no veía el gasto de
    los clientes ni el de la ejecución en la máquina, que sí vacían el libro.
    Un partner podía leer «20 % usado» y recibir un ``wallet_empty``.

    Ahora el medidor sale del libro y el desglose sigue saliendo de los runs, de
    modo que **el medidor puede ser mayor**. La diferencia no se oculta ni se
    reparte entre los teammates que sí aparecen: se nombra
    (``attribution_gap``), y la pantalla Cuenta ya tiene la línea para decirla.
    """
    a = console_world["a"]
    sofia, nilo = _teammate(a["partner_id"], "Sofía"), _teammate(a["partner_id"], "Nilo")
    db_session.add_all([sofia, nilo])
    await db_session.flush()
    await _run(
        db_session,
        a,
        principal_id=a["user_id"],
        teammate_id=sofia.id,
        input_tokens=100,
        output_tokens=50,
    )
    await _run(
        db_session,
        a,
        principal_id=a["user_id"],
        teammate_id=nilo.id,
        input_tokens=200,
        output_tokens=100,
    )
    # Y un hilo del Companion de la consola, sin teammate: cuenta en el medidor
    # y **no** aparece en el desglose.
    await _run(
        db_session,
        a,
        principal_id=a["user_id"],
        teammate_id=None,
        input_tokens=40,
        output_tokens=10,
    )

    body = (await _usage(client, a)).json()

    by_teammate = sum(r["input_tokens"] + r["output_tokens"] for r in body["by_teammate"])
    assert by_teammate == 450, "el desglose reparte solo lo atribuible a un teammate"
    # El hilo sin teammate (50) no aparece en el desglose, y eso es correcto.
    assert [r["teammate_id"] for r in body["by_teammate"]].count(None) == 0

    # El medidor es el libro. Estos runs se sembraron a mano, sin pasar por
    # ``debit_wallet``, así que el libro no ha bajado — y el medidor lo dice.
    # Comprobar aquí que «cierran» sería volver a atar el total a los runs.
    from nexus_api.api.console.companion import attribution_gap

    assert body["budget"]["used"] == 0
    assert attribution_gap(total=body["budget"]["used"], attributed=by_teammate) == 0


async def test_a_teammate_with_nothing_this_month_is_not_in_the_breakdown(
    client, db_session, console_world
):
    """Una fila a cero por cada teammate del roster sería ruido: el desglose
    dice quién gastó, y la pantalla ya tiene el roster para el resto."""
    a = console_world["a"]
    quieto = _teammate(a["partner_id"], "Quieto")
    db_session.add(quieto)
    await db_session.commit()

    body = (await _usage(client, a)).json()

    assert body["by_teammate"] == []


async def test_last_months_runs_do_not_count_in_the_breakdown(client, db_session, console_world):
    a = console_world["a"]
    sofia = _teammate(a["partner_id"], "Sofía")
    db_session.add(sofia)
    await db_session.flush()
    old = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(
        days=2
    )
    await _run(
        db_session,
        a,
        principal_id=a["user_id"],
        teammate_id=sofia.id,
        input_tokens=9_000,
        output_tokens=1_000,
        started_at=old,
    )
    await _run(
        db_session,
        a,
        principal_id=a["user_id"],
        teammate_id=sofia.id,
        input_tokens=10,
        output_tokens=5,
    )

    body = (await _usage(client, a)).json()

    # El medidor sale del libro y estos runs se sembraron a mano; lo que este
    # test comprueba es el DESGLOSE: el del mes pasado no aparece, el de este
    # sí (spec 004, R4.2 — la suma de runs es atribución, no total).
    assert body["by_teammate"][0]["input_tokens"] == 10
    assert body["by_teammate"][0]["output_tokens"] == 5


async def test_another_partners_spending_is_not_here(client, db_session, console_world):
    a, b = console_world["a"], console_world["b"]
    theirs = _teammate(b["partner_id"], "Ajeno")
    db_session.add(theirs)
    await db_session.flush()
    await _run(
        db_session,
        b,
        principal_id=b["user_id"],
        teammate_id=theirs.id,
        input_tokens=5_000,
        output_tokens=5_000,
    )

    body = (await _usage(client, a)).json()

    assert body["by_teammate"] == []
    assert body["budget"]["used"] == 0


async def test_without_the_permission_there_is_no_usage(client, db_session, console_world):
    a = console_world["a"]
    analyst = await add_console_member(db_session, partner_id=a["partner_id"], role="analyst")
    assert (await _usage(client, analyst)).status_code == 403
