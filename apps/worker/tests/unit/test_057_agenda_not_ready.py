"""Spec 057, T031 (requisitos 4.2 y 4.3): la agenda aún no está lista.

El partner publica un agente con agenda antes de que el cliente termine Reservas
(sin profesionales, sin horario…). Mientras falte algo, en **cada turno** y con la
RLS del cliente (``research.md`` R4):

- **las herramientas**: se quitan las que piden una agenda terminada
  (``find_slots``, ``create``, ``reschedule``, ``join_waitlist``,
  ``answer_offer``) y se quedan ``services``, ``list_mine``, ``cancel`` y
  ``confirm_attendance``. La tupla es también la lista blanca del despacho;
- **la nota**: con cualquier intención (también ``info``), pide servicio, día y
  hora, pasar a una persona y decir que el equipo escribirá para confirmar la
  hora. Nunca «no hay huecos», nunca una cita por hecha, nunca «tu cita» (el
  filtro del freno de citas);
- **casos límite**: si la lectura falla, el turno sigue con todas
  (``agenda.ready_read_failed``, solo el tipo del error); sin
  ``escalate.escalate_to_human``, una petición de cita la traspasa el runtime con
  ``agenda_not_ready``; el freno de citas no salta en un turno que pasó a una
  persona con la agenda sin terminar.

Ningún proveedor real ni ninguna base: los cargadores del grafo se sustituyen,
como en ``test_pipeline_booking_brake.py``.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from nexus_api.services.activations import ToolPolicy
from nexus_api.services.router_catalog import CatalogSnapshot
from nexus_mcp import MCPRegistry
from structlog.testing import capture_logs

import nexus_worker.runtime.pipeline as pipeline
from nexus_worker.runtime import booking_brake
from nexus_worker.runtime import dispatcher as dispatcher
from nexus_worker.runtime.agent_loader import AgentBundle
from nexus_worker.runtime.llm import CooldownBook, InMemoryProvider, LLMCall, LLMRouter, ToolCall
from nexus_worker.runtime.model_resolver import RouteDecision, RouteFacts
from nexus_worker.runtime.pipeline import (
    _AGENDA_NOT_READY_NOTE,
    _AGENDA_NOT_READY_NOTE_NO_HAND_OFF,
    _HAND_OFF_NOTE,
    _HANDOFF_RESPONSE,
    AGENDA_NOT_READY,
    _agenda_not_ready_note_applies,
    make_handler_node,
    without_unready_agenda,
)
from tests.unit._router_world import AGENT, TENANT, snapshot

pytestmark = pytest.mark.asyncio

#: The real loader, before ``conftest`` swaps it for «ready» in every unit test.
REAL_LOAD_AGENDA_READY = pipeline._load_agenda_ready

CONVERSATION = uuid.UUID("00000000-0000-0000-0000-00000000c057")
VERSION = uuid.UUID("00000000-0000-0000-0000-0000000005e7")
HAND_OFF = "escalate.escalate_to_human"

NEEDS_A_READY_AGENDA = (
    "reservas.find_slots",
    "reservas.create",
    "reservas.reschedule",
    "reservas.join_waitlist",
    "reservas.answer_offer",
)
WORKS_WITH_WHAT_THERE_IS = (
    "reservas.services",
    "reservas.list_mine",
    "reservas.cancel",
    "reservas.confirm_attendance",
)
AGENDA = NEEDS_A_READY_AGENDA + WORKS_WITH_WHAT_THERE_IS
WITH_HAND_OFF = frozenset({*AGENDA, HAND_OFF, "response.send_interactive"})
WITHOUT_HAND_OFF = frozenset({*AGENDA, "response.send_interactive"})

ASKS = "¿Qué servicio quieres y qué día y a qué hora te viene mejor?"
HANDED = "Te paso con el equipo y te escribirá para confirmar tu cita del martes."


# ── las piezas, sin grafo ───────────────────────────────────────────────────


def test_the_tools_that_need_a_finished_agenda_leave() -> None:
    names = (*AGENDA, HAND_OFF, "client.get_history")
    kept = without_unready_agenda(names)
    assert not set(kept) & set(NEEDS_A_READY_AGENDA)
    assert set(WORKS_WITH_WHAT_THERE_IS) <= set(kept)
    assert HAND_OFF in kept and "client.get_history" in kept
    assert list(kept) == [n for n in names if n in kept], "sin reordenar"


def test_the_note_applies_on_having_the_agenda_not_on_the_intent() -> None:
    assert _agenda_not_ready_note_applies(WITH_HAND_OFF, ready=False)
    assert _agenda_not_ready_note_applies(("reservas.services",), ready=False)
    assert not _agenda_not_ready_note_applies(WITH_HAND_OFF, ready=True)
    assert not _agenda_not_ready_note_applies(WITH_HAND_OFF, ready=None), "sin leer: falla abierta"
    assert not _agenda_not_ready_note_applies((HAND_OFF, "client.get_history"), ready=False)


@pytest.mark.parametrize("note", [_AGENDA_NOT_READY_NOTE, _AGENDA_NOT_READY_NOTE_NO_HAND_OFF])
def test_the_note_never_trips_the_booking_brake(note: str) -> None:
    folded = note.casefold()
    assert "tu cita" not in folded and "su cita" not in folded
    assert not booking_brake.might_claim(note), "si el modelo la copia, el freno no salta"
    assert "nunca" in folded and "huecos" in folded, "nunca dice que no hay huecos"


def test_the_note_asks_the_service_day_and_time_and_hands_over() -> None:
    folded = _AGENDA_NOT_READY_NOTE.casefold()
    assert HAND_OFF in _AGENDA_NOT_READY_NOTE
    assert "servicio" in folded and "día" in folded and "hora" in folded
    assert "el equipo le escribirá para confirmar la hora" in folded
    assert HAND_OFF not in _AGENDA_NOT_READY_NOTE_NO_HAND_OFF, "no pide una herramienta que no hay"


def test_the_reason_goes_to_the_inbox_and_silences_the_agent() -> None:
    assert AGENDA_NOT_READY == "agenda_not_ready"
    assert AGENDA_NOT_READY in dispatcher._ROUTER_REASONS
    assert AGENDA_NOT_READY in dispatcher._SILENCES_THE_AGENT


def test_a_hand_over_backs_the_reply_only_while_the_agenda_is_not_ready() -> None:
    escalated = {"tool": HAND_OFF, "status": "ok", "result": {"ok": True}}
    assert booking_brake.backs(escalated, agenda_pending=True)
    assert not booking_brake.backs(escalated), "con la agenda lista, pasar no es reservar"
    assert not booking_brake.backs({**escalated, "status": "error"}, agenda_pending=True)
    assert booking_brake.backs({**escalated, "status": "skipped:dry_run"}, agenda_pending=True)
    assert booking_brake.is_backed([escalated], agenda_pending=True)


# ── el mundo del grafo, sin base ───────────────────────────────────────────


@dataclass
class World:
    ready: bool | None = False
    reads: int = 0
    dispatched: list[str] = field(default_factory=list)
    envelope: Callable[[ToolCall], dict[str, Any]] | None = None
    records: list[dict[str, Any]] = field(default_factory=list)


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    w = World()

    async def catalog(*, force: bool = False) -> CatalogSnapshot:
        return snapshot([], [])

    async def facts(
        _tenant: uuid.UUID, _agent: uuid.UUID | None, *, partner_id: uuid.UUID | None = None
    ) -> RouteFacts:
        return RouteFacts(eu_only=True)

    async def anomaly(_decision: RouteDecision) -> None:
        return None

    async def nothing(*_a: Any, **_k: Any) -> Any:
        return ""

    async def no_knowledge(*_a: Any, **_k: Any) -> tuple[str, list[Any]]:
        return "", []

    async def no_gates(_tenant: uuid.UUID) -> frozenset[str]:
        return frozenset()

    async def open_policy(_tenant: uuid.UUID, _agent: uuid.UUID | None) -> ToolPolicy:
        return ToolPolicy()

    async def readiness(tenant_id: uuid.UUID) -> bool | None:
        assert tenant_id == TENANT, "solo el cliente del turno"
        w.reads += 1
        return w.ready

    async def dispatch(
        registry: MCPRegistry,
        call: ToolCall,
        available: tuple[str, ...],
        intent: str,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        w.dispatched.append(call.name)
        if call.name not in available:
            return {"tool": call.name, "intent": intent, "status": "skipped:not_in_whitelist"}
        if w.envelope is not None:
            return {"intent": intent, **w.envelope(call)}
        return {"tool": call.name, "intent": intent, "status": "ok", "result": {"ok": True}}

    async def conversation_backed(_tenant: uuid.UUID, _conversation: Any) -> bool:
        return False

    async def record(**kwargs: Any) -> None:
        w.records.append(kwargs)

    monkeypatch.setattr(pipeline, "get_catalog_snapshot", catalog)
    monkeypatch.setattr(pipeline, "load_route_facts", facts)
    monkeypatch.setattr(pipeline, "_record_router_anomaly", anomaly)
    monkeypatch.setattr(pipeline, "_load_kg_snapshot_text", nothing)
    monkeypatch.setattr(pipeline, "_load_knowledge", no_knowledge)
    monkeypatch.setattr(pipeline, "_load_gated_tools", no_gates)
    monkeypatch.setattr(pipeline, "_load_tool_policy", open_policy)
    monkeypatch.setattr(pipeline, "_load_agenda_ready", readiness)
    monkeypatch.setattr(pipeline, "_dispatch_tool", dispatch)
    monkeypatch.setattr(pipeline, "_now_note", lambda _tz: "Hoy es lunes, 10:00.")
    monkeypatch.setattr(booking_brake, "conversation_backed", conversation_backed)
    monkeypatch.setattr(booking_brake, "record_brake", record)
    yield w


class _Loader:
    def __init__(self, bundle: AgentBundle) -> None:
        self.bundle = bundle

    async def load(self, _tenant: uuid.UUID, _agent: uuid.UUID | None = None) -> AgentBundle:
        return self.bundle


class _Registry(MCPRegistry):
    """Las herramientas declaradas para que el modelo las vea; el despacho lo
    sustituye la prueba."""

    def get_openai_tools(self, names: Any) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {"name": n, "description": "x", "parameters": {"type": "object"}},
            }
            for n in names
        ]

    def is_side_effecting(self, name: str) -> bool:
        return False

    def names(self) -> tuple[str, ...]:
        # Every tool of these agents is the house's: none is a Composio proxy.
        return tuple(sorted({*WITH_HAND_OFF, "client.get_history"}))


def _bundle(tools: frozenset[str]) -> AgentBundle:
    return AgentBundle(
        tenant_id=TENANT,
        version=1,
        version_id=VERSION,
        system_prompt="Eres la recepción del spa. Das citas.",
        tools=tools,
        agent_id=AGENT,
    )


def _state(**over: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "tenant_id": str(TENANT),
        "agent_id": str(AGENT),
        "conversation_id": str(CONVERSATION),
        "inbound_message_id": "turn-1",
        "customer_id": str(uuid.uuid4()),
        "channel_type": "whatsapp",
        "user_message": "Quiero una cita para un masaje el martes por la tarde",
        "history": [],
        "classification": {},
        "router_turn": {},
    }
    state.update(over)
    return state


@dataclass
class Script:
    answer: str = ASKS
    tool: ToolCall | None = None
    verdict: str = "YES"


def _provider(script: Script) -> InMemoryProvider:
    provider = InMemoryProvider()

    def answered(call: LLMCall) -> bool:
        return bool(call.messages) and call.messages[-1].get("role") == "tool"

    def responder(call: LLMCall) -> str:
        if call.role == "classify":
            return script.verdict
        if script.tool is not None and not answered(call):
            return ""
        return script.answer

    def tool_caller(call: LLMCall) -> list[ToolCall]:
        if call.role == "classify" or script.tool is None or answered(call):
            return []
        return [script.tool]

    provider.responder = responder
    provider.tool_caller = tool_caller
    return provider


async def _turn(
    tools: frozenset[str], provider: InMemoryProvider, *, intent: str = "book"
) -> dict[str, Any]:
    llm = LLMRouter(
        provider=provider,
        classify_model="legacy/classify",
        respond_model="legacy/respond",
        fallback_model="legacy/fallback",
        cooldowns=CooldownBook(),
        retry_backoff_s=0.0,
    )
    handler = make_handler_node(intent, _Loader(_bundle(tools)), llm, _Registry())  # type: ignore[arg-type]
    out: dict[str, Any] = await handler(_state())  # type: ignore[arg-type]
    return out


def _handler_calls(provider: InMemoryProvider, intent: str = "book") -> list[LLMCall]:
    return [c for c in provider.calls if c.role == intent]


def _offered(call: LLMCall) -> set[str]:
    return {t["function"]["name"] for t in call.tools}


def _system(call: LLMCall) -> list[str]:
    return [str(m.get("content")) for m in call.messages if m.get("role") == "system"]


def _brake_checks(provider: InMemoryProvider) -> list[LLMCall]:
    return [
        c
        for c in provider.calls
        if c.role == "classify"
        and any(booking_brake.CLASSIFY_PROMPT in str(m.get("content")) for m in c.messages)
    ]


# ── las herramientas y la nota en el turno ─────────────────────────────────


async def test_an_unready_agenda_offers_only_what_works_and_the_note(world: World) -> None:
    provider = _provider(Script())

    with capture_logs() as logs:
        out = await _turn(WITH_HAND_OFF, provider)

    [call] = _handler_calls(provider)
    offered = _offered(call)
    assert not offered & set(NEEDS_A_READY_AGENDA), offered
    assert set(WORKS_WITH_WHAT_THERE_IS) | {HAND_OFF} <= offered
    assert _AGENDA_NOT_READY_NOTE in _system(call)
    assert _HAND_OFF_NOTE in _system(call)
    assert world.reads == 1, "una lectura por turno"
    assert out["response"] == ASKS and out["turn_failure"] is None
    [event] = [e for e in logs if e["event"] == "agenda.not_ready_turn"]
    assert event["tenant_id"] == str(TENANT) and event["agent_id"] == str(AGENT)
    assert event["intent"] == "book" and event["escalated"] is False
    assert ASKS not in str(event), "nunca el texto"


@pytest.mark.parametrize("intent", ["info", "fallback", "escalate"])
async def test_the_note_goes_with_any_intent(world: World, intent: str) -> None:
    """Una petición de cita clasificada ``info`` también tiene que pasar."""
    provider = _provider(Script())

    out = await _turn(WITH_HAND_OFF, provider, intent=intent)

    [call] = _handler_calls(provider, intent)
    assert _AGENDA_NOT_READY_NOTE in _system(call)
    assert not _offered(call) & set(NEEDS_A_READY_AGENDA)
    assert out["turn_failure"] is None


async def test_a_ready_agenda_changes_nothing(world: World) -> None:
    world.ready = True
    provider = _provider(Script())

    with capture_logs() as logs:
        await _turn(WITH_HAND_OFF, provider)

    [call] = _handler_calls(provider)
    assert set(AGENDA) <= _offered(call)
    assert not any("AGENDA SIN TERMINAR" in s for s in _system(call))
    assert not [e for e in logs if e["event"] == "agenda.not_ready_turn"]


async def test_an_agent_without_the_agenda_reads_nothing(world: World) -> None:
    provider = _provider(Script())

    await _turn(frozenset({HAND_OFF, "client.get_history"}), provider)

    assert world.reads == 0, "sin reservas.* no se pregunta por la agenda"
    [call] = _handler_calls(provider)
    assert not any("AGENDA SIN TERMINAR" in s for s in _system(call))


async def test_an_invented_booking_is_refused_by_the_whitelist(world: World) -> None:
    """El modelo inventa ``reservas.create``: la tupla del turno es la lista blanca."""
    provider = _provider(
        Script(tool=ToolCall(id="x1", name="reservas.create", arguments={"date": "2026-11-10"}))
    )

    out = await _turn(WITH_HAND_OFF, provider)

    assert world.dispatched == ["reservas.create"]
    assert [e["status"] for e in out["tool_calls"]] == ["skipped:not_in_whitelist"]


# ── casos límite ───────────────────────────────────────────────────────────


async def test_a_read_that_fails_keeps_every_tool(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Falla abierta: el servidor de Reservas ya rechaza lo imposible."""

    def broken() -> Any:
        raise ConnectionRefusedError("postgres://secret@db/nexus")

    monkeypatch.setattr(pipeline, "_load_agenda_ready", REAL_LOAD_AGENDA_READY)
    monkeypatch.setattr(pipeline, "get_sessionmaker", broken)
    provider = _provider(Script())

    with capture_logs() as logs:
        out = await _turn(WITH_HAND_OFF, provider)

    [call] = _handler_calls(provider)
    assert set(AGENDA) <= _offered(call)
    assert not any("AGENDA SIN TERMINAR" in s for s in _system(call))
    assert out["turn_failure"] is None
    [event] = [e for e in logs if e["event"] == "agenda.ready_read_failed"]
    assert event["tenant_id"] == str(TENANT)
    assert event["error"] == "ConnectionRefusedError", "solo el tipo"
    assert "secret" not in str(event)


