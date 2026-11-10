"""El router dentro del grafo (spec 047, T140 · requisitos 40.3, 40.4, 40.5,
40.7, 40.9 y 40.10; historia 13).

``pipeline.py`` es quien llama al clasificador tipado, lee las señales del grafo,
pide la subllamada de escalado y escribe la afinidad en el estado del hilo, sobre
la API de ``model_resolver``. Dos mundos:

- **un agente de hoy** (su versión no tiene ``model_policy``): sigue fijado en su
  modelo de hoy por el camino de hoy. La primera prueba lo demuestra comparando,
  llamada a llamada, lo que recibe el proveedor con el router inalcanzable, con el
  catálogo de hoy (ninguna retención cero comprobada, research D44) y con un
  catálogo que sí sirve: es idéntico. Solo su clasificador se mueve, y solo a un
  despliegue certificado para ``classify`` (D24, T145);
- **un agente con perfil o con modelo fijado**: cada llamada de conversación, el
  clasificador y el escalado van por ``chain_for``.

Ningún proveedor real: ``InMemoryProvider`` y el catálogo de mentira de
``_router_world``. Ninguna base: los cargadores del grafo se sustituyen.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from nexus_api.services.router_catalog import CatalogSnapshot
from nexus_mcp import MCPRegistry
from nexus_mcp.base import ToolError
from pydantic import BaseModel, ValidationError
from structlog.testing import capture_logs

import nexus_worker.runtime.pipeline as pipeline
from nexus_worker.runtime.agent_loader import AgentBundle
from nexus_worker.runtime.llm import (
    ROUTE_DECISION_EVENT,
    CooldownBook,
    InMemoryProvider,
    LLMCall,
    LLMRouter,
    ToolCall,
)
from nexus_worker.runtime.model_resolver import (
    ESCALATION_WINDOW_S,
    PinnedModel,
    RouteDecision,
    RouteFacts,
    pins_from_state,
    with_pin,
)
from nexus_worker.runtime.pipeline import (
    _HANDOFF_RESPONSE,
    _dispatch_tool,
    make_classify_node,
    make_handler_node,
)
from tests.unit._router_world import AGENT, SIBLING, TENANT, cert, dep, profile, snapshot

CONVERSATION = uuid.UUID("00000000-0000-0000-0000-00000000c0c0")
VERSION = uuid.UUID("00000000-0000-0000-0000-0000000000e1")
NEW_VERSION = uuid.UUID("00000000-0000-0000-0000-0000000000f2")
TOOL = "client.get_history"

# Un despliegue barato para clasificar, dos básicos de conversación en dos
# proveedores y dos medianos para escalar. Todos en la UE, con retención cero.
TINY = dep(
    "eu-t/tiny", provider="prov_t", family="openai-gpt-oss", price_in="0.02", price_out="0.1"
)
HAIKU_A = dep("eu-a/haiku", provider="prov_a", price_in="1", price_out="5")
HAIKU_B = dep("eu-b/haiku", provider="prov_b", price_in="1.1", price_out="5.5")
SONNET_A = dep(
    "eu-a/sonnet", provider="prov_a", price_in="3", price_out="15", caps={"tier": "medium"}
)
SONNET_B = dep(
    "eu-b/sonnet", provider="prov_b", price_in="3.3", price_out="16.5", caps={"tier": "medium"}
)
CONVERSATION_TASKS = ("answer", "tool_turn")


def _economy() -> Any:
    """«Económico» del contrato, sin gama a la que escalar."""
    return profile(
        "economy",
        tool_turn={"escalate_to": None},
        answer={"escalate_to": None},
    )


def servable(*, classify: bool = True) -> CatalogSnapshot:
    deployments = [TINY, HAIKU_A, HAIKU_B, SONNET_A, SONNET_B]
    certs = [cert(d, t) for d in (HAIKU_A, HAIKU_B) for t in CONVERSATION_TASKS]
    certs += [cert(SONNET_A, "escalate"), cert(SONNET_B, "escalate")]
    if classify:
        certs += [cert(TINY, "classify"), cert(HAIKU_A, "classify")]
    return snapshot(deployments, certs, profile(), _economy())


def todays_catalog() -> CatalogSnapshot:
    """Research D44: las filas de hoy, sin retención cero comprobada."""
    rows = [
        dep(d.key, provider=d.provider, zero_retention=False, caps=d.capabilities.to_contract())
        for d in (TINY, HAIKU_A, HAIKU_B, SONNET_A, SONNET_B)
    ]
    certs = [cert(d, t) for d in rows for t in ("classify", *CONVERSATION_TASKS)]
    return snapshot(rows, certs, profile(), _economy())


# ── el mundo del grafo, sin base ───────────────────────────────────────────


@dataclass
class World:
    catalog: CatalogSnapshot | None
    facts: RouteFacts = field(
        default_factory=lambda: RouteFacts(
            eu_only=True, agent_certified=frozenset({HAIKU_A.key, HAIKU_B.key})
        )
    )
    facts_reads: int = 0
    anomalies: list[RouteDecision] = field(default_factory=list)
    dispatched: list[ToolCall] = field(default_factory=list)
    envelope: Callable[[ToolCall], dict[str, Any]] | None = None


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    w = World(catalog=servable())

    async def catalog(*, force: bool = False) -> CatalogSnapshot:
        if w.catalog is None:
            raise ConnectionError("catálogo inalcanzable")
        return w.catalog

    async def facts(
        _tenant: uuid.UUID, _agent: uuid.UUID | None, *, partner_id: uuid.UUID | None = None
    ) -> RouteFacts:
        w.facts_reads += 1
        return w.facts

    async def anomaly(decision: RouteDecision) -> None:
        if decision.anomaly:
            w.anomalies.append(decision)

    async def nothing(*_a: Any, **_k: Any) -> Any:
        return ""

    async def no_history(*_a: Any, **_k: Any) -> list[dict[str, str]]:
        return []

    async def no_gates(_tenant: uuid.UUID) -> frozenset[str]:
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
            return w.envelope(call)
        return {"tool": call.name, "intent": intent, "status": "ok", "result": {"visits": 2}}

    monkeypatch.setattr(pipeline, "get_catalog_snapshot", catalog)
    monkeypatch.setattr(pipeline, "load_route_facts", facts)
    monkeypatch.setattr(pipeline, "_record_router_anomaly", anomaly)
    monkeypatch.setattr(pipeline, "_load_recent_history", no_history)
    monkeypatch.setattr(pipeline, "_load_kg_snapshot_text", nothing)

    async def no_knowledge(*_a: Any, **_k: Any) -> tuple[str, list[Any]]:
        return "", []

    monkeypatch.setattr(pipeline, "_load_knowledge", no_knowledge)
    monkeypatch.setattr(pipeline, "_load_gated_tools", no_gates)
    monkeypatch.setattr(pipeline, "_dispatch_tool", dispatch)
    # La hora del turno va en el prompt: fija, para comparar dos turnos byte a byte.
    monkeypatch.setattr(pipeline, "_now_note", lambda _tz: "Hoy es sábado, 10:00.")
    yield w


class _Loader:
    def __init__(self, bundle: AgentBundle) -> None:
        self.bundle = bundle

    async def load(self, _tenant: uuid.UUID, _agent: uuid.UUID | None = None) -> AgentBundle:
        return self.bundle


class _Tool(BaseModel):
    pass


class _Registry(MCPRegistry):
    """Un registro con una herramienta de lectura declarada, para que el modelo
    la vea; el despacho lo sustituye la prueba."""

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
        return (TOOL,)


def _bundle(
    model_policy: dict[str, Any] | None = None,
    *,
    tools: frozenset[str] = frozenset(),
    version: uuid.UUID = VERSION,
    llm_policy: dict[str, Any] | None = None,
) -> AgentBundle:
    policies: dict[str, Any] = {}
    if model_policy is not None:
        policies["model_policy"] = model_policy
    if llm_policy is not None:
        policies["llm"] = llm_policy
    return AgentBundle(
        tenant_id=TENANT,
        version=1,
        version_id=version,
        system_prompt="PROMPT-DEL-AGENTE",
        tools=tools,
        policies=policies,
        agent_id=AGENT,
    )


AUTO = {"kind": "profile", "profile": "auto"}
ECONOMY = {"kind": "profile", "profile": "economy"}


def _state(**over: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "tenant_id": str(TENANT),
        "agent_id": str(AGENT),
        "conversation_id": str(CONVERSATION),
        "inbound_message_id": "turn-1",
        "customer_id": str(uuid.uuid4()),
        "channel_type": "whatsapp",
        "user_message": "¿A qué hora abren el sábado?",
        "history": [],
        "intent": "info",
        "classification": {},
        "router_turn": {},
    }
    state.update(over)
    return state


_CLASSIFIED = {
    "intent": "info",
    "needs_tools": False,
    "risk": "low",
    "complexity": "low",
    "language": "es",
    "intents": 1,
}


def _provider(
    *,
    tool_first: bool = False,
    down: frozenset[str] = frozenset(),
    escalation: dict[str, Any] | None = None,
) -> InMemoryProvider:
    """Responde como un modelo: JSON al clasificador tipado y al escalado, la
    etiqueta al clasificador de hoy, y texto (o una herramienta) al turno."""
    provider = InMemoryProvider()

    def responder(call: LLMCall) -> str:
        task = call.extra.get("task")
        if task == "classify":
            return json.dumps(_CLASSIFIED)
        if task == "escalate":
            return json.dumps(escalation or {"guidance": "Pide la fecha exacta.", "handoff": False})
        if call.role == "classify":
            return "info"
        return "Abrimos de 10 a 14."

    def tool_caller(call: LLMCall) -> list[ToolCall]:
        if not tool_first or call.extra.get("tool_choice") == "none":
            return []
        if any(m.get("role") == "tool" for m in call.messages):
            return []
        return [ToolCall(id="t1", name=TOOL, arguments={"x": 1})]

    provider.responder = responder
    provider.tool_caller = tool_caller
    if down:
        original_with_tools = provider.acomplete_with_tools

        async def failing(**kwargs: Any) -> Any:
            if kwargs["model"] in down:
                error = type("ServiceUnavailableError", (Exception,), {})
                raise error(f"{kwargs['model']} is down")
            return await original_with_tools(**kwargs)

        provider.acomplete_with_tools = failing  # type: ignore[method-assign]
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


async def _turn(
    bundle: AgentBundle,
    provider: InMemoryProvider,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Un turno: clasificar y el manejador de su intención, como el grafo."""
    llm = _router(provider)
    loader = _Loader(bundle)
    current = state or _state()
    classified = await make_classify_node(loader, llm)(current)  # type: ignore[arg-type]
    current = {**current, **classified}
    handler = make_handler_node(current["intent"], loader, llm, _Registry())  # type: ignore[arg-type]
    out = await handler(current)  # type: ignore[arg-type]
    return {**current, **out}


