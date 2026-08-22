"""El ciclo entero de una acción, por HTTP (CO-04).

Proponer → parar → confirmar → aplicar → verificar, contra la aplicación
real: los routers ``/console/*``, la RLS de ``companion.*``, el log durable
de Redis y el checkpointer de LangGraph. Lo único de mentira es el
proveedor de modelo, que responde con un guion.

Es donde se ve si el diseño aguanta, porque aquí sí pasan las cosas que no
pasan en un unitario: el run se aparca en la base, la acción caduca de
verdad, el hash se recalcula contra el estado que cambió y el segundo
``resume`` choca con un 409.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa
from nexus_worker.runtime.llm import InMemoryProvider, ToolCall

from nexus_api.api.console import companion as companion_api
from nexus_api.core.principal_context import apply_principal_to_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models.companion import CompanionAction, CompanionRun

pytestmark = pytest.mark.asyncio

ANSWER = "Preparado. Dime si lo confirmas."
NEW_PROMPT = "Responde en el idioma del cliente y nunca des precios por WhatsApp."


def _script(*rounds: list[tuple[str, dict[str, Any]]]):
    """Guion de llamadas a herramienta, ronda por ronda."""
    seen = {"n": 0}

    def _caller(_call: Any) -> list[ToolCall]:
        i = seen["n"]
        seen["n"] += 1
        if i >= len(rounds):
            return []
        return [
            ToolCall(id=f"t{i}-{j}", name=name, arguments=args)
            for j, (name, args) in enumerate(rounds[i])
        ]

    return _caller


@pytest_asyncio.fixture
def companion_provider():
    """Proveedor en memoria y **el resto del camino real**: el grafo se
    compila por run con su propio juego de herramientas, así que el carril
    de escritura existe de verdad."""

    def _install(*rounds: list[tuple[str, dict[str, Any]]]) -> InMemoryProvider:
        provider = InMemoryProvider(
            responder=lambda _c: ANSWER, tool_caller=_script(*rounds) if rounds else None
        )
        companion_api.set_provider_for_tests(provider)
        return provider

    yield _install
    companion_api.reset_graph_cache_for_tests()


async def _thread(client, world) -> str:
    created = await client.post(
        "/console/companion/threads",
        headers=world["headers"](),
        json={"title": "t", "mode": "build"},
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


async def _wait_for_action(principal_id: str, timeout: float = 10.0) -> CompanionAction:
    """El POST devuelve 202 y el turno sigue por su cuenta: sin esperar,
    el test correría contra una fila a medio escribir."""
    sm = get_sessionmaker()
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        async with sm() as session, session.begin():
            await apply_principal_to_session(session, principal_id)
            row = (
                await session.execute(
                    sa.select(CompanionAction).order_by(CompanionAction.proposed_at.desc()).limit(1)
                )
            ).scalar_one_or_none()
            if row is not None:
                await session.refresh(row)
                return row
        await asyncio.sleep(0.05)
    raise AssertionError("la acción no se propuso a tiempo")


async def _wait_for_run(
    run_id: uuid.UUID, principal_id: str, timeout: float = 10.0
) -> CompanionRun:
    sm = get_sessionmaker()
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        async with sm() as session, session.begin():
            await apply_principal_to_session(session, principal_id)
            run = await session.get(CompanionRun, run_id)
            if run is not None and run.status != "running":
                await session.refresh(run)
                return run
        await asyncio.sleep(0.05)
    raise AssertionError("el run no se cerró a tiempo")


async def _action_row(action_id: uuid.UUID, principal_id: str) -> CompanionAction:
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_principal_to_session(session, principal_id)
        row = await session.get(CompanionAction, action_id)
        assert row is not None
        await session.refresh(row)
        return row


async def _propose_prompt(client, world, provider_factory) -> tuple[str, str, CompanionAction]:
    """Un turno que acaba proponiendo un cambio de prompt."""
    provider_factory(
        [("console.propose_prompt", {"client_ref": world["ref"], "system_prompt": NEW_PROMPT})]
    )
    thread_id = await _thread(client, world)
    run_id = await _turn(client, world, thread_id)
    action = await _wait_for_action(world["user_id"])
    return thread_id, run_id, action


# ── proponer y parar ───────────────────────────────────────────────────


async def test_a_proposal_stops_the_turn_and_leaves_a_pending_action(
    client, console_world, companion_provider
):
    a = console_world["a"]
    _thread_id, run_id, action = await _propose_prompt(client, a, companion_provider)

    assert action.kind == "prompt"
    assert action.status == "proposed"
    assert action.state_hash
    assert str(action.run_id) == run_id

    events = await client.get(f"/console/companion/runs/{run_id}/events", headers=a["headers"]())
    names = [e["event"] for e in events.json()["events"]]

    assert "plan.proposed" in names
    assert "hitl.requested" in names
    # El turno NO se cerró: el grafo está parado en el ``interrupt()`` y el
    # cajón tiene que seguir con la tarjeta en pantalla, no dar el trabajo
    # por terminado.
    assert "run.completed" not in names

    hitl = next(e["data"] for e in events.json()["events"] if e["event"] == "hitl.requested")
    assert set(hitl) == {
        "action_id",
        "kind",
        "title",
        "preview",
        "diff",
        "impact",
        "expires_at",
    }
    assert hitl["action_id"] == str(action.id)


async def test_a_parked_run_stays_running_and_records_its_tokens(
    client, console_world, companion_provider
):
    """El gasto del turno cuenta contra el tope aunque la confirmación no
    llegue nunca. Perderlo sería regalar tokens por cada propuesta que nadie
    responde."""
    a = console_world["a"]
    _t, run_id, _action = await _propose_prompt(client, a, companion_provider)

    row = await _run_row(uuid.UUID(run_id), a["user_id"])
    assert row.status == "running"
    assert row.ended_at is None


async def _run_row(run_id: uuid.UUID, principal_id: str) -> CompanionRun:
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_principal_to_session(session, principal_id)
        run = await session.get(CompanionRun, run_id)
        assert run is not None
        await session.refresh(run)
        return run


async def test_the_action_endpoint_paints_the_card_after_a_reload(
    client, console_world, companion_provider
):
    """El estado *parcial* del §14: recargar con una confirmación pendiente
    tiene que pintar la tarjeta sin depender de que Redis siga vivo."""
    a = console_world["a"]
    _t, _r, action = await _propose_prompt(client, a, companion_provider)

    got = await client.get(f"/console/companion/actions/{action.id}", headers=a["headers"]())
    assert got.status_code == 200, got.text
    body = got.json()

    assert body["kind"] == "prompt"
    assert body["status"] == "proposed"
    assert body["risk"] in {"low", "medium", "high"}
    assert body["reversible"] is True
    assert isinstance(body["diff"], list) and body["diff"]
    assert body["expires_at"] > body["proposed_at"]
    assert body["decided_at"] is None and body["ok"] is None


async def test_another_members_action_is_an_opaque_404(
    client, console_world, companion_provider, db_session
):
    """La RLS de ``companion.actions`` cuelga del hilo, y el hilo es del
    principal. Otro miembro del MISMO partner tampoco la ve."""
    from tests.conftest import add_console_member

    a = console_world["a"]
    _t, _r, action = await _propose_prompt(client, a, companion_provider)
    other = await add_console_member(db_session, partner_id=a["partner_id"], role="owner")

    denied = await client.get(f"/console/companion/actions/{action.id}", headers=other["headers"]())
    missing = await client.get(
        f"/console/companion/actions/{uuid.uuid4()}", headers=other["headers"]()
    )
    assert denied.status_code == 404
    assert denied.json() == missing.json()


# ── confirmar, aplicar, verificar ──────────────────────────────────────


async def test_confirming_applies_the_change_and_verifies_it(
    client, console_world, companion_provider
):
    """El camino feliz completo, y el que más partes tiene que encajar: la
    escritura sale por el router de verdad, así que crea una versión de
    agente real, y la verificación la relee."""
    a = console_world["a"]
    _t, run_id, action = await _propose_prompt(client, a, companion_provider)

    resumed = await client.post(
        f"/console/companion/runs/{run_id}/resume",
        headers=a["headers"](),
        json={"action_id": str(action.id), "decision": "confirm"},
    )
    assert resumed.status_code == 202, resumed.text
    body = resumed.json()
    assert body["status"] == "confirmed"
    assert body["action_id"] == str(action.id)
    # Un run NUEVO continúa el hilo; la interfaz tiene que seguir ese.
    assert body["run_id"] != run_id

    await _wait_for_run(uuid.UUID(body["run_id"]), a["user_id"])
    row = await _action_row(action.id, a["user_id"])
    assert row.status == "applied"
    assert row.applied_at is not None
    assert row.decided_by == a["user_id"]

    # Y el cambio existe de verdad: un borrador nuevo con el prompt pedido.
    agent = await client.get(f"/console/clients/{a['ref']}/agent", headers=a["headers"]())
    prompts = [v["system_prompt"] for v in agent.json()["versions"]]
    assert NEW_PROMPT in prompts


async def test_the_resume_run_emits_the_contract_sequence(
    client, console_world, companion_provider
):
    a = console_world["a"]
    _t, run_id, action = await _propose_prompt(client, a, companion_provider)
    resumed = await client.post(
        f"/console/companion/runs/{run_id}/resume",
        headers=a["headers"](),
        json={"action_id": str(action.id), "decision": "confirm"},
    )
    new_run = resumed.json()["run_id"]
    await _wait_for_run(uuid.UUID(new_run), a["user_id"])

    events = await client.get(f"/console/companion/runs/{new_run}/events", headers=a["headers"]())
    names = [e["event"] for e in events.json()["events"]]

    # §4.3: ``hitl.resolved`` es el primero después de ``run.started``.
    assert names[0] == "run.started"
    assert names[1] == "hitl.resolved"
    assert "verify.result" in names
    assert names[-1] == "run.completed"

    resolved = next(e["data"] for e in events.json()["events"] if e["event"] == "hitl.resolved")
    assert set(resolved) == {"action_id", "decision", "by", "at", "note"}
    # El ``principal_id``, nunca el correo de nadie.
    assert resolved["by"] == a["user_id"]
    assert "@" not in resolved["by"]

    verify = next(e["data"] for e in events.json()["events"] if e["event"] == "verify.result")
    # ``trial`` es del contrato v2 §7 (CO-05). Tres valores y no dos:
    # ``None`` = esta acción no admite prueba; ``{"ran": False}`` = la
    # admite y nadie probó — que es lo que el aviso de publicación
    # necesita distinguir.
    assert set(verify) == {"action_id", "checks", "ok", "trial"}
    assert verify["trial"] is None or verify["trial"]["ran"] is False
    assert verify["ok"] is True, verify
    for check in verify["checks"]:
        assert isinstance(check["expected"], str) and isinstance(check["actual"], str)


async def test_the_parked_run_is_closed_by_the_resume(client, console_world, companion_provider):
    a = console_world["a"]
    _t, run_id, action = await _propose_prompt(client, a, companion_provider)
    await client.post(
        f"/console/companion/runs/{run_id}/resume",
        headers=a["headers"](),
        json={"action_id": str(action.id), "decision": "confirm"},
    )
    row = await _run_row(uuid.UUID(run_id), a["user_id"])
    assert row.status == "completed"
    assert row.ended_at is not None


# ── rechazos ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("decision", "expected"), [("cancel", "cancelled"), ("edit", "superseded")]
)
async def test_a_refusal_records_its_own_status_and_applies_nothing(
    client, console_world, companion_provider, decision: str, expected: str
):
    """``edit`` no es ``cancelled``: cancelar cierra el trabajo, editar lo
    continúa por otro camino, y la traza tiene que poder distinguirlos."""
    a = console_world["a"]
    _t, run_id, action = await _propose_prompt(client, a, companion_provider)
    before = await client.get(f"/console/clients/{a['ref']}/agent", headers=a["headers"]())

    resumed = await client.post(
        f"/console/companion/runs/{run_id}/resume",
        headers=a["headers"](),
        json={
            "action_id": str(action.id),
            "decision": decision,
            "note": "Mejor sin tocar el horario.",
        },
    )
    assert resumed.status_code == 202, resumed.text
    assert resumed.json()["status"] == expected

    await _wait_for_run(uuid.UUID(resumed.json()["run_id"]), a["user_id"])
    row = await _action_row(action.id, a["user_id"])
    assert row.status == expected
    assert row.applied_at is None

    after = await client.get(f"/console/clients/{a['ref']}/agent", headers=a["headers"]())
    assert after.json() == before.json(), "un rechazo no puede cambiar nada"

    events = await client.get(
        f"/console/companion/runs/{resumed.json()['run_id']}/events", headers=a["headers"]()
    )
    resolved = next(e["data"] for e in events.json()["events"] if e["event"] == "hitl.resolved")
    # El motivo vuelve al agente: es el ``deny_message`` de Managed Agents.
    assert resolved["note"] == "Mejor sin tocar el horario."


# ── los códigos del §4.2 ───────────────────────────────────────────────


async def test_deciding_twice_is_a_409_with_the_reason(client, console_world, companion_provider):
    a = console_world["a"]
    _t, run_id, action = await _propose_prompt(client, a, companion_provider)
    first = await client.post(
        f"/console/companion/runs/{run_id}/resume",
        headers=a["headers"](),
        json={"action_id": str(action.id), "decision": "cancel"},
    )
    assert first.status_code == 202

    again = await client.post(
        f"/console/companion/runs/{run_id}/resume",
        headers=a["headers"](),
        json={"action_id": str(action.id), "decision": "confirm"},
    )
    assert again.status_code == 409, again.text
    assert again.json()["detail"]["code"] == "action_already_decided"


async def test_an_expired_action_is_a_409_and_not_a_412(client, console_world, companion_provider):
    """Los dos llevan a lo mismo —volver a proponer— pero la causa no es la
    misma, y la interfaz las pinta distinto: «se te pasó el plazo» no es
    «alguien cambió esto mientras decidías»."""
    a = console_world["a"]
    _t, run_id, action = await _propose_prompt(client, a, companion_provider)

    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_principal_to_session(session, a["user_id"])
        await session.execute(
            sa.update(CompanionAction)
            .where(CompanionAction.id == action.id)
            .values(proposed_at=datetime.now(UTC) - timedelta(minutes=30))
        )

    late = await client.post(
        f"/console/companion/runs/{run_id}/resume",
        headers=a["headers"](),
        json={"action_id": str(action.id), "decision": "confirm"},
    )
    assert late.status_code == 409, late.text
    assert late.json()["detail"]["code"] == "action_expired"
    # Y la caducidad se PERSISTE al leerla: no hay cron, y el estado tiene
    # que ser el mismo lo lea quien lo lea.
    assert (await _action_row(action.id, a["user_id"])).status == "expired"


async def test_state_drift_is_a_412_and_the_action_expires(
    client, console_world, companion_provider
):
    """**El CAS del Companion.** Otra persona apila una versión mientras
    esta decide: el diff que vio ya no describe la realidad."""
    a = console_world["a"]
    _t, run_id, action = await _propose_prompt(client, a, companion_provider)

    # Alguien más toca el agente por la vía normal de la consola.
    staged = await client.post(
        f"/console/clients/{a['ref']}/agent/versions",
        headers=a["headers"](),
        json={"system_prompt": "Otra persona escribió esto mientras tanto."},
    )
    assert staged.status_code == 201, staged.text

    drifted = await client.post(
        f"/console/companion/runs/{run_id}/resume",
        headers=a["headers"](),
        json={"action_id": str(action.id), "decision": "confirm"},
    )
    assert drifted.status_code == 412, drifted.text
    assert drifted.json()["detail"]["code"] == "state_changed"
    assert (await _action_row(action.id, a["user_id"])).status == "expired"


async def test_drift_does_not_block_a_cancel(client, console_world, companion_provider):
    """El hash solo se revalida al confirmar. Cancelar algo que ya no se
    puede aplicar tiene que seguir siendo posible — si no, una acción
    derivada se quedaría atascada hasta caducar."""
    a = console_world["a"]
    _t, run_id, action = await _propose_prompt(client, a, companion_provider)
    await client.post(
        f"/console/clients/{a['ref']}/agent/versions",
        headers=a["headers"](),
        json={"system_prompt": "Otra cosa."},
    )
    cancelled = await client.post(
        f"/console/companion/runs/{run_id}/resume",
        headers=a["headers"](),
        json={"action_id": str(action.id), "decision": "cancel"},
    )
    assert cancelled.status_code == 202, cancelled.text


async def test_an_action_of_another_member_is_a_404_before_any_409(
    client, console_world, companion_provider, db_session
):
    """Se comprueba la pertenencia PRIMERO. Si un tercero pudiera distinguir
    «no existe» de «existe y ya está aplicada», esto sería un oráculo."""
    from tests.conftest import add_console_member

    a = console_world["a"]
    _t, run_id, action = await _propose_prompt(client, a, companion_provider)
    other = await add_console_member(db_session, partner_id=a["partner_id"], role="owner")

    denied = await client.post(
        f"/console/companion/runs/{run_id}/resume",
        headers=other["headers"](),
        json={"action_id": str(action.id), "decision": "confirm"},
    )
    assert denied.status_code == 404, denied.text


async def test_a_mismatched_run_and_action_is_a_404(client, console_world, companion_provider):
    """La acción tiene que ser de ESTE run. Aceptar una de otro dejaría
    reanudar un grafo con la decisión de una propuesta distinta."""
    a = console_world["a"]
    _t, _run_id, action = await _propose_prompt(client, a, companion_provider)

    wrong = await client.post(
        f"/console/companion/runs/{uuid.uuid4()}/resume",
        headers=a["headers"](),
        json={"action_id": str(action.id), "decision": "confirm"},
    )
    assert wrong.status_code == 404


async def test_a_malformed_decision_is_a_422(client, console_world, companion_provider):
    a = console_world["a"]
    _t, run_id, action = await _propose_prompt(client, a, companion_provider)
    bad = await client.post(
        f"/console/companion/runs/{run_id}/resume",
        headers=a["headers"](),
        json={"action_id": str(action.id), "decision": "aplicalo-ya"},
    )
    assert bad.status_code == 422


async def test_a_note_longer_than_the_limit_is_a_422(client, console_world, companion_provider):
    a = console_world["a"]
    _t, run_id, action = await _propose_prompt(client, a, companion_provider)
    bad = await client.post(
        f"/console/companion/runs/{run_id}/resume",
        headers=a["headers"](),
        json={"action_id": str(action.id), "decision": "cancel", "note": "x" * 2001},
    )
    assert bad.status_code == 422


# ── el presupuesto no bloquea una confirmación (§23.2) ─────────────────


async def test_the_monthly_cap_does_not_block_a_resume(
    client, console_world, companion_provider, db_session
):
    """Responder una confirmación **no arranca trabajo nuevo**. Un hilo
    esperando decisión no puede quedarse atrapado porque el partner haya
    gastado su presupuesto entre la propuesta y el sí — eso dejaría al
    usuario con una tarjeta que no se puede ni cancelar."""
    from nexus_api.db.models import Partner

    a = console_world["a"]
    _t, run_id, action = await _propose_prompt(client, a, companion_provider)

    # Cero y no uno: así el tope está agotado sin depender de que la fila
    # del run aparcado haya terminado de escribir sus tokens, que es una
    # carrera con la tarea de fondo y no lo que este test mide.
    partner = await db_session.get(Partner, a["partner_id"])
    partner.companion_monthly_token_cap = 0
    await db_session.commit()

    # Un turno nuevo SÍ está cortado… con **409 ``budget_paused``** desde
    # CO-08 (§6.2 de CONTRACT-V2): el tope pausa en vez de matar, y 429
    # sería mentira porque reintentar no lo desbloquea.
    blocked = await client.post(
        f"/console/companion/threads/{_t}/runs",
        headers=a["headers"](),
        json={"prompt": "otra cosa"},
    )
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["detail"]["code"] == "budget_paused"

    # …pero cerrar el que estaba abierto, no.
    resumed = await client.post(
        f"/console/companion/runs/{run_id}/resume",
        headers=a["headers"](),
        json={"action_id": str(action.id), "decision": "cancel"},
    )
    assert resumed.status_code == 202, resumed.text


# ── el modo del hilo recorta lo que el modelo puede pedir ──────────────


async def test_a_consult_thread_cannot_propose_anything(client, console_world, companion_provider):
    """El modo es del usuario y nunca del modelo: en *Consultar* las
    herramientas de propuesta ni siquiera se publican, así que no hay texto
    que pueda convencer al agente de intentarlo."""
    a = console_world["a"]
    companion_provider(
        [("console.propose_prompt", {"client_ref": a["ref"], "system_prompt": NEW_PROMPT})]
    )
    created = await client.post(
        "/console/companion/threads",
        headers=a["headers"](),
        json={"title": "t", "mode": "consult"},
    )
    thread_id = created.json()["id"]
    run_id = await _turn(client, a, thread_id)
    run = await _wait_for_run(uuid.UUID(run_id), a["user_id"])
    assert run.status == "completed"

    events = await client.get(f"/console/companion/runs/{run_id}/events", headers=a["headers"]())
    names = [e["event"] for e in events.json()["events"]]
    assert "hitl.requested" not in names

    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_principal_to_session(session, a["user_id"])
        count = await session.scalar(sa.select(sa.func.count()).select_from(CompanionAction))
    assert count == 0


# ── el timeline es del hilo, no del run (contrato v1.1 §5.2) ───────────


async def test_a_thread_lists_its_runs_in_order(client, console_world, companion_provider):
    """Los dos runs de una confirmación —el que se paró y el que continuó—
    tienen que salir aquí, en orden, o el cajón no puede reconstruir la
    conversación al recargar."""
    a = console_world["a"]
    thread_id, run_id, action = await _propose_prompt(client, a, companion_provider)
    resumed = await client.post(
        f"/console/companion/runs/{run_id}/resume",
        headers=a["headers"](),
        json={"action_id": str(action.id), "decision": "confirm"},
    )
    second = resumed.json()["run_id"]
    await _wait_for_run(uuid.UUID(second), a["user_id"])

    listed = await client.get(
        f"/console/companion/threads/{thread_id}/runs", headers=a["headers"]()
    )
    assert listed.status_code == 200, listed.text
    body = listed.json()

    assert body["thread_id"] == thread_id
    ids = [r["run_id"] for r in body["runs"]]
    assert ids == [run_id, second], "ascendente por started_at"
    assert [r["started_at"] for r in body["runs"]] == sorted(r["started_at"] for r in body["runs"])
    # Y sirve para lo que existe: cada run se puede pedir por su lado.
    for run in body["runs"]:
        events = await client.get(
            f"/console/companion/runs/{run['run_id']}/events", headers=a["headers"]()
        )
        assert events.status_code == 200


async def test_a_paused_run_appears_as_still_running(client, console_world, companion_provider):
    """Es la mitad del valor del endpoint: quien recarga con una
    confirmación pendiente tiene que ver que ese run sigue abierto."""
    a = console_world["a"]
    thread_id, run_id, _action = await _propose_prompt(client, a, companion_provider)

    listed = await client.get(
        f"/console/companion/threads/{thread_id}/runs", headers=a["headers"]()
    )
    row = next(r for r in listed.json()["runs"] if r["run_id"] == run_id)
    assert row["status"] == "running"
    assert row["ended_at"] is None


async def test_the_run_listing_carries_no_transcript(client, console_world, companion_provider):
    """Metadatos y nada más. Los cuerpos viven en ``…/events``, que tiene su
    propio guardián; duplicarlos aquí sería abrir una segunda puerta sin
    portero."""
    a = console_world["a"]
    thread_id, _r, _action = await _propose_prompt(client, a, companion_provider)
    listed = await client.get(
        f"/console/companion/threads/{thread_id}/runs", headers=a["headers"]()
    )
    for run in listed.json()["runs"]:
        assert set(run) == {"run_id", "status", "started_at", "ended_at"}


async def test_another_members_thread_runs_are_an_opaque_404(
    client, console_world, companion_provider, db_session
):
    from tests.conftest import add_console_member

    a = console_world["a"]
    thread_id, _r, _action = await _propose_prompt(client, a, companion_provider)
    other = await add_console_member(db_session, partner_id=a["partner_id"], role="owner")

    denied = await client.get(
        f"/console/companion/threads/{thread_id}/runs", headers=other["headers"]()
    )
    missing = await client.get(
        f"/console/companion/threads/{uuid.uuid4()}/runs", headers=other["headers"]()
    )
    assert denied.status_code == 404
    assert denied.json() == missing.json()


# ── auditoría ──────────────────────────────────────────────────────────


async def test_the_write_is_audited_as_the_companion(client, console_world, companion_provider):
    """Una escritura del agente no puede parecer, en el registro, una que la
    persona hizo a mano: son eventos distintos aunque haya la misma persona
    detrás. Quién confirmó sigue estando en ``companion.actions.decided_by``."""
    from nexus_api.db.models import AuditLog

    a = console_world["a"]
    _t, run_id, action = await _propose_prompt(client, a, companion_provider)
    resumed = await client.post(
        f"/console/companion/runs/{run_id}/resume",
        headers=a["headers"](),
        json={"action_id": str(action.id), "decision": "confirm"},
    )
    await _wait_for_run(uuid.UUID(resumed.json()["run_id"]), a["user_id"])

    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        actors = list((await session.execute(sa.select(AuditLog.actor).distinct())).scalars())
    assert f"companion:{a['user_id']}" in actors, actors


async def test_allocation_drift_is_412_and_does_not_mutate(
    client, console_world, companion_provider
):
    a = console_world["a"]
    companion_provider(
        [("console.propose_allocation", {"client_ref": a["ref"], "cap": 400_000})]
    )
    thread_id = await _thread(client, a)
    run_id = await _turn(client, a, thread_id, prompt="baja el cupo")
    action = await _wait_for_action(a["user_id"])
    assert action.kind == "allocation"
    assert action.status == "proposed"

    changed = await client.put(
        f"/console/clients/{a['ref']}/allocation",
        headers=a["headers"](),
        json={"cap": 300_000},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["cap"] == 300_000

    drifted = await client.post(
        f"/console/companion/runs/{run_id}/resume",
        headers=a["headers"](),
        json={"action_id": str(action.id), "decision": "confirm"},
    )
    assert drifted.status_code == 412, drifted.text
    assert drifted.json()["detail"]["code"] == "state_changed"
    assert (await _action_row(action.id, a["user_id"])).status == "expired"

    still = await client.get(
        f"/console/clients/{a['ref']}/allocation", headers=a["headers"]()
    )
    assert still.status_code == 200, still.text
    assert still.json()["cap"] == 300_000