async def test_without_the_hand_off_tool_the_runtime_hands_over(world: World) -> None:
    provider = _provider(Script())

    with capture_logs() as logs:
        out = await _turn(WITHOUT_HAND_OFF, provider)

    assert not _handler_calls(provider), "nada que pueda decir el modelo cambia esto"
    assert out["response"] == _HANDOFF_RESPONSE
    assert out["turn_failure"] == {"kind": "handoff", "reason": AGENDA_NOT_READY, "detail": None}
    assert out["interactive_payload"] == {}
    [event] = [e for e in logs if e["event"] == "agenda.not_ready_turn"]
    assert event["escalated"] is True


async def test_without_the_hand_off_tool_other_intents_answer(world: World) -> None:
    """Solo una petición de cita se traspasa; lo demás lo contesta el agente."""
    provider = _provider(Script(answer="Abrimos de 10 a 20."))

    out = await _turn(WITHOUT_HAND_OFF, provider, intent="info")

    [call] = _handler_calls(provider, "info")
    assert _AGENDA_NOT_READY_NOTE_NO_HAND_OFF in _system(call)
    assert _AGENDA_NOT_READY_NOTE not in _system(call)
    assert out["response"] == "Abrimos de 10 a 20." and out["turn_failure"] is None


async def test_the_brake_does_not_fire_on_a_hand_over(world: World) -> None:
    """«…para confirmar tu cita» pasa el filtro del freno; con la agenda sin
    terminar y la conversación pasada a una persona, no es una cita inventada."""
    provider = _provider(
        Script(
            answer=HANDED,
            tool=ToolCall(id="e1", name=HAND_OFF, arguments={"reason": "Masaje, martes, 17:00"}),
        )
    )
    assert booking_brake.might_claim(HANDED)

    with capture_logs() as logs:
        out = await _turn(WITH_HAND_OFF, provider)

    assert world.dispatched == [HAND_OFF]
    assert out["response"] == HANDED and out["turn_failure"] is None
    assert not _brake_checks(provider), "ni se pregunta al clasificador"
    assert not world.records
    [event] = [e for e in logs if e["event"] == "agenda.not_ready_turn"]
    assert event["escalated"] is True