def _wire(provider: InMemoryProvider) -> list[tuple[Any, ...]]:
    """Lo que salió hacia el proveedor, llamada a llamada."""
    return [
        (
            c.role,
            c.model,
            json.dumps(c.messages, sort_keys=True, default=str),
            json.dumps(list(c.tools), sort_keys=True, default=str),
            json.dumps(c.extra, sort_keys=True, default=str),
        )
        for c in provider.calls
    ]


def _routed(provider: InMemoryProvider, task: str) -> list[LLMCall]:
    return [c for c in provider.calls if c.extra.get("task") == task]


# ── historia 13: lo que existe sigue funcionando ───────────────────────────


@pytest.mark.parametrize(
    "catalog",
    [todays_catalog, lambda: servable(classify=False)],
    ids=["catalogo_de_hoy_D44", "catalogo_que_sirve_sin_clasificador"],
)
@pytest.mark.parametrize(
    ("tools", "llm_policy"),
    [
        (frozenset(), None),
        (frozenset({TOOL}), None),
        (frozenset({TOOL}), {"respond_model": "anthropic/claude-haiku-4-5"}),
    ],
    ids=["sin_herramientas", "con_herramientas", "con_modelo_propio"],
)
async def test_an_agent_of_today_calls_its_provider_exactly_as_before(
    world: World,
    catalog: Callable[[], CatalogSnapshot],
    tools: frozenset[str],
    llm_policy: dict[str, Any] | None,
) -> None:
    """La prueba de la historia 13: el mismo turno de un agente de hoy, con el
    router fuera de alcance y con el router cableado, manda al proveedor las
    mismas llamadas byte a byte, y no deja afinidad ni decisiones."""
    bundle = _bundle(tools=tools, llm_policy=llm_policy)

    world.catalog = None
    before = _provider(tool_first=bool(tools))
    out_before = await _turn(bundle, before)

    world.catalog = catalog()
    after = _provider(tool_first=bool(tools))
    with capture_logs() as logs:
        out_after = await _turn(bundle, after)

    assert _wire(after) == _wire(before)
    assert len(after.calls) >= 2
    assert all("deployment" not in c.extra and "task" not in c.extra for c in after.calls)
    assert {c.model for c in after.calls} <= {
        "legacy/classify",
        "legacy/respond",
        "anthropic/claude-haiku-4-5",
    }
    for key in ("response", "intent", "tool_calls", "turn_failure", "response_model"):
        assert out_after[key] == out_before[key], key
    assert "pinned_model" not in out_after and "router_escalations" not in out_after
    assert not [e for e in logs if e["event"] == ROUTE_DECISION_EVENT]
    assert world.facts_reads == 0, "un agente de hoy no paga una lectura más por turno"
    assert not world.anomalies


