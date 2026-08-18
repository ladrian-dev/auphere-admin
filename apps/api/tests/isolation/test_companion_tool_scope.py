"""Garantía C1 — una herramienta del Companion no cruza de partner.

Y su corolario, que es el que de verdad decide si el mecanismo de CO-02 es
seguro: **el sujeto de una llamada interna no se puede fabricar desde
fuera**. Las herramientas no llevan Bearer (el token de consola dura 60 s y
su ``jti`` se quema en la primera presentación); el sujeto viaja por una
variable de contexto que solo fija el ejecutor, dentro de la tarea del run
y después de que un principal real se haya verificado.

Si alguien pudiera encender esa variable con una cabecera, el aislamiento
entero de la consola se caería. Aquí se fija que no puede.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
import pytest_asyncio

from nexus_api.companion.tools import CompanionToolbelt
from nexus_api.core.console_auth import InProcessActor
from tests.conftest import add_console_member

pytestmark = [pytest.mark.isolation, pytest.mark.asyncio]


def _actor(world_side: dict[str, Any], user_id: str | None = None) -> InProcessActor:
    return InProcessActor(
        user_id=user_id or world_side["user_id"],
        partner_id=world_side["partner_id"],
        jti=f"companion:{uuid.uuid4()}",
    )


@pytest_asyncio.fixture
async def belt_for(client):
    """Un juego de herramientas contra la app real, con lifespan abierto."""
    from nexus_api.main import app

    made: list[CompanionToolbelt] = []

    async def _make(actor: InProcessActor, **kwargs: Any) -> CompanionToolbelt:
        belt = CompanionToolbelt(actor=actor, app=app, **kwargs)
        await belt.__aenter__()
        made.append(belt)
        return belt

    yield _make
    for belt in made:
        await belt.__aexit__(None, None, None)


# ── C1 · el cliente de otro partner no existe ──────────────────────────


async def test_a_client_ref_of_another_partner_is_the_same_404_as_a_missing_one(
    belt_for, console_world
):
    """Idéntico, byte a byte. Si el 404 del ref ajeno se distinguiera del
    del inexistente, el Companion sería un oráculo para averiguar la
    cartera de clientes de la competencia probando referencias."""
    belt = await belt_for(_actor(console_world["a"]))

    foreign = await belt.call("console.get_client", {"client_ref": console_world["b"]["ref"]})
    missing = await belt.call("console.get_client", {"client_ref": "no-existe-jamas"})

    assert foreign.ok is False and missing.ok is False
    assert foreign.error_code == "unknown_client"
    assert foreign.content == missing.content


async def test_the_foreign_client_never_appears_in_a_listing(belt_for, console_world):
    belt = await belt_for(_actor(console_world["a"]))
    listed = await belt.call("console.list_clients", {})
    assert listed.ok
    assert console_world["b"]["ref"] not in listed.content
    assert console_world["a"]["ref"] in listed.content


async def test_a_client_scoped_read_of_another_partner_is_refused(belt_for, console_world):
    """No solo la ficha: cualquier herramienta con ``{client_ref}`` en la
    ruta pasa por ``client_scope``, y ahí muere."""
    belt = await belt_for(_actor(console_world["a"]))
    for tool in (
        "console.get_agent",
        "console.get_policy",
        "console.list_tools",
        "console.list_channels",
        "console.conversation_stats",
    ):
        out = await belt.call(tool, {"client_ref": console_world["b"]["ref"]})
        assert out.ok is False, tool
        assert out.error_code == "unknown_client", tool


# ── el sujeto no se puede fabricar ─────────────────────────────────────


async def test_a_forged_header_does_not_grant_an_in_process_actor(client, console_world):
    """Una petición HTTP de verdad, con cabeceras inventadas que imitan al
    mecanismo interno, sigue necesitando su Bearer. El actor en proceso vive
    en una variable de contexto que uvicorn no puede heredar de nadie."""
    a = console_world["a"]
    refused = await client.get(
        "/console/me",
        headers={
            "X-Companion-Actor": a["user_id"],
            "X-In-Process-Actor": a["user_id"],
            "X-Companion-Partner": str(a["partner_id"]),
        },
    )
    assert refused.status_code == 401


async def test_the_actor_does_not_survive_its_block(client, console_world):
    """Se restaura siempre, también si lo de dentro lanza. Una variable de
    contexto que sobrevive a su bloque es exactamente el fallo que haría
    peligroso este mecanismo."""
    from nexus_api.core.console_auth import acting_as, current_in_process_actor

    assert current_in_process_actor() is None
    with pytest.raises(RuntimeError), acting_as(_actor(console_world["a"])):
        assert current_in_process_actor() is not None
        raise RuntimeError("boom")
    assert current_in_process_actor() is None


async def test_the_membership_is_re_read_on_every_internal_call(
    belt_for, console_world, db_session
):
    """El actor no es una credencial congelada: cada llamada relee la
    membresía. Un miembro expulsado a mitad de run deja de poder leer, sin
    esperar a que termine el turno."""
    from nexus_api.db.models import PartnerMembership

    a = console_world["a"]
    member = await add_console_member(db_session, partner_id=a["partner_id"], role="builder")
    belt = await belt_for(_actor(a, user_id=member["user_id"]))

    assert (await belt.call("console.whoami", {})).ok

    row = await db_session.get(PartnerMembership, member["membership_id"])
    row.status = "suspended"
    await db_session.commit()

    after = await belt.call("console.list_clients", {})
    assert after.ok is False
    # 403 del router: el principal ya no resuelve. Se traduce a algo que el
    # modelo pueda decir en voz alta sin filtrar el motivo.
    assert after.error_code == "forbidden"


async def test_a_role_without_the_permission_gets_the_routers_403(
    belt_for, console_world, db_session
):
    """El permiso lo sigue comprobando el router, con el rol de la FILA. El
    Companion no puede leer lo que su humano no podría leer: un ``billing``
    no ve el agente de un cliente."""
    a = console_world["a"]
    member = await add_console_member(db_session, partner_id=a["partner_id"], role="billing")
    belt = await belt_for(_actor(a, user_id=member["user_id"]))

    denied = await belt.call("console.get_agent", {"client_ref": a["ref"]})
    assert denied.ok is False
    assert denied.error_code == "forbidden"

    # Y lo que su rol SÍ permite sigue funcionando.
    allowed = await belt.call("console.get_usage", {})
    assert allowed.ok, allowed.content


# ── el tope de consultas es del motor ──────────────────────────────────


async def test_the_call_budget_is_hard(belt_for, console_world):
    belt = await belt_for(_actor(console_world["a"]), max_calls=2)
    assert (await belt.call("console.whoami", {})).ok
    assert (await belt.call("console.list_clients", {})).ok
    refused = await belt.call("console.get_onboarding", {})
    assert refused.ok is False
    assert refused.error_code == "budget_exhausted"


async def test_an_identical_read_is_refused_within_the_turn(belt_for, console_world):
    """Repetir la misma lectura no cambia el resultado y gasta ventana de
    contexto, que es el recurso escaso del turno."""
    belt = await belt_for(_actor(console_world["a"]))
    assert (await belt.call("console.list_clients", {"limit": 10})).ok
    again = await belt.call("console.list_clients", {"limit": 10})
    assert again.ok is False
    assert again.error_code == "already_read"


async def test_a_successful_read_produces_a_citation(belt_for, console_world):
    """La cita es lo que sostiene R1: un dato con su procedencia."""
    belt = await belt_for(_actor(console_world["a"]))
    out = await belt.call("console.get_usage", {"days": 7})
    assert out.ok, out.content
    assert out.citation is not None
    payload = out.citation.as_payload()
    assert set(payload) == {"citation_id", "claim", "source", "fetched_at"}
    assert payload["source"].startswith("/console/usage")
    assert belt.reads_done == 1


async def test_a_failed_read_produces_no_citation(belt_for, console_world):
    """Un 404 no respalda nada. Si contara como lectura, R1 dejaría pasar
    justo los turnos que tiene que marcar."""
    belt = await belt_for(_actor(console_world["a"]))
    out = await belt.call("console.get_client", {"client_ref": "no-existe"})
    assert out.ok is False
    assert out.citation is None
    assert belt.reads_done == 0


async def test_the_error_payload_tells_the_model_what_to_do(belt_for, console_world):
    """No un volcado de excepción: una frase accionable. Un volcado lo
    repite al usuario o le hace inventarse una alternativa."""
    belt = await belt_for(_actor(console_world["a"]))
    out = await belt.call("console.get_client", {"client_ref": "no-existe"})
    payload = json.loads(out.content)
    assert payload["error"] == "unknown_client"
    assert "console.list_clients" in payload["message"]