async def test_with_a_ready_agenda_a_hand_over_does_not_back_a_claim(world: World) -> None:
    world.ready = True
    provider = _provider(
        Script(
            answer=HANDED,
            tool=ToolCall(id="e1", name=HAND_OFF, arguments={"reason": "Masaje"}),
        )
    )

    await _turn(WITH_HAND_OFF, provider)

    assert _brake_checks(provider), "con la agenda lista el freno mira como siempre"


# ── el freno de la reescritura del revisor (spec 056, T017) ────────────────


class _ToolsLoader:
    def __init__(self, tools: tuple[str, ...]) -> None:
        self.tools = tools

    async def load(self, tenant_id: Any, agent_id: Any) -> Any:
        from types import SimpleNamespace

        return SimpleNamespace(tools=self.tools, agent_id=agent_id)


@pytest.mark.parametrize(("ready", "pending"), [(False, True), (True, False)])
async def test_the_grader_rewrite_brake_knows_whether_the_agenda_is_ready(
    monkeypatch: pytest.MonkeyPatch, ready: bool, pending: bool
) -> None:
    """La reescritura del revisor pasa por el mismo freno: con la agenda sin terminar,
    pasar la cita a una persona respalda la respuesta igual que en el manejador."""
    seen: dict[str, Any] = {}

    async def _claim(*_args: Any, agenda_pending: bool = False, **_kw: Any) -> bool:
        seen["agenda_pending"] = agenda_pending
        return False

    async def _ready(_tenant_id: Any) -> bool:
        return ready

    monkeypatch.setattr(booking_brake, "unbacked_claim", _claim)
    monkeypatch.setattr(pipeline, "_load_agenda_ready", _ready)
    state: Any = {
        "tenant_id": str(TENANT),
        "agent_id": str(AGENT),
        "tool_calls": [],
        "conversation_id": None,
        "inbound_message_id": None,
    }
    loader: Any = _ToolsLoader(("reservas.create", HAND_OFF))
    claimed = await pipeline._rewrite_claims_a_booking(
        state, "Te paso con el equipo para confirmar la hora.", llm=object(), loader=loader
    )
    assert claimed is False
    assert seen["agenda_pending"] is pending