async def test_the_classifier_of_every_agent_moves_to_the_cheapest_certified(
    world: World,
) -> None:
    """T145 (D24): ``classify`` pasa al certificado más barato para todos, en
    cuanto hay uno que pasa la batería. El de respuesta del agente de hoy, no."""
    provider = _provider()
    out = await _turn(_bundle(), provider)

    [classify] = _routed(provider, "classify")
    assert classify.model == TINY.key and classify.extra["deployment"] == TINY.key
    assert out["classification"] == _CLASSIFIED
    assert out["intent"] == "info"
    [answer] = [c for c in provider.calls if c.role == "info"]
    assert answer.model == "legacy/respond" and "deployment" not in answer.extra
    assert "pinned_model" not in out


async def test_the_typed_classifier_is_an_object_apart_from_the_answer_model(
    world: World,
) -> None:
    provider = _provider()
    out = await _turn(_bundle(AUTO), provider)
    [classify] = _routed(provider, "classify")
    [answer] = _routed(provider, "answer")
    assert classify.model == TINY.key
    assert answer.model == HAIKU_A.key, "el clasificador nunca es el de respuesta"
    assert out["classification"]["intents"] == 1
    assert out["router_turn"]["calls"] == 2


async def test_an_invalid_classification_is_a_fallback_turn(world: World) -> None:
    provider = _provider()
    original = provider.responder
    assert original is not None
    provider.responder = lambda c: (
        "no es json" if c.extra.get("task") == "classify" else original(c)
    )
    out = await _turn(_bundle(AUTO), provider)
    assert out["intent"] == "fallback"
    assert out["classification"] == {}
    assert out["response"] == "Abrimos de 10 a 14."


