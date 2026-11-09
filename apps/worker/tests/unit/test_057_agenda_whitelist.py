"""Spec 057, T006 (garantía 2; requisitos 7.6 y 4.2), la parte del runtime.

La lista de herramientas de un turno es a la vez lo que ve el modelo
(``get_openai_tools``) y la lista blanca del despacho (``registry.dispatch``):

- con Reservas encendido y la agenda lista, un agente **sin** agenda no tiene
  ninguna ``reservas.*`` ni en una ni en otra, con ninguna intención; y si el
  modelo inventa una, el registro la rechaza sin ejecutarla;
- con la agenda sin terminar, un agente **con** agenda no puede ejecutar
  ``reservas.create`` aunque el modelo la invente.

El registro es el de verdad (``build_default_registry``) y el despacho, el del
grafo (``pipeline._dispatch_tool``): solo se graban las listas que reciben.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Iterator
from typing import Any

import pytest
from nexus_api.services.activations import ToolPolicy
from nexus_mcp import MCPRegistry, build_default_registry

import nexus_worker.runtime.pipeline as pipeline
from nexus_worker.runtime import booking_brake
from nexus_worker.runtime.agent_loader import AgentBundle
from nexus_worker.runtime.llm import CooldownBook, InMemoryProvider, LLMCall, LLMRouter, ToolCall
from nexus_worker.runtime.pipeline import VALID_INTENTS, make_handler_node
from tests.unit._router_world import AGENT, TENANT

pytestmark = pytest.mark.asyncio

RESERVAS = "reservas."
#: Un agente de cobros: con Reservas encendido para el cliente, sigue sin agenda.
COLLECTIONS = frozenset(
    {"escalate.escalate_to_human", "client.get_history", "response.send_interactive"}
)
#: Uno que da citas.
GIVER = frozenset(
    {
        "reservas.services",
        "reservas.find_slots",
        "reservas.create",
        "reservas.list_mine",
        "reservas.cancel",
        "escalate.escalate_to_human",
    }
)


class RecordingRegistry(MCPRegistry):
    """El registro de verdad, que apunta qué lista recibe cada llamada."""

    def __init__(self) -> None:
        super().__init__()
        source = build_default_registry()
        for name in source.names():
            self._tools[name] = source._tools[name]
        self.offered: list[tuple[str, ...]] = []
        self.whitelists: list[tuple[str, ...]] = []
        self.ran: list[str] = []

    def get_openai_tools(self, whitelist: Iterable[str]) -> list[dict[str, Any]]:
        names = tuple(whitelist)
        self.offered.append(names)
        return super().get_openai_tools(names)

    async def dispatch(self, name: str, args: dict[str, Any], *, whitelist: Iterable[str]) -> Any:
        names = tuple(whitelist)
        self.whitelists.append(names)
        if name in names:  # pragma: no cover - lo que se prueba es que nunca llega
            self.ran.append(name)
        return await super().dispatch(name, args, whitelist=names)


@pytest.fixture(autouse=True)
def graph_without_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    async def nothing(*_a: Any, **_k: Any) -> Any:
        return ""

    async def no_knowledge(*_a: Any, **_k: Any) -> tuple[str, list[Any]]:
        return "", []

    async def no_gates(_tenant: uuid.UUID) -> frozenset[str]:
        return frozenset()

    async def open_policy(_tenant: uuid.UUID, _agent: uuid.UUID | None) -> ToolPolicy:
        return ToolPolicy()

    async def not_backed(*_a: Any, **_k: Any) -> bool:
        return False

    async def no_record(**_k: Any) -> None:
        return None

    monkeypatch.setattr(pipeline, "_load_kg_snapshot_text", nothing)
    monkeypatch.setattr(pipeline, "_load_knowledge", no_knowledge)
    monkeypatch.setattr(pipeline, "_load_gated_tools", no_gates)
    monkeypatch.setattr(pipeline, "_load_tool_policy", open_policy)
    monkeypatch.setattr(pipeline, "_now_note", lambda _tz: "Hoy es lunes, 10:00.")
    monkeypatch.setattr(booking_brake, "conversation_backed", not_backed)
    monkeypatch.setattr(booking_brake, "record_brake", no_record)
    yield


def _ready(monkeypatch: pytest.MonkeyPatch, value: bool) -> None:
    async def readiness(_tenant: uuid.UUID) -> bool:
        return value

    monkeypatch.setattr(pipeline, "_load_agenda_ready", readiness)


class _Loader:
    def __init__(self, tools: frozenset[str]) -> None:
        self.bundle = AgentBundle(
            tenant_id=TENANT,
            version=1,
            version_id=uuid.uuid4(),
            system_prompt="Eres el agente del negocio.",
            tools=tools,
            agent_id=AGENT,
        )

    async def load(self, _tenant: uuid.UUID, _agent: uuid.UUID | None = None) -> AgentBundle:
        return self.bundle


def _inventing(name: str) -> InMemoryProvider:
    """Un modelo que pide ``name`` una vez, la tenga o no, y luego contesta."""

    def answered(call: LLMCall) -> bool:
        return bool(call.messages) and call.messages[-1].get("role") == "tool"

    def tool_caller(call: LLMCall) -> list[ToolCall]:
        if call.role == "classify" or answered(call):
            return []
        return [ToolCall(id="inv", name=name, arguments={"date": "2026-11-10", "time": "10:00"})]

    def responder(call: LLMCall) -> str:
        return "NO" if call.role == "classify" else ("" if not answered(call) else "Vale.")

    return InMemoryProvider(responder=responder, tool_caller=tool_caller)


async def _turn(
    tools: frozenset[str], provider: InMemoryProvider, registry: RecordingRegistry, intent: str
) -> dict[str, Any]:
    llm = LLMRouter(
        provider=provider,
        classify_model="t/c",
        respond_model="t/r",
        fallback_model="t/f",
        cooldowns=CooldownBook(),
        retry_backoff_s=0.0,
    )
    handler = make_handler_node(intent, _Loader(tools), llm, registry)  # type: ignore[arg-type]
    state = {
        "tenant_id": str(TENANT),
        "agent_id": str(AGENT),
        "conversation_id": None,
        "inbound_message_id": "turn-1",
        "customer_id": None,
        "channel_type": "whatsapp",
        "user_message": "Quiero una cita el martes a las 10",
        "history": [],
        "classification": {},
        "router_turn": {},
    }
    out: dict[str, Any] = await handler(state)  # type: ignore[arg-type]
    return out


@pytest.mark.parametrize("intent", VALID_INTENTS)
async def test_an_agent_without_the_agenda_never_gets_a_reservas_tool(
    monkeypatch: pytest.MonkeyPatch, intent: str
) -> None:
    _ready(monkeypatch, True)
    registry = RecordingRegistry()

    out = await _turn(COLLECTIONS, _inventing("reservas.create"), registry, intent)

    assert registry.offered, "el turno pidió sus herramientas"
    for names in (*registry.offered, *registry.whitelists):
        assert not [n for n in names if n.startswith(RESERVAS)], names
    assert registry.ran == []
    invented = [e for e in out["tool_calls"] if e.get("tool") == "reservas.create"]
    assert invented and all(e["status"] == "skipped:not_in_whitelist" for e in invented)


async def test_with_the_agenda_not_ready_an_invented_booking_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ready(monkeypatch, False)
    registry = RecordingRegistry()

    out = await _turn(GIVER, _inventing("reservas.create"), registry, "book")

    [whitelist] = registry.whitelists
    assert "reservas.create" not in whitelist and "reservas.find_slots" not in whitelist
    assert "reservas.list_mine" in whitelist, "lo que sirve con lo que hay se queda"
    assert registry.ran == []
    [envelope] = out["tool_calls"]
    assert envelope["tool"] == "reservas.create"
    assert envelope["status"] == "skipped:not_in_whitelist"


async def test_with_the_agenda_ready_the_giver_keeps_its_agenda(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El control: lo de arriba es por la agenda, no por el agente."""
    _ready(monkeypatch, True)
    registry = RecordingRegistry()
    quiet = InMemoryProvider(responder=lambda call: "NO" if call.role == "classify" else "Vale.")

    await _turn(GIVER, quiet, registry, "book")

    [offered] = registry.offered
    assert {"reservas.find_slots", "reservas.create", "reservas.list_mine"} <= set(offered)
