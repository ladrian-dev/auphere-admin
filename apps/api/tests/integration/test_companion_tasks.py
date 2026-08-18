"""Los cinco trabajos del §4.3, en su forma de consulta (CO-02).

Extremo a extremo de verdad: el POST devuelve 202, el driver arranca, el
grafo pide herramientas, las herramientas entran por el ASGI a los routers
``/console/*`` reales —con su ``client_scope``, su RLS y sus permisos—, y
los eventos salen por el log durable de Redis.

Lo único simulado es el modelo: ``InMemoryProvider`` con un guion de qué
herramientas pediría en cada paso. Eso es exactamente lo que hay que
simular, porque lo que se prueba no es si el modelo elige bien la
herramienta —eso son los evals— sino si el carril entero funciona cuando la
elige.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import pytest
import pytest_asyncio
from nexus_worker.runtime.llm import InMemoryProvider, ToolCall

from nexus_api.api.console import companion as companion_api
from nexus_api.core.principal_context import apply_principal_to_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models.companion import CompanionRun

pytestmark = pytest.mark.asyncio


def _script(*rounds: list[tuple[str, dict[str, Any]]]):
    """``tool_caller`` con un guion por paso; después, respuesta."""
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
def companion_provider(monkeypatch):
    """Instala un proveedor en memoria y deja el resto del camino REAL: el
    grafo se compila por run, con su propio juego de herramientas."""

    def _install(
        *, answer: str, rounds: tuple[list[tuple[str, dict]], ...] = ()
    ) -> InMemoryProvider:
        provider = InMemoryProvider(
            responder=lambda _c: answer,
            tool_caller=_script(*rounds) if rounds else None,
        )
        companion_api.set_provider_for_tests(provider)
        return provider

    yield _install
    companion_api.reset_graph_cache_for_tests()


async def _events(client, world, prompt: str) -> tuple[list[dict], dict]:
    """Un turno completo. Devuelve los eventos y la fila del run cerrada."""
    created = await client.post(
        "/console/companion/threads", headers=world["headers"](), json={"title": "t"}
    )
    assert created.status_code == 201, created.text
    thread_id = created.json()["id"]
    started = await client.post(
        f"/console/companion/threads/{thread_id}/runs",
        headers=world["headers"](),
        json={"prompt": prompt},
    )
    assert started.status_code == 202, started.text
    run_id = started.json()["run_id"]

    run = await _finished(uuid.UUID(run_id), world["user_id"])
    listed = await client.get(
        f"/console/companion/runs/{run_id}/events", headers=world["headers"]()
    )
    assert listed.status_code == 200, listed.text
    return listed.json()["events"], {"row": run, "run_id": run_id}


async def _finished(run_id: uuid.UUID, principal_id: str, timeout: float = 10.0) -> CompanionRun:
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


def _named(events: list[dict], name: str) -> list[dict]:
    return [e["data"] for e in events if e["event"] == name]


def _tools_used(events: list[dict]) -> list[str]:
    return [d["name"] for d in _named(events, "tool.call.started")]


# ── §4.3.1 · crear un cliente, en su forma de consulta ─────────────────


async def test_a_new_client_walkthrough_reads_quota_and_templates(
    client, console_world, companion_provider
):
    """ "Necesito un agente para una clínica dental." En CO-02 no se crea
    nada: se lee la cuota y la biblioteca, y se dice qué haría falta."""
    companion_provider(
        answer="Te queda cuota. La plantilla de clínica pide nombre fiscal y horarios.",
        rounds=([("console.get_quota", {}), ("console.get_prompt_library", {})],),
    )
    events, run = await _events(
        client, console_world["a"], "quiero un agente para una clínica dental"
    )
    assert set(_tools_used(events)) == {"console.get_quota", "console.get_prompt_library"}
    assert run["row"].status == "completed"
    # Dos lecturas con éxito ⇒ dos citas.
    assert len(_named(events, "citation")) == 2


# ── §4.3.2 · mejorar un prompt con contexto real ───────────────────────


async def test_improving_a_prompt_reads_the_agent_its_tools_and_its_policy(
    client, console_world, companion_provider
):
    a = console_world["a"]
    companion_provider(
        answer="El prompt no menciona los horarios que sí están en la política.",
        rounds=(
            [
                ("console.get_agent", {"client_ref": a["ref"]}),
                ("console.list_tools", {"client_ref": a["ref"]}),
                ("console.get_policy", {"client_ref": a["ref"]}),
            ],
        ),
    )
    events, _run = await _events(client, a, "mejora el prompt de este cliente")
    assert set(_tools_used(events)) == {
        "console.get_agent",
        "console.list_tools",
        "console.get_policy",
    }
    assert all(d["ok"] for d in _named(events, "tool.call.completed"))


# ── §4.3.3 · diagnosticar "no funciona" ────────────────────────────────


async def test_diagnosing_chains_channels_diagnostics_templates_and_audit(
    client, console_world, companion_provider
):
    """El encadenado del §4.3: canales → diagnóstico → plantillas →
    auditoría, en dos rondas, que es como sale de verdad."""
    a = console_world["a"]
    companion_provider(
        answer="El canal no está conectado; por eso no salen mensajes.",
        rounds=(
            [
                ("console.list_channels", {"client_ref": a["ref"]}),
                ("console.channel_diagnostics", {"client_ref": a["ref"]}),
            ],
            [("console.get_audit", {"client_ref": a["ref"], "limit": 20})],
        ),
    )
    events, run = await _events(client, a, "el agente de este cliente no responde")
    used = _tools_used(events)
    assert used[:2] == ["console.list_channels", "console.channel_diagnostics"]
    assert "console.get_audit" in used
    assert run["row"].status == "completed"


async def test_a_tool_that_the_platform_refuses_is_reported_not_hidden(
    client, console_world, companion_provider
):
    """Las plantillas dan 409 sin WhatsApp conectado. Eso es la respuesta,
    no un error que ocultar — y el evento lo dice."""
    a = console_world["a"]
    companion_provider(
        answer="No hay WhatsApp conectado, así que no hay plantillas que mirar.",
        rounds=([("console.list_templates", {"client_ref": a["ref"]})],),
    )
    events, _run = await _events(client, a, "¿qué plantillas tiene?")
    completed = _named(events, "tool.call.completed")[0]
    assert completed["ok"] is False
    assert completed["error"] in {"conflict", "unavailable"}
    assert not _named(events, "citation")


# ── §4.3.4 · explicar el gasto ─────────────────────────────────────────


async def test_explaining_the_spend_reads_the_total_and_then_the_series(
    client, console_world, companion_provider
):
    a = console_world["a"]
    companion_provider(
        answer="El gasto del mes está en el total; la serie no muestra ningún salto.",
        rounds=(
            [("console.get_usage", {"client_ref": a["ref"], "days": 30})],
            [("console.usage_series", {"client_ref": a["ref"], "days": 30})],
        ),
    )
    events, _run = await _events(client, a, "¿por qué subió el consumo de este cliente?")
    assert _tools_used(events) == ["console.get_usage", "console.usage_series"]
    sources = [d["source"] for d in _named(events, "citation")]
    assert any(s.startswith("/console/usage?") for s in sources)
    assert any(s.startswith("/console/usage/series?") for s in sources)


# ── §4.3.5 · enseñar la plataforma sin documentación ───────────────────


async def test_explaining_a_skill_reads_the_live_catalogue(
    client, console_world, companion_provider
):
    a = console_world["a"]
    companion_provider(
        answer="Esa skill da formato a las respuestas con botones nativos de WhatsApp.",
        rounds=([("console.list_skills", {"client_ref": a["ref"]})],),
    )
    events, _run = await _events(
        client, a, "¿qué hace la skill de componentes nativos de WhatsApp?"
    )
    assert _tools_used(events) == ["console.list_skills"]
    assert len(_named(events, "citation")) == 1


# ── garantías transversales ────────────────────────────────────────────


async def test_asking_about_a_client_of_another_partner_is_an_opaque_404(
    client, console_world, companion_provider
):
    """La garantía C1, extremo a extremo: el turno termina bien y el evento
    dice ``unknown_client``, sin distinguirlo de un ref inexistente."""
    companion_provider(
        answer="No encuentro ese cliente con esa referencia.",
        rounds=([("console.get_client", {"client_ref": console_world["b"]["ref"]})],),
    )
    events, run = await _events(client, console_world["a"], "cuéntame de ese cliente")
    completed = _named(events, "tool.call.completed")[0]
    assert completed["ok"] is False and completed["error"] == "unknown_client"
    assert run["row"].status == "completed"


async def test_a_turn_that_states_a_figure_without_reading_is_flagged_unsupported(
    client, console_world, companion_provider
):
    """Regla R1, y llega hasta el evento terminal — que es donde se mide."""
    companion_provider(answer="Tienes 14 clientes y gastaste 2.400.000 tokens este mes.")
    events, _run = await _events(client, console_world["a"], "¿cuántos clientes tengo?")
    assert not _tools_used(events)
    completed = _named(events, "run.completed")[0]
    assert completed["unsupported"] is True


async def test_a_turn_that_read_first_is_not_flagged(client, console_world, companion_provider):
    companion_provider(
        answer="Tienes 1 cliente activo.",
        rounds=([("console.list_clients", {})],),
    )
    events, _run = await _events(client, console_world["a"], "¿cuántos clientes tengo?")
    completed = _named(events, "run.completed")[0]
    assert completed["unsupported"] is False


async def test_no_tool_event_ever_carries_what_a_tool_read(
    client, console_world, companion_provider
):
    """Decisión C8, a nivel de cable: el resultado de la lectura va al
    contexto del modelo, nunca al stream. Lo garantiza el catálogo cerrado,
    y esto lo comprueba sobre eventos reales."""
    a = console_world["a"]
    companion_provider(
        answer="listo",
        rounds=([("console.get_client", {"client_ref": a["ref"]})],),
    )
    events, _run = await _events(client, a, "dime de este cliente")
    for event in events:
        if event["event"].startswith("tool.call."):
            assert set(event["data"]) <= {
                "tool_call_id",
                "name",
                "label",
                "args",
                "ok",
                "latency_ms",
                "error",
                "citation_id",
            }
            assert "content" not in event["data"] and "result" not in event["data"]


async def test_the_answer_lands_in_the_thread_history(client, console_world, companion_provider):
    """El turno se persiste como cualquier otro: lo que el usuario vio
    tiene que seguir ahí después de un F5."""
    a = console_world["a"]
    companion_provider(answer="Tienes un cliente activo.", rounds=([("console.list_clients", {})],))
    _events_list, run = await _events(client, a, "¿cuántos clientes tengo?")
    assert run["row"].output_tokens > 0

    from nexus_api.db.models.companion import CompanionMessage

    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_principal_to_session(session, a["user_id"])
        import sqlalchemy as sa

        rows = (
            await session.execute(
                sa.select(CompanionMessage.role, CompanionMessage.content).order_by(
                    CompanionMessage.seq
                )
            )
        ).all()
    assert [r[0] for r in rows] == ["user", "assistant"]
    assert rows[1][1] == "Tienes un cliente activo."


async def test_the_tool_args_event_only_carries_what_the_model_wrote(
    client, console_world, companion_provider
):
    a = console_world["a"]
    companion_provider(
        answer="ok", rounds=([("console.get_usage", {"client_ref": a["ref"], "days": 7})],)
    )
    events, _run = await _events(client, a, "gasto")
    started = _named(events, "tool.call.started")[0]
    assert json.loads(started["args"]) == {"client_ref": a["ref"], "days": 7}