# ── afinidad (40.3, garantía 4) ────────────────────────────────────────────


async def test_a_profiled_agent_answers_on_the_cheapest_certified_and_pins_it(
    world: World,
) -> None:
    provider = _provider()
    out = await _turn(_bundle(AUTO), provider)

    [answer] = _routed(provider, "answer")
    assert answer.model == HAIKU_A.key
    pin = pins_from_state(out)[str(AGENT)]
    assert pin.deployment == HAIKU_A.key
    assert pin.agent_version == str(VERSION)
    assert pin.expires_at - pin.pinned_at >= 3600
    assert out["response_model"] == HAIKU_A.key
    assert out["turn_failure"] is None


async def test_the_affinity_holds_against_a_cheaper_one_until_a_new_version(
    world: World,
) -> None:
    now = time.time()
    held = PinnedModel(HAIKU_B.key, str(VERSION), pinned_at=now - 60, expires_at=now + 3000)
    state = _state(pinned_model=with_pin({}, AGENT, held))

    provider = _provider()
    out = await _turn(_bundle(AUTO), provider, state)
    [answer] = _routed(provider, "answer")
    assert answer.model == HAIKU_B.key, "la afinidad gana al más barato"
    assert pins_from_state(out)[str(AGENT)].expires_at > held.expires_at, "se desliza con el uso"

    provider = _provider()
    out = await _turn(_bundle(AUTO, version=NEW_VERSION), provider, state)
    [answer] = _routed(provider, "answer")
    assert answer.model == HAIKU_A.key, "otra versión publicada rompe la afinidad"
    assert pins_from_state(out)[str(AGENT)].agent_version == str(NEW_VERSION)


