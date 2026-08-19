"""El piloto: la pausa por presupuesto y el escalado a soporte (CO-08).

Contra la aplicación real —los routers ``/console/*``, la RLS de
``companion.*``, el log durable de Redis y el checkpointer de LangGraph—
con el proveedor de modelo guionizado. Es donde se ve si el diseño aguanta,
porque aquí sí pasan las cosas que no pasan en un unitario: el run se cierra
en la base con el estado nuevo, el ticket sale por el endpoint de verdad y
el identificador vuelve por el stream.

- **E5** · por encima del tope, ``POST …/runs`` da **409 ``budget_paused``**
  y ``POST …/resume`` sigue dando **202**. Confirmar algo que ya se propuso
  no arranca trabajo nuevo, y dejarlo morir sería tirar a la basura justo el
  trabajo que ya se pagó.
- **E6** · el run cortado por presupuesto conserva historia y tokens y sale
  con ``status="paused"``. Un hilo pausado que pierde la historia no es una
  pausa, es un fallo con otro nombre.
- **Soporte** · propose → confirm → apply → ``support.ticket``, con el
  ``AU-<n>`` que nace al aplicar y la fila en el centro de notificaciones.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa
from nexus_worker.runtime.llm import InMemoryProvider, ToolCall

from nexus_api.api.console import companion as companion_api
from nexus_api.core.principal_context import apply_principal_to_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Partner
from nexus_api.db.models.companion import CompanionAction, CompanionMessage, CompanionRun

pytestmark = pytest.mark.asyncio

ANSWER = "Preparado. Dime si lo confirmas."


def _script(*rounds: list[tuple[str, dict[str, Any]]]):
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
    def _install(*rounds: list[tuple[str, dict[str, Any]]]) -> InMemoryProvider:
        provider = InMemoryProvider(
            responder=lambda _c: ANSWER, tool_caller=_script(*rounds) if rounds else None
        )
        companion_api.set_provider_for_tests(provider)
        return provider

    yield _install
    companion_api.reset_graph_cache_for_tests()


# ── utilidades ─────────────────────────────────────────────────────────


async def _set_cap(partner_id: uuid.UUID, cap: int) -> None:
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await session.execute(
            sa.update(Partner)
            .where(Partner.id == partner_id)
            .values(companion_monthly_token_cap=cap)
        )


async def _thread(client, world, mode: str = "build") -> str:
    created = await client.post(
        "/console/companion/threads",
        headers=world["headers"](),
        json={"title": "t", "mode": mode},
    )
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


async def _wait_for_run(run_id: uuid.UUID, principal_id: str, timeout: float = 15.0):
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


async def _wait_for_action(principal_id: str, timeout: float = 15.0) -> CompanionAction:
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


async def _events(client, world, run_id: str) -> list[dict[str, Any]]:
    resp = await client.get(f"/console/companion/runs/{run_id}/events", headers=world["headers"]())
    assert resp.status_code == 200, resp.text
    return list(resp.json()["events"])


# ── E5 · lo que acepta y lo que no un partner en pausa ─────────────────


async def test_over_the_cap_a_new_turn_is_409_budget_paused(
    client, console_world, companion_provider
):
    """E5, primera mitad. **409 y no 429 a propósito**: 429 significa
    "vuelve a intentarlo" y aquí reintentar no sirve — no pasa el tiempo,
    pasa que alguien sube el tope. Un ``Retry-After`` sería mentira."""
    a = console_world["a"]
    companion_provider()
    thread_id = await _thread(client, a)
    await _set_cap(a["partner_id"], 0)
    try:
        denied = await client.post(
            f"/console/companion/threads/{thread_id}/runs",
            headers=a["headers"](),
            json={"prompt": "hola"},
        )
        assert denied.status_code == 409, denied.text
        detail = denied.json()["detail"]
        assert detail["code"] == "budget_paused"
        # La instantánea viaja en el cuerpo para que la interfaz pinte la
        # explicación sin una segunda petición.
        assert set(detail) == {"code", "used", "cap", "period", "resets_at"}
        assert detail["cap"] == 0
        assert "Retry-After" not in denied.headers
    finally:
        await _set_cap(a["partner_id"], 500_000)


async def test_over_the_cap_reads_still_answer(client, console_world, companion_provider):
    """Un hilo en pausa no desaparece: la historia sigue ahí y se lee."""
    a = console_world["a"]
    companion_provider()
    thread_id = await _thread(client, a)
    await _set_cap(a["partner_id"], 0)
    try:
        for path in (
            "/console/companion/threads",
            "/console/companion/budget",
            f"/console/companion/threads/{thread_id}/runs",
        ):
            resp = await client.get(path, headers=a["headers"]())
            assert resp.status_code == 200, f"{path} → {resp.status_code}"
    finally:
        await _set_cap(a["partner_id"], 500_000)


async def test_over_the_cap_a_pending_confirmation_still_resumes(
    client, console_world, companion_provider
):
    """E5, segunda mitad y la que importa. Confirmar una acción propuesta
    **antes** de la pausa no arranca trabajo nuevo, y dejarla morir por un
    tope sería tirar a la basura justo el trabajo que ya se pagó."""
    a = console_world["a"]
    companion_provider(
        [("console.propose_prompt", {"client_ref": a["ref"], "system_prompt": "Sé breve."})]
    )
    thread_id = await _thread(client, a)
    started = await client.post(
        f"/console/companion/threads/{thread_id}/runs",
        headers=a["headers"](),
        json={"prompt": "cambia el prompt"},
    )
    assert started.status_code == 202, started.text
    run_id = started.json()["run_id"]
    action = await _wait_for_action(a["user_id"])

    await _set_cap(a["partner_id"], 0)
    try:
        resumed = await client.post(
            f"/console/companion/runs/{run_id}/resume",
            headers=a["headers"](),
            json={"action_id": str(action.id), "decision": "confirm"},
        )
        assert resumed.status_code == 202, resumed.text
        assert resumed.json()["status"] == "confirmed"
    finally:
        await _set_cap(a["partner_id"], 500_000)


# ── E6 · el turno que cruza el tope conserva todo ──────────────────────


async def test_a_turn_that_crosses_the_cap_pauses_and_keeps_everything(
    client, console_world, companion_provider
):
    """E6. El proveedor guionizado reporta 120 tokens por turno; con el tope
    en 100 el turno arranca (0 < 100) y lo cruza al reportar.

    Lo que se comprueba es lo que hace que una pausa sea una pausa y no un
    fallo con otro nombre: el evento, el estado terminal, y que la historia,
    la respuesta parcial y los tokens **siguen ahí**.
    """
    a = console_world["a"]
    companion_provider()
    thread_id = await _thread(client, a, mode="consult")
    await _set_cap(a["partner_id"], 100)
    try:
        started = await client.post(
            f"/console/companion/threads/{thread_id}/runs",
            headers=a["headers"](),
            json={"prompt": "¿cuántos clientes tengo?"},
        )
        assert started.status_code == 202, started.text
        run_id = started.json()["run_id"]
        row = await _wait_for_run(uuid.UUID(run_id), a["user_id"])

        assert row.status == "paused", row.status
        assert row.ended_at is not None  # terminal: el reaper no lo toca
        # Los tokens se conservan: el turno se pagó y tiene que contar.
        assert (row.input_tokens or 0) + (row.output_tokens or 0) > 0

        events = await _events(client, a, run_id)
        names = [e["event"] for e in events]
        assert "budget.paused" in names, names
        paused = next(e["data"] for e in events if e["event"] == "budget.paused")
        assert set(paused) == {"used", "cap", "period", "resets_at", "scope"}
        assert paused["scope"] == "partner"
        assert paused["used"] >= paused["cap"]

        terminal = next(e["data"] for e in events if e["event"] == "run.completed")
        assert terminal["status"] == "paused"

        # Y la historia: la respuesta parcial quedó persistida como mensaje
        # del hilo. Sin esto el usuario volvería a un hilo que no coincide
        # con lo que vio en pantalla.
        sm = get_sessionmaker()
        async with sm() as session, session.begin():
            await apply_principal_to_session(session, a["user_id"])
            roles = list(
                (
                    await session.execute(
                        sa.select(CompanionMessage.role)
                        .where(CompanionMessage.thread_id == uuid.UUID(thread_id))
                        .order_by(CompanionMessage.seq)
                    )
                ).scalars()
            )
        assert roles == ["user", "assistant"], roles
    finally:
        await _set_cap(a["partner_id"], 500_000)


async def test_a_paused_run_does_not_block_the_concurrency_cap(
    client, console_world, companion_provider
):
    """``paused`` es terminal, así que no cuenta como trabajo en vuelo. Si
    contara, cruzar el tope una vez dejaría al miembro con un hueco menos
    para siempre."""
    a = console_world["a"]
    companion_provider()
    thread_id = await _thread(client, a, mode="consult")
    await _set_cap(a["partner_id"], 100)
    try:
        started = await client.post(
            f"/console/companion/threads/{thread_id}/runs",
            headers=a["headers"](),
            json={"prompt": "hola"},
        )
        run = await _wait_for_run(uuid.UUID(started.json()["run_id"]), a["user_id"])
        assert run.status == "paused"
    finally:
        await _set_cap(a["partner_id"], 500_000)

    # Con el tope restaurado el hilo sigue vivo y acepta trabajo otra vez:
    # subir el tope reanuda, sin despausar nada a mano.
    again = await client.post(
        f"/console/companion/threads/{thread_id}/runs",
        headers=a["headers"](),
        json={"prompt": "otra vez"},
    )
    assert again.status_code == 202, again.text


# ── soporte, de punta a punta ──────────────────────────────────────────


async def _propose_ticket(client, world, companion_provider, **args: Any):
    payload = {
        "topic": "connector.shopify",
        "need": "Sincronizar pedidos de Shopify para responder por el envío",
        **args,
    }
    companion_provider(
        [
            ("console.list_clients", {}),
            ("console.get_capabilities", {}),
        ],
        [("support.request_help", payload)],
    )
    thread_id = await _thread(client, world)
    started = await client.post(
        f"/console/companion/threads/{thread_id}/runs",
        headers=world["headers"](),
        json={"prompt": "¿puedo conectar Shopify?"},
    )
    assert started.status_code == 202, started.text
    action = await _wait_for_action(world["user_id"])
    return thread_id, str(started.json()["run_id"]), action


async def test_a_support_ticket_is_proposed_with_the_file_it_read(
    client, console_world, companion_provider
):
    """El expediente del §25.1: ``checked`` sale de las etiquetas de las
    lecturas del turno, no de texto libre. Es lo que hace que soporte no
    empiece de cero."""
    a = console_world["a"]
    _t, _r, action = await _propose_ticket(client, a, companion_provider)

    assert action.kind == "support_help"
    assert action.status == "proposed"
    preview = dict(action.payload["preview"])
    assert preview["category"] == "help"
    assert preview["topic"] == "connector.shopify"
    assert preview["bridge"] is False
    assert preview["alternative"] is None
    assert len(preview["checked"]) >= 2, preview["checked"]
    # Etiquetas del catálogo, no prosa del modelo.
    assert any("cliente" in c.lower() or "clientes" in c.lower() for c in preview["checked"])
    # Y nada que se llame como el cuerpo de un mensaje de un cliente final.
    assert not ({"text", "body", "content", "message", "notes", "reason"} & set(preview))


async def test_confirming_opens_the_ticket_and_the_reference_comes_back(
    client, console_world, companion_provider
):
    """El identificador y la expectativa (§4.4), y el evento que los trae
    (§4.5). Sin identificador el ticket es un agujero negro."""
    a = console_world["a"]
    _t, run_id, action = await _propose_ticket(client, a, companion_provider)

    resumed = await client.post(
        f"/console/companion/runs/{run_id}/resume",
        headers=a["headers"](),
        json={"action_id": str(action.id), "decision": "confirm"},
    )
    assert resumed.status_code == 202, resumed.text
    new_run = resumed.json()["run_id"]
    await _wait_for_run(uuid.UUID(new_run), a["user_id"])

    events = await _events(client, a, new_run)
    names = [e["event"] for e in events]
    assert "support.ticket" in names, names
    # §4.5: después del 2xx de ``console.apply`` y ANTES de ``verify.result``.
    assert names.index("support.ticket") < names.index("verify.result")

    ticket = next(e["data"] for e in events if e["event"] == "support.ticket")
    assert set(ticket) == {"action_id", "ticket_ref", "category", "topic", "sla"}
    assert ticket["ticket_ref"].startswith("AU-")
    assert ticket["category"] == "help"
    assert ticket["topic"] == "connector.shopify"
    # Identificador estable, no una frase: la interfaz lo traduce.
    assert ticket["sla"] == "next_business_day"

    # Y aterrizó donde §4.3 dice: el centro de notificaciones del partner.
    notifications = await client.get("/console/notifications", headers=a["headers"]())
    assert notifications.status_code == 200
    kinds = {n["kind"] for n in notifications.json()["items"]}
    assert "support.ticket_opened" in kinds, kinds
    row = next(n for n in notifications.json()["items"] if n["kind"] == "support.ticket_opened")
    assert row["data"]["ticket_ref"] == ticket["ticket_ref"]
    assert row["severity"] == "info"

    # Y la auditoría del partner lo cuenta como una frase, con la persona
    # detrás del Companion (cabo 3).
    audit = await client.get(
        "/console/audit?action=console.support&lang=es", headers=a["headers"]()
    )
    assert audit.status_code == 200, audit.text
    entries = audit.json()["items"]
    assert entries, audit.text
    assert entries[0]["actor"] == "Companion · owner-a@example.com"
    assert ticket["ticket_ref"] in entries[0]["summary"]


async def test_the_ticket_reference_survives_the_rotation_of_the_redis_log(
    client, console_world, companion_provider
):
    """§19.4. ``support.ticket`` viaja por el log de Redis y el log **rota**.
    Si ``hitl.requested`` rotó y el evento del ticket no, la interfaz se
    queda sin tarjeta a la que atar el ``ticket_ref`` y el usuario pierde en
    silencio el identificador del ticket que acaba de abrir.

    Se cierra igual que la v1.1 cerró la tarjeta pendiente: por el endpoint
    de la acción, que lee de Postgres y no depende de que Redis siga vivo.
    """
    a = console_world["a"]
    _t, run_id, action = await _propose_ticket(client, a, companion_provider)

    # Antes de aplicar no hay ticket, y decirlo con ``null`` es más honesto
    # que inventar un identificador que todavía no existe.
    before = await client.get(f"/console/companion/actions/{action.id}", headers=a["headers"]())
    assert before.status_code == 200, before.text
    assert before.json()["ticket_ref"] is None
    assert before.json()["sla"] is None

    resumed = await client.post(
        f"/console/companion/runs/{run_id}/resume",
        headers=a["headers"](),
        json={"action_id": str(action.id), "decision": "confirm"},
    )
    assert resumed.status_code == 202, resumed.text
    await _wait_for_run(uuid.UUID(resumed.json()["run_id"]), a["user_id"])

    after = await client.get(f"/console/companion/actions/{action.id}", headers=a["headers"]())
    assert after.status_code == 200, after.text
    body = after.json()
    assert body["status"] == "applied"
    assert body["ticket_ref"].startswith("AU-")
    assert body["sla"] == "next_business_day"


async def test_a_non_support_action_carries_no_ticket_fields(
    client, console_world, companion_provider
):
    """Nulos para todo ``kind`` que no sea de soporte: el mapa ``APPLY_ECHO``
    no tiene entrada para ellos, así que no hay de dónde sacarlos ni forma de
    inventárselos."""
    a = console_world["a"]
    companion_provider(
        [("console.propose_prompt", {"client_ref": a["ref"], "system_prompt": "Sé breve."})]
    )
    thread_id = await _thread(client, a)
    started = await client.post(
        f"/console/companion/threads/{thread_id}/runs",
        headers=a["headers"](),
        json={"prompt": "cambia el prompt"},
    )
    assert started.status_code == 202
    action = await _wait_for_action(a["user_id"])

    got = await client.get(f"/console/companion/actions/{action.id}", headers=a["headers"]())
    assert got.status_code == 200
    assert got.json()["ticket_ref"] is None
    assert got.json()["sla"] is None


async def test_a_ticket_without_a_file_is_refused_by_the_engine(
    client, console_world, companion_provider
):
    """§25.1 entero: un ticket sin expediente es lo que este mecanismo
    existe para evitar. Sin ni una lectura, no hay propuesta — y el modelo
    recibe un motivo que le dice qué hacer, no un fallo opaco."""
    a = console_world["a"]
    companion_provider(
        [
            (
                "support.request_help",
                {"topic": "connector.shopify", "need": "quiero Shopify"},
            )
        ]
    )
    thread_id = await _thread(client, a)
    started = await client.post(
        f"/console/companion/threads/{thread_id}/runs",
        headers=a["headers"](),
        json={"prompt": "abre un ticket"},
    )
    assert started.status_code == 202
    run_id = started.json()["run_id"]
    await _wait_for_run(uuid.UUID(run_id), a["user_id"])

    events = await _events(client, a, run_id)
    assert "hitl.requested" not in [e["event"] for e in events]
    failed = [
        e["data"]
        for e in events
        if e["event"] == "tool.call.completed" and e["data"]["name"] == "support.request_help"
    ]
    assert failed and failed[0]["ok"] is False
    assert failed[0]["error"] == "no_evidence", failed[0]


async def test_the_capability_document_is_served_and_takes_no_parameters(client, console_world):
    """§5.3: el documento es el mismo para todos los partners. Un filtro
    convertiría un catálogo público en una superficie con ámbito."""
    a, b = console_world["a"], console_world["b"]
    mine = await client.get("/console/capabilities", headers=a["headers"]())
    theirs = await client.get("/console/capabilities", headers=b["headers"]())
    assert mine.status_code == 200, mine.text
    assert mine.json() == theirs.json()

    body = mine.json()
    assert body["version"]
    keys = {e["key"] for e in body["entries"]}
    assert "capability.embed_widget" in keys
    for entry in body["entries"]:
        assert set(entry) == {"key", "family", "status", "label", "note", "eta", "replaced_by"}
