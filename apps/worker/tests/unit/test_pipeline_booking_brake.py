"""El freno de citas dentro del manejador (spec 056, T013 · requisitos 1.1, 1.2 y 1.4).

Una respuesta que da por hecha una cita sin una reserva detrás no sale así:

- **primer intento**: el bucle ReAct vuelve a correr con la nota del freno
  (``BOOKING_BRAKE_NOTE``) como ``system`` y sin el borrador (constitución §III:
  el último mensaje sigue siendo del cliente), con sus herramientas, dentro del
  mismo manejador;
- **segundo intento** que vuelve a afirmarla: la conversación pasa a una persona,
  ``turn_failure.reason == "booking_unbacked"``, con la frase de traspaso y sin
  componente interactivo;
- una reserva hecha en el turno respalda la respuesta **sin ninguna llamada** de
  clasificación (escenario 3 de la historia 1);
- si el clasificador falla, cuenta como afirmación (falla cerrado);
- se mira también el componente interactivo y el borrador que reescribe el
  revisor de resultados;
- vale igual para un agente de hoy (legado, camino de hoy) y para uno
  estructurado que va por el router.

Ningún proveedor real (``InMemoryProvider``) y ninguna base: los cargadores del
grafo y la lectura de la conversación se sustituyen, como en
``test_pipeline_router.py``.
"""

from __future__ import annotations

import json
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
from nexus_worker.guardrails import GRADER_FALLBACK_RESPONSE
from nexus_worker.runtime import booking_brake
from nexus_worker.runtime.agent_loader import AgentBundle
from nexus_worker.runtime.llm import CooldownBook, InMemoryProvider, LLMCall, LLMRouter, ToolCall
from nexus_worker.runtime.model_resolver import RouteDecision, RouteFacts
from nexus_worker.runtime.pipeline import (
    _HANDOFF_RESPONSE,
    make_classify_node,
    make_grade_outcome_node,
    make_handler_node,
)
from tests.unit._router_world import AGENT, TENANT, cert, dep, profile, snapshot

CONVERSATION = uuid.UUID("00000000-0000-0000-0000-00000000b0b0")
VERSION = uuid.UUID("00000000-0000-0000-0000-0000000000e1")

CLAIM = "¡Listo! Tu cita queda confirmada para el viernes a las 10."
CLAIM_AGAIN = "Tu cita del viernes a las 10 está confirmada. Te esperamos."
HONEST = "No he podido reservarla: ese día no tenemos horario. ¿Te paso con el equipo?"
BRIEF = {"id": "7f0c", "date": "2026-11-13", "start": "10:00", "end": "10:30"}

TINY = dep("eu-t/tiny", provider="prov_t", family="openai-gpt-oss", price_in="0.02")
HAIKU = dep("eu-a/haiku", provider="prov_a", price_in="1", price_out="5")


def _catalog() -> CatalogSnapshot:
    certs = [cert(HAIKU, "answer"), cert(HAIKU, "tool_turn"), cert(TINY, "classify")]
    return snapshot([TINY, HAIKU], certs, profile())


# ── el mundo del grafo, sin base ───────────────────────────────────────────