async def test_each_agent_keeps_its_own_affinity_in_the_shared_thread(world: World) -> None:
    now = time.time()
    sibling = PinnedModel(SONNET_B.key, "v-hermano", pinned_at=now, expires_at=now + 3600)
    state = _state(pinned_model=with_pin({}, SIBLING, sibling))
    out = await _turn(_bundle(AUTO), _provider(), state)
    pins = pins_from_state(out)
    assert pins[str(SIBLING)] == sibling
    assert pins[str(AGENT)].deployment == HAIKU_A.key


async def test_a_fallen_provider_answers_with_the_alternative_and_the_pin_follows(
    world: World,
) -> None:
    provider = _provider(down=frozenset({HAIKU_A.key}))
    out = await _turn(_bundle(AUTO), provider)
    assert out["response"] == "Abrimos de 10 a 14."
    assert out["response_model"] == HAIKU_B.key
    assert pins_from_state(out)[str(AGENT)].deployment == HAIKU_B.key


async def test_a_pinned_model_covers_only_the_conversation(world: World) -> None:
    world.facts = RouteFacts(eu_only=True, agent_certified=frozenset({HAIKU_A.key}))
    provider = _provider()
    out = await _turn(_bundle({"kind": "pinned", "deployment": SONNET_B.key}), provider)
    [classify] = _routed(provider, "classify")
    [answer] = _routed(provider, "answer")
    assert classify.model == TINY.key, "las demás tareas siguen la política (39.8)"
    assert answer.model == SONNET_B.key
    assert "pinned_model" not in out, "«Fijar un modelo» no es afinidad"


# ── escalado (40.4) ────────────────────────────────────────────────────────


def _refused(call: ToolCall) -> dict[str, Any]:
    return {
        "tool": call.name,
        "status": "error",
        "error": "1 validation error",
        "error_kind": "invalid_arguments",
        "result": {},
    }


