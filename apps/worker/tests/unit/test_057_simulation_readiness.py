"""Spec 057, T033 (requisitos 4.1 y 4.2): el playground y las pruebas del agente
dicen si la agenda está lista.

- ``run_turn(agenda_ready=...)``: el manejador usa lo que se le da en vez de
  leerlo de la base. ``False``: la cita pasa a una persona en el mundo simulado y
  no se reserva nada. ``True``: reserva. Sin dar nada, se lee (el canal).
- **La suite del agente** (``jobs/handlers/agent_tests.py``) corre con
  ``agenda_ready=True``: mide el texto del agente, no lo que le falta al cliente.
  Un cliente sin profesionales no suspende las pruebas de reservar ni bloquea la
  publicación (decisión 1 de Luis).
- El playground pasa la de verdad: ``apps/api/tests/integration/builder/test_playground_draft.py``.

``run_turn`` corre de verdad con el registro simulado y el manejador de verdad;
solo se sustituyen su base (la versión, el mensaje entrante) y el grafo alrededor
del manejador (clasificar y guardar la respuesta, que escriben en la base).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

import pytest
from nexus_api.services.activations import ToolPolicy
from nexus_api.services.router_catalog import CatalogSnapshot

import nexus_worker.runtime.pipeline as pipeline
from nexus_worker.jobs.handlers import agent_tests
from nexus_worker.runtime import agent_loader, booking_brake
from nexus_worker.runtime.agent_loader import AgentBundle
from nexus_worker.runtime.llm import CooldownBook, InMemoryProvider, LLMCall, LLMRouter, ToolCall
from nexus_worker.runtime.model_resolver import RouteFacts
from nexus_worker.simulation import runner
from nexus_worker.simulation.customer import Conversation
from nexus_worker.simulation.runner import SimConversation, run_turn
from nexus_worker.simulation.world import SimService, World
from tests.unit._router_world import AGENT, TENANT, snapshot

pytestmark = pytest.mark.asyncio

VERSION = uuid.UUID("00000000-0000-0000-0000-0000000057a1")
HAND_OFF = "escalate.escalate_to_human"
TOOLS = frozenset(
    {"reservas.services", "reservas.find_slots", "reservas.create", "reservas.list_mine", HAND_OFF}
)
#: Lunes 9 de noviembre de 2026, 09:00 en Madrid; abre todos los días de 10 a 20.
NOW = "2026-11-09T08:00:00+00:00"
TUESDAY = "2026-11-10"


def _world() -> World:
    return World(
        timezone="Europe/Madrid",
        now=NOW,
        week=[[[600, 1200]] for _ in range(7)],
        services=[SimService(id=str(uuid.uuid4()), name="Masaje", duration_min=60, bookable=True)],
    )


def _conv() -> SimConversation:
    return SimConversation(
        channel_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
        identifier="sim::test",
    )


class _Session:
    """La base de ``run_turn``: la versión que se prueba y el mensaje entrante."""

    async def get(self, _model: Any, _id: Any) -> Any:
        return SimpleNamespace(agent_id=AGENT)

    def add(self, obj: Any) -> None:
        obj.id = uuid.uuid4()

    async def flush(self) -> None:
        return None


class _HandlerOnly:
    """El grafo alrededor del manejador de ``book``: ni clasifica ni guarda."""

    def __init__(self, *, agent_loader: Any, llm_router: Any, mcp_registry: Any, **_: Any) -> None:
        self.handler = pipeline.make_handler_node("book", agent_loader, llm_router, mcp_registry)

    async def ainvoke(self, state: dict[str, Any], config: Any = None) -> dict[str, Any]:
        out: dict[str, Any] = await self.handler(state)  # type: ignore[arg-type]
        return {**state, **out, "intent": "book"}


@pytest.fixture
def reads(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[uuid.UUID]]:
    """Lo que ``run_turn`` y el manejador leerían de la base, sustituido. Devuelve
    las lecturas de la agenda que hizo el manejador."""
    seen: list[uuid.UUID] = []

    @asynccontextmanager
    async def session() -> AsyncIterator[_Session]:
        yield _Session()

    @asynccontextmanager
    async def scoped(_session: Any, _tenant: uuid.UUID) -> AsyncIterator[None]:
        yield

    async def bundle_of(_session: Any, tenant_id: uuid.UUID, _cfg: Any) -> AgentBundle:
        return AgentBundle(
            tenant_id=tenant_id,
            version=1,
            version_id=VERSION,
            system_prompt="Eres la recepción del spa. Das citas.",
            tools=TOOLS,
            agent_id=AGENT,
        )

    async def no_connectors(_session: Any) -> dict[str, bool]:
        return {}

    async def on(_session: Any, _tenant: uuid.UUID) -> bool:
        return True

    async def no_partner(_tenant: uuid.UUID) -> None:
        return None

    async def readiness(tenant_id: uuid.UUID) -> bool:
        seen.append(tenant_id)
        return False

    async def nothing(*_a: Any, **_k: Any) -> Any:
        return ""

    async def no_knowledge(*_a: Any, **_k: Any) -> tuple[str, list[Any]]:
        return "", []

    async def no_gates(_tenant: uuid.UUID) -> frozenset[str]:
        return frozenset()

    async def open_policy(_tenant: uuid.UUID, _agent: uuid.UUID | None) -> ToolPolicy:
        return ToolPolicy()

    async def catalog(*, force: bool = False) -> CatalogSnapshot:
        return snapshot([], [])

    async def facts(*_a: Any, **_k: Any) -> RouteFacts:
        return RouteFacts(eu_only=True)

    async def no_record(**_k: Any) -> None:
        return None

    monkeypatch.setattr(runner, "get_sessionmaker", lambda: session)
    monkeypatch.setattr(runner, "tenant_scoped_session", scoped)
    monkeypatch.setattr(runner, "load_connector_tools", no_connectors)
    monkeypatch.setattr(agent_loader, "bundle_of", bundle_of)
    monkeypatch.setattr("nexus_api.services.reservations.passing.reservas_enabled", on)
    monkeypatch.setattr("nexus_api.core.llm_proxy.partner_id_for_tenant_standalone", no_partner)
    monkeypatch.setattr(pipeline, "build_pipeline", _HandlerOnly)
    monkeypatch.setattr(pipeline, "_load_agenda_ready", readiness)
    monkeypatch.setattr(pipeline, "_load_kg_snapshot_text", nothing)
    monkeypatch.setattr(pipeline, "_load_knowledge", no_knowledge)
    monkeypatch.setattr(pipeline, "_load_gated_tools", no_gates)
    monkeypatch.setattr(pipeline, "_load_tool_policy", open_policy)
    monkeypatch.setattr(pipeline, "get_catalog_snapshot", catalog)
    monkeypatch.setattr(pipeline, "load_route_facts", facts)
    monkeypatch.setattr(pipeline, "_now_note", lambda _tz: "Hoy es lunes, 09:00.")
    monkeypatch.setattr(booking_brake, "record_brake", no_record)
    yield seen


def _router() -> tuple[LLMRouter, InMemoryProvider]:
    """Un modelo que, con la agenda, reserva el martes a las 10; sin ella, pasa
    la cita al equipo con el servicio, el día y la hora."""

    def answered(call: LLMCall) -> bool:
        return bool(call.messages) and call.messages[-1].get("role") == "tool"

    def offered(call: LLMCall) -> set[str]:
        return {t["function"]["name"] for t in call.tools}

    def tool_caller(call: LLMCall) -> list[ToolCall]:
        if call.role != "book" or answered(call):
            return []
        if "reservas.create" in offered(call):
            args = {"date": TUESDAY, "time": "10:00", "service_name": "Masaje"}
            return [ToolCall(id="c1", name="reservas.create", arguments=args)]
        reason = "Cita: masaje, martes 10 de noviembre a las 10:00"
        return [ToolCall(id="e1", name=HAND_OFF, arguments={"reason": reason})]

    def responder(call: LLMCall) -> str:
        if call.role == "classify":
            return "NO"
        if not answered(call):
            return ""
        if "reservas.create" in offered(call):
            return "Listo, te reservé el masaje el martes a las 10:00."
        return "Se lo paso al equipo, que te escribirá para confirmar la hora."

    provider = InMemoryProvider(responder=responder, tool_caller=tool_caller)
    router = LLMRouter(
        provider=provider,
        classify_model="t/c",
        respond_model="t/r",
        fallback_model="t/f",
        cooldowns=CooldownBook(),
        retry_backoff_s=0.0,
    )
    return router, provider


async def _run(world: World, agenda_ready: bool | None) -> Any:
    router, _ = _router()
    return await run_turn(
        tenant_id=TENANT,
        version_id=VERSION,
        world=world,
        conv=_conv(),
        text="Quiero un masaje el martes a las 10",
        llm_router=router,
        agenda_ready=agenda_ready,
    )


async def test_an_unready_agenda_hands_the_appointment_to_a_person(
    reads: list[uuid.UUID],
) -> None:
    world = _world()

    outcome = await _run(world, False)

    assert reads == [], "lo que se da no se lee"
    assert world.escalated is True
    assert not world.bookings, "nada reservado"
    phrases = [a["phrase"] for a in outcome.actions]
    assert phrases == [
        "Pasar la conversación al equipo: Cita: masaje, martes 10 de noviembre a las 10:00"
    ]
    assert outcome.bubbles == ["Se lo paso al equipo, que te escribirá para confirmar la hora."]
    assert outcome.failure is None


async def test_a_ready_agenda_books(reads: list[uuid.UUID]) -> None:
    world = _world()

    outcome = await _run(world, True)

    assert reads == []
    assert [b.status for b in world.bookings] == ["confirmed"]
    assert world.escalated is False
    assert [a["tool"] for a in outcome.actions] == ["reservas.create"]


async def test_without_a_given_readiness_the_handler_reads_it(reads: list[uuid.UUID]) -> None:
    """El canal no da nada: el manejador lo lee, con la RLS del cliente."""
    world = _world()

    await _run(world, None)

    assert reads == [TENANT]
    assert world.escalated is True and not world.bookings


async def test_the_readiness_does_not_outlive_the_turn(reads: list[uuid.UUID]) -> None:
    await _run(_world(), True)

    assert pipeline.given_agenda_ready() is None


# ── la suite del agente ────────────────────────────────────────────────────


async def test_the_agent_suite_runs_with_a_ready_agenda(monkeypatch: pytest.MonkeyPatch) -> None:
    """Las pruebas miden el texto del agente: un cliente sin profesionales no
    suspende las de reservar."""
    calls: list[dict[str, Any]] = []

    @asynccontextmanager
    async def session() -> AsyncIterator[Any]:
        yield object()

    @asynccontextmanager
    async def scoped(_session: Any, _tenant: uuid.UUID) -> AsyncIterator[None]:
        yield

    async def seed(_session: Any, _agent: uuid.UUID) -> World:
        return _world()

    async def opened(_tenant: uuid.UUID) -> SimConversation:
        return _conv()

    async def closed(*_a: Any) -> None:
        return None

    async def fake_run_turn(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return SimpleNamespace(bubbles=["Hola"], actions=[], failure=None)

    async def fake_converse(*, agent_turn: Any, first_message: str, **_k: Any) -> Conversation:
        await agent_turn(first_message)
        return Conversation(transcript=[])

    async def decided(**_k: Any) -> tuple[bool, None, list[Any]]:
        return True, None, []

    async def recorded(*_a: Any, **_k: Any) -> None:
        return None

    monkeypatch.setattr(agent_tests, "get_sessionmaker", lambda: session)
    monkeypatch.setattr(agent_tests, "tenant_scoped_session", scoped)
    monkeypatch.setattr(agent_tests, "seed_world", seed)
    monkeypatch.setattr(agent_tests, "open_conversation", opened)
    monkeypatch.setattr(agent_tests, "close_conversation", closed)
    monkeypatch.setattr(agent_tests, "run_turn", fake_run_turn)
    monkeypatch.setattr(agent_tests, "converse", fake_converse)
    monkeypatch.setattr(agent_tests, "_decide", decided)
    monkeypatch.setattr(agent_tests, "_record", recorded)

    run = SimpleNamespace(
        agent_id=AGENT, agent_config_id=VERSION, reason="manual", model_policy=None
    )
    test = SimpleNamespace(id=uuid.uuid4(), first_message="Quiero cita", persona="", plan="")
    passed = await agent_tests._attempt(
        ctx=SimpleNamespace(tenant_id=TENANT),  # type: ignore[arg-type]
        run=run,  # type: ignore[arg-type]
        test=test,  # type: ignore[arg-type]
        attempt=1,
        judge=None,
        judge_blocks=False,
        router=None,
    )

    assert passed is True
    [call] = calls
    assert call["agenda_ready"] is True