@dataclass
class World:
    history_backed: bool = False
    history_reads: int = 0
    dispatched: list[ToolCall] = field(default_factory=list)
    envelope: Callable[[ToolCall], dict[str, Any]] | None = None
    records: list[dict[str, Any]] = field(default_factory=list)


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    w = World()

    async def catalog(*, force: bool = False) -> CatalogSnapshot:
        return _catalog()

    async def facts(
        _tenant: uuid.UUID, _agent: uuid.UUID | None, *, partner_id: uuid.UUID | None = None
    ) -> RouteFacts:
        return RouteFacts(eu_only=True, agent_certified=frozenset({HAIKU.key}))

    async def anomaly(_decision: RouteDecision) -> None:
        return None

    async def nothing(*_a: Any, **_k: Any) -> Any:
        return ""

    async def no_history(*_a: Any, **_k: Any) -> list[dict[str, str]]:
        return []

    async def no_knowledge(*_a: Any, **_k: Any) -> tuple[str, list[Any]]:
        return "", []

    async def no_gates(_tenant: uuid.UUID) -> frozenset[str]:
        return frozenset()

    async def open_policy(_tenant: uuid.UUID, _agent: uuid.UUID | None) -> ToolPolicy:
        return ToolPolicy()

    async def no_read_only(*_a: Any, **_k: Any) -> frozenset[str]:
        return frozenset()

    async def dispatch(
        _registry: MCPRegistry,
        call: ToolCall,
        _available: tuple[str, ...],
        intent: str,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        w.dispatched.append(call)
        if w.envelope is not None:
            return {"intent": intent, **w.envelope(call)}
        return {"tool": call.name, "intent": intent, "status": "ok", "result": {}}

    async def conversation_backed(
        _tenant: uuid.UUID, conversation_id: str | uuid.UUID | None
    ) -> bool:
        w.history_reads += 1
        assert str(conversation_id) == str(CONVERSATION), "solo la conversación del turno"
        return w.history_backed

    async def record(**kwargs: Any) -> None:
        w.records.append(kwargs)

    monkeypatch.setattr(pipeline, "get_catalog_snapshot", catalog)
    monkeypatch.setattr(pipeline, "load_route_facts", facts)
    monkeypatch.setattr(pipeline, "_record_router_anomaly", anomaly)
    monkeypatch.setattr(pipeline, "_load_recent_history", no_history)
    monkeypatch.setattr(pipeline, "_load_kg_snapshot_text", nothing)
    monkeypatch.setattr(pipeline, "_load_knowledge", no_knowledge)
    monkeypatch.setattr(pipeline, "_load_gated_tools", no_gates)
    monkeypatch.setattr(pipeline, "_load_tool_policy", open_policy)
    monkeypatch.setattr(pipeline, "load_read_only_tools", no_read_only)
    monkeypatch.setattr(pipeline, "_dispatch_tool", dispatch)
    monkeypatch.setattr(pipeline, "_now_note", lambda _tz: "Hoy es sábado, 10:00.")
    monkeypatch.setattr(booking_brake, "conversation_backed", conversation_backed)
    monkeypatch.setattr(booking_brake, "record_brake", record)
    yield w


class _Loader:
    def __init__(self, bundle: AgentBundle) -> None:
        self.bundle = bundle

    async def load(self, _tenant: uuid.UUID, _agent: uuid.UUID | None = None) -> AgentBundle:
        return self.bundle


TOOLS = frozenset({"reservas.find_slots", "reservas.create", "response.send_interactive"})


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
        return tuple(sorted(TOOLS))


LEGACY = "legado"
STRUCTURED = "estructurado"


def _bundle(kind: str) -> AgentBundle:
    """Un agente de hoy, con un prompt libre y el camino de hoy, o uno
    estructurado (prompt compilado) que va por el router. Ninguno dice nada de
    confirmar citas: el freno no depende del prompt (requisito 1.4)."""
    if kind == LEGACY:
        return AgentBundle(
            tenant_id=TENANT,
            version=1,
            version_id=VERSION,
            system_prompt="Eres la recepción de la barbería.",
            tools=TOOLS,
            agent_id=AGENT,
        )
    return AgentBundle(
        tenant_id=TENANT,
        version=3,
        version_id=VERSION,
        system_prompt="# Quién eres\nRecepción de la barbería.\n# Qué haces\nReservas citas.",
        tools=TOOLS,
        policies={"model_policy": {"kind": "profile", "profile": "auto"}},
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
        "user_message": "Quiero una cita el viernes a las 10",
        "history": [],
        "classification": {},
        "router_turn": {},
    }
    state.update(over)
    return state


_CLASSIFIED = {
    "intent": "book",
    "needs_tools": True,
    "risk": "low",
    "complexity": "low",
    "language": "es",
    "intents": 1,
}


def _is_brake_check(call: LLMCall) -> bool:
    return call.role == "classify" and any(
        m.get("role") == "system" and booking_brake.CLASSIFY_PROMPT in str(m.get("content"))
        for m in call.messages
    )


def _is_handler(call: LLMCall) -> bool:
    return call.role == "book"


@dataclass
class Script:
    """Lo que contesta el modelo: un borrador por intento del manejador, el
    veredicto del freno y, si se pide, una herramienta en la primera llamada."""

    drafts: list[str]
    verdict: str = "YES"
    first_tool: ToolCall | None = None
    handler_calls: int = 0


def _provider(script: Script) -> InMemoryProvider:
    provider = InMemoryProvider()

    def responder(call: LLMCall) -> str:
        if call.extra.get("task") == "classify":
            return json.dumps(_CLASSIFIED)
        if _is_brake_check(call):
            return script.verdict
        if call.role == "classify":
            return "book"
        if _is_handler(call):
            if script.first_tool is not None and call.messages[-1].get("role") != "tool":
                return ""
            # One draft per attempt: the brake's note marks the second one.
            retried = any(
                booking_brake.BOOKING_BRAKE_NOTE in str(m.get("content")) for m in call.messages
            )
            return script.drafts[1 if retried else 0]
        return "ok"

    def tool_caller(call: LLMCall) -> list[ToolCall]:
        if not _is_handler(call) or script.first_tool is None:
            return []
        if call.messages and call.messages[-1].get("role") == "tool":
            return []  # the tool answered: now the text
        return [script.first_tool]  # first call of each attempt

    provider.responder = responder
    provider.tool_caller = tool_caller
    return provider


def _router(provider: InMemoryProvider) -> LLMRouter:
    return LLMRouter(
        provider=provider,
        classify_model="legacy/classify",
        respond_model="legacy/respond",
        fallback_model="legacy/fallback",
        cooldowns=CooldownBook(),
        retry_backoff_s=0.0,
    )


async def _turn(bundle: AgentBundle, provider: InMemoryProvider) -> dict[str, Any]:
    llm = _router(provider)
    loader = _Loader(bundle)
    current = _state()
    classified = await make_classify_node(loader, llm)(current)  # type: ignore[arg-type]
    current = {**current, **classified}
    assert current["intent"] == "book"
    handler = make_handler_node("book", loader, llm, _Registry())  # type: ignore[arg-type]
    out = await handler(current)  # type: ignore[arg-type]
    return {**current, **out}


def _handler_calls(provider: InMemoryProvider) -> list[LLMCall]:
    return [c for c in provider.calls if _is_handler(c)]


def _brake_checks(provider: InMemoryProvider) -> list[LLMCall]:
    return [c for c in provider.calls if _is_brake_check(c)]


def _has_note(call: LLMCall) -> bool:
    return any(booking_brake.BOOKING_BRAKE_NOTE in str(m.get("content")) for m in call.messages)


KINDS = pytest.mark.parametrize("kind", [LEGACY, STRUCTURED])


# ── un intento más con la nota ─────────────────────────────────────────────


@KINDS
async def test_an_unbacked_claim_is_retried_with_the_brake_note(world: World, kind: str) -> None:
    provider = _provider(Script(drafts=[CLAIM, HONEST]))

    out = await _turn(_bundle(kind), provider)

    first, second = _handler_calls(provider)
    assert not _has_note(first)
    assert _has_note(second), "el segundo intento lleva la nota del freno"
    assert second.messages[-1] == {"role": "system", "content": booking_brake.BOOKING_BRAKE_NOTE}
    assert not any(CLAIM in str(m.get("content")) for m in second.messages), (
        "sin el borrador: como assistant, el hilo acabaría en él"
    )
    [*_, last_turn] = [m for m in second.messages if m.get("role") != "system"]
    assert last_turn == {"role": "user", "content": _state()["user_message"]}, (
        "el último mensaje del hilo sigue siendo el del cliente"
    )
    assert not any(
        m.get("role") == "user" and booking_brake.BOOKING_BRAKE_NOTE in str(m.get("content"))
        for m in second.messages
    ), "la nota nunca va con forma de cliente"
    assert second.tools, "el reintento puede reservar: lleva sus herramientas"
    assert out["response"] == HONEST
    assert out["turn_failure"] is None
    assert len(_brake_checks(provider)) == 1, "la respuesta sincera no pasa el filtro"
    [check] = _brake_checks(provider)
    assert check.messages[-1] == {"role": "user", "content": CLAIM}, "el borrador va como dato"
    assert [r["outcome"] for r in world.records] == ["retried"]
    assert world.history_reads == 1


@KINDS
async def test_two_claims_hand_the_conversation_to_a_person(world: World, kind: str) -> None:
    provider = _provider(Script(drafts=[CLAIM, CLAIM_AGAIN]))

    out = await _turn(_bundle(kind), provider)

    assert len(_handler_calls(provider)) == 2, "un solo reintento"
    assert out["response"] == _HANDOFF_RESPONSE
    assert out["turn_failure"] == {"kind": "handoff", "reason": "booking_unbacked", "detail": None}
    assert out["interactive_payload"] == {}
    assert len(_brake_checks(provider)) == 2
    assert [r["outcome"] for r in world.records] == ["handed_off"]
    record = world.records[0]
    assert record["agent_id"] == AGENT
    assert str(record["conversation_id"]) == str(CONVERSATION)
    assert CLAIM not in json.dumps(record, default=str), "sin el texto del mensaje"


@KINDS
async def test_a_booking_made_in_the_turn_costs_no_classifier_call(world: World, kind: str) -> None:
    world.envelope = lambda call: {
        "tool": call.name,
        "status": "ok",
        "result": {"booking": BRIEF, "refused": None, "idempotent_replay": False},
    }
    script = Script(
        drafts=[CLAIM, CLAIM_AGAIN],
        first_tool=ToolCall(id="t1", name="reservas.create", arguments={"date": "2026-11-13"}),
    )
    provider = _provider(script)

    out = await _turn(_bundle(kind), provider)

    assert [c.name for c in world.dispatched] == ["reservas.create"]
    assert out["response"] == CLAIM, "sale sin cambios"
    assert out["turn_failure"] is None
    assert not _brake_checks(provider), "con la reserva hecha no se pregunta a nadie"
    assert world.history_reads == 0, "ni se lee la conversación"
    assert not world.records


@KINDS
async def test_a_refused_booking_with_status_ok_does_not_back_the_claim(
    world: World, kind: str
) -> None:
    """``reservas.create`` contesta ``ok`` también al rechazar (``hours_missing``)."""
    world.envelope = lambda call: {
        "tool": call.name,
        "status": "ok",
        "result": {"booking": None, "refused": "hours_missing", "first_fit": None},
    }
    world.history_backed = True  # una reserva de antes no cubre la que acaba de fallar
    script = Script(
        drafts=[CLAIM, CLAIM_AGAIN],
        first_tool=ToolCall(id="t1", name="reservas.create", arguments={"date": "2026-11-13"}),
    )
    provider = _provider(script)

    out = await _turn(_bundle(kind), provider)

    assert out["turn_failure"] == {"kind": "handoff", "reason": "booking_unbacked", "detail": None}
    checks = _brake_checks(provider)
    assert checks and all(booking_brake.ONLY_NEW_PROMPT in str(c.messages[0]) for c in checks), (
        "con una reserva de antes, solo cuenta dar por hecha una nueva"
    )


@KINDS
async def test_a_live_booking_of_this_conversation_backs_the_reply(world: World, kind: str) -> None:
    world.history_backed = True
    provider = _provider(Script(drafts=["Tu cita del lunes sigue en pie.", CLAIM_AGAIN]))

    out = await _turn(_bundle(kind), provider)

    assert out["response"] == "Tu cita del lunes sigue en pie."
    assert not _brake_checks(provider)
    assert world.history_reads == 1
    assert len(_handler_calls(provider)) == 1


@KINDS
async def test_a_classifier_that_fails_counts_as_a_claim(world: World, kind: str) -> None:
    provider = _provider(Script(drafts=[CLAIM, CLAIM_AGAIN], verdict=""))

    with capture_logs() as logs:
        out = await _turn(_bundle(kind), provider)

    assert out["turn_failure"] == {"kind": "handoff", "reason": "booking_unbacked", "detail": None}
    brake = [e for e in logs if e["event"] == "booking.brake"]
    assert any(e["outcome"] == "classifier_failed_closed" for e in brake), brake
    for e in brake:
        assert e["tenant_id"] == str(TENANT)
        assert "result" not in e and "text" not in e


@KINDS
async def test_a_classifier_that_says_no_lets_the_reply_through(world: World, kind: str) -> None:
    """El filtro es barato y amplio («tu cita» también sale en una pregunta)."""
    question = "¿Para qué hora quieres tu cita?"
    provider = _provider(Script(drafts=[question, CLAIM], verdict="NO"))

    out = await _turn(_bundle(kind), provider)

    assert out["response"] == question
    assert len(_brake_checks(provider)) == 1
    assert len(_handler_calls(provider)) == 1
    assert not world.records


# ── el componente interactivo ──────────────────────────────────────────────


@KINDS
async def test_an_interactive_reply_is_checked_and_dropped_on_handoff(
    world: World, kind: str
) -> None:
    interactive = {
        "body": "Elige cómo seguimos",
        "buttons": [{"id": "ok", "title": "Cita confirmada"}, {"id": "x", "title": "Cambiarla"}],
    }
    world.envelope = lambda call: {"tool": call.name, "status": "ok", "result": {"sent": True}}
    script = Script(
        drafts=["", ""],
        first_tool=ToolCall(id="i1", name="response.send_interactive", arguments=interactive),
    )
    provider = _provider(script)

    out = await _turn(_bundle(kind), provider)

    assert out["turn_failure"] == {"kind": "handoff", "reason": "booking_unbacked", "detail": None}
    assert out["interactive_payload"] == {}, "sin componente interactivo"
    assert out["response"] == _HANDOFF_RESPONSE
    [first, *_] = _brake_checks(provider)
    assert "Cita confirmada" in first.messages[-1]["content"]


# ── el borrador que reescribe el revisor ───────────────────────────────────


@dataclass
class _Verdict:
    overall: str
    feedback: str = ""


class _Grader:
    """Suspende el borrador una vez y aprueba el siguiente."""

    def __init__(self) -> None:
        self.verdicts = [_Verdict("fail", "Sé más concreto"), _Verdict("pass")]

    async def grade(self, **_kw: Any) -> _Verdict:
        return self.verdicts.pop(0)


async def test_the_grader_rewrite_is_checked_again(world: World) -> None:
    provider = InMemoryProvider()
    provider.responder = lambda c: (
        "YES" if _is_brake_check(c) else "Listo, te he reservado el viernes."
    )
    node = make_grade_outcome_node(
        grader=_Grader(),  # type: ignore[arg-type]
        llm_router=_router(provider),
        agent_loader=_Loader(_bundle(LEGACY)),  # type: ignore[arg-type]
    )
    state = _state(
        intent="book",
        response="¿Qué hora te viene bien el viernes?",
        tool_calls=[],
        interactive_payload={},
        agent_runtime_flags={"outcome_grader": True, "grader_mode": "sync"},
    )

    out = await node(state)  # type: ignore[arg-type]

    assert out["response"] == GRADER_FALLBACK_RESPONSE
    assert len(_brake_checks(provider)) == 1
    assert [r["outcome"] for r in world.records] == ["grader_fallback"]


async def test_a_grader_rewrite_without_a_claim_passes(world: World) -> None:
    provider = InMemoryProvider()
    provider.responder = lambda c: "¿A qué hora te viene bien el viernes?"
    node = make_grade_outcome_node(
        grader=_Grader(),  # type: ignore[arg-type]
        llm_router=_router(provider),
        agent_loader=_Loader(_bundle(LEGACY)),  # type: ignore[arg-type]
    )
    state = _state(
        intent="book",
        response="Dime la hora.",
        tool_calls=[],
        agent_runtime_flags={"outcome_grader": True, "grader_mode": "sync"},
    )

    out = await node(state)  # type: ignore[arg-type]

    assert out["response"] == "¿A qué hora te viene bien el viernes?"
    assert out["outcome_overall"] == "pass"
    assert not _brake_checks(provider)