async def test_a_tool_that_refuses_its_arguments_escalates_in_an_isolated_subcall(
    world: World,
) -> None:
    world.envelope = _refused
    provider = _provider(tool_first=True)
    out = await _turn(_bundle(AUTO, tools=frozenset({TOOL})), provider)

    [escalate] = _routed(provider, "escalate")
    assert escalate.model == SONNET_A.key, "la gama de encima, hasta la que deja el perfil"
    assert len(escalate.messages) == 2, "un resumen, no el hilo"
    assert "PROMPT-DEL-AGENTE" not in json.dumps(escalate.messages)
    assert "tool_args_rejected" in escalate.messages[1]["content"]

    loop = _routed(provider, "tool_turn")
    assert len(loop) == 2
    assert {c.model for c in loop} == {HAIKU_A.key}, "el bucle principal no cambia de modelo"
    assert any("Pide la fecha exacta." in m.get("content", "") for m in loop[1].messages)
    assert len(out["router_escalations"]) == 1
    assert pins_from_state(out)[str(AGENT)].deployment == HAIKU_A.key
    assert out["turn_failure"] is None


async def test_several_requests_in_one_message_escalate_before_answering(world: World) -> None:
    provider = _provider()
    state = _state(classification={**_CLASSIFIED, "intents": 2})

    llm = _router(provider)
    out = await make_handler_node("info", _Loader(_bundle(AUTO)), llm, _Registry())(state)  # type: ignore[arg-type]
    assert [c.extra["task"] for c in provider.calls] == ["escalate", "answer"]
    assert out["response"] == "Abrimos de 10 a 14."


async def test_the_adviser_can_hand_the_conversation_to_a_person(world: World) -> None:
    world.envelope = _refused
    provider = _provider(
        tool_first=True, escalation={"guidance": "Que lo vea alguien.", "handoff": True}
    )
    out = await _turn(_bundle(AUTO, tools=frozenset({TOOL})), provider)
    assert out["turn_failure"] == {"kind": "handoff", "reason": "escalated", "detail": None}
    assert out["response"] == _HANDOFF_RESPONSE


async def test_economy_does_not_escalate_it_hands_over_to_a_person(world: World) -> None:
    world.envelope = _refused
    provider = _provider(tool_first=True)
    out = await _turn(_bundle(ECONOMY, tools=frozenset({TOOL})), provider)
    assert not _routed(provider, "escalate")
    assert out["turn_failure"] == {"kind": "handoff", "reason": "escalated", "detail": None}
    assert out["response"] == _HANDOFF_RESPONSE


async def test_three_escalations_an_hour_then_a_person(world: World) -> None:
    world.envelope = _refused
    now = time.time()
    recent = [now - 600, now - 300, now - 60]
    provider = _provider(tool_first=True)
    out = await _turn(
        _bundle(AUTO, tools=frozenset({TOOL})), provider, _state(router_escalations=recent)
    )
    assert not _routed(provider, "escalate")
    assert out["turn_failure"]["reason"] == "turn_limit"
    old = [now - ESCALATION_WINDOW_S - 1, now - 60]
    provider = _provider(tool_first=True)
    out = await _turn(
        _bundle(AUTO, tools=frozenset({TOOL})), provider, _state(router_escalations=old)
    )
    assert len(_routed(provider, "escalate")) == 1, "lo de hace más de una hora no cuenta"


# ── fallos y límites (40.6, 40.7, 40.10) ───────────────────────────────────


async def test_without_a_model_in_the_residency_the_turn_does_not_leave_it(
    world: World,
) -> None:
    world.catalog = todays_catalog()
    provider = _provider()
    out = await _turn(_bundle(AUTO), provider)
    assert provider.calls == [], "nada sale de la residencia del cliente"
    assert out["turn_failure"] == {"kind": "llm_failed", "reason": "no_model", "detail": None}
    assert out["intent"] == "fallback"
    assert {(d.task, d.anomaly) for d in world.anomalies} == {
        ("classify", "no_model"),
        ("answer", "no_model"),
    }
    assert all(d.tenant_id == TENANT and d.agent_id == AGENT for d in world.anomalies)


async def test_a_profiled_agent_without_its_catalog_has_no_model_never_todays(
    world: World,
) -> None:
    world.catalog = None
    provider = _provider()
    out = await _turn(_bundle(AUTO), provider)
    assert provider.calls == [], (
        "sin catálogo no sale nada: los modelos de hoy no son su residencia"
    )
    assert out["intent"] == "fallback"
    assert out["turn_failure"]["reason"] == "no_model"


async def test_when_every_alternative_fails_it_is_a_provider_failure(world: World) -> None:
    provider = _provider(down=frozenset({HAIKU_A.key, HAIKU_B.key}))
    out = await _turn(_bundle(AUTO), provider)
    assert out["turn_failure"]["kind"] == "llm_failed"
    assert out["turn_failure"]["reason"] == "provider_failure"


async def test_twelve_calls_per_turn_then_a_person(world: World) -> None:
    provider = _provider()
    state = _state(router_turn={"calls": 12, "cost_micros": 0})
    llm = _router(provider)
    out = await make_handler_node("info", _Loader(_bundle(AUTO)), llm, _Registry())(state)  # type: ignore[arg-type]
    assert provider.calls == []
    assert out["turn_failure"]["reason"] == "turn_limit"
    assert out["response"] == _HANDOFF_RESPONSE


async def test_the_reserve_model_answers_and_is_an_anomaly(world: World) -> None:
    reserve = profile(
        "auto",
        answer={"reserve": HAIKU_B.key},
        classify={"reserve": TINY.key},
    )
    world.catalog = snapshot([TINY, HAIKU_A, HAIKU_B, SONNET_A, SONNET_B], [], reserve, _economy())
    provider = _provider()
    out = await _turn(_bundle(AUTO), provider)
    assert [c.model for c in provider.calls] == [TINY.key, HAIKU_B.key]
    assert {(d.task, d.anomaly) for d in world.anomalies} == {
        ("classify", "reserve_model"),
        ("answer", "reserve_model"),
    }
    assert "pinned_model" not in out, "la reserva no fija modelo"


# ── registro (40.9, garantía 6) ────────────────────────────────────────────


async def test_every_decision_names_the_conversation_and_the_version_and_no_text(
    world: World,
) -> None:
    with capture_logs() as logs:
        await _turn(_bundle(AUTO), _provider())
    events = [e for e in logs if e["event"] == ROUTE_DECISION_EVENT]
    assert [e["task"] for e in events] == ["classify", "answer"]
    for event in events:
        assert event["tenant_id"] == str(TENANT)
        assert event["agent_id"] == str(AGENT)
        assert event["conversation_id"] == str(CONVERSATION)
        assert event["agent_version"] == str(VERSION)
        assert event["turn_id"] == "turn-1"
        assert uuid.UUID(event["decision_id"])
    assert "sábado" not in repr(events)


# ── la señal «la herramienta rechazó sus argumentos» ───────────────────────


async def test_the_dispatch_marks_a_tool_that_refused_its_arguments() -> None:
    class Strict(BaseModel):
        n: int

    class Refusing(MCPRegistry):
        async def dispatch(self, name: str, args: dict[str, Any], **_: Any) -> dict[str, Any]:
            try:
                Strict.model_validate(args)
            except ValidationError as exc:
                raise ToolError(f"tool {name!r} failed: {exc}") from exc
            raise AssertionError("unreachable")

    class Failing(MCPRegistry):
        async def dispatch(self, name: str, args: dict[str, Any], **_: Any) -> dict[str, Any]:
            raise ToolError("the calendar is down")

    call = ToolCall(id="t", name=TOOL, arguments={"n": "dos"})
    refused = await _dispatch_tool(Refusing(), call, (TOOL,), "info")
    assert refused["status"] == "error" and refused["error_kind"] == "invalid_arguments"
    failed = await _dispatch_tool(Failing(), call, (TOOL,), "info")
    assert failed["status"] == "error" and "error_kind" not in failed
