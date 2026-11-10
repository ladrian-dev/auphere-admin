"""Spec 047, T177 — Recepción en el bucle del manejador (requisito 53).

- Recepción lee su lista (nombre, id y cuándo) justo después de su prompt, y
  solo cuando tiene la herramienta de derivar en la lista blanca de este turno.
- La herramienta se ofrece en todas las intenciones, también ``escalate``.
- Una derivación hecha corta el bucle: una sola llamada al modelo, sin la
  respuesta de reserva (contesta el destino) y con ``reception_handoff`` en el
  estado. Una negativa no corta: el modelo sigue y contesta.
- El juez no gradúa la pasada de Recepción que derivó.

El despacho (``_dispatch_tool``) se sustituye: la herramienta de verdad, contra la
base, la prueban ``apps/api/tests/integration/reception``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
from nexus_mcp import MCPRegistry
from nexus_mcp.servers.reception import ReceptionHandoff

import nexus_worker.runtime.pipeline as pipeline
from nexus_worker.runtime.agent_loader import AgentBundle, ReceptionTarget
from nexus_worker.runtime.llm import LLMResponse, LLMRouter, ToolCall
from nexus_worker.runtime.pipeline import make_grade_outcome_node, make_handler_node

HANDOFF = "reception.handoff"
SALES = uuid.UUID("22222222-2222-4222-8222-222222222222")
WHEN = "Cuando pidan precios de mayorista."


@dataclass
class _Scripted:
    responses: list[LLMResponse] = field(default_factory=list)
    calls: int = 0
    seen_tools: list[list[str]] = field(default_factory=list)
    seen_messages: list[list[dict[str, Any]]] = field(default_factory=list)

    async def acomplete(self, **_: Any) -> str:
        return "info"

    async def acomplete_with_tools(
        self,
        *,
        tenant_id: uuid.UUID,
        role: str,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        extra: dict[str, Any] | None = None,
    ) -> LLMResponse:
        self.seen_tools.append([t.get("function", {}).get("name", "") for t in tools])
        self.seen_messages.append(list(messages))
        idx = self.calls
        self.calls += 1
        return self.responses[idx] if idx < len(self.responses) else LLMResponse(text="Vale.")


def _bundle(*, targets: bool = True) -> AgentBundle:
    return AgentBundle(
        tenant_id=uuid.uuid4(),
        version=1,
        version_id=uuid.uuid4(),
        system_prompt="Eres la recepción de la barbería.",
        tools=frozenset({HANDOFF}),
        policies={},
        reception_targets=(ReceptionTarget(SALES, "Ventas mayoristas", WHEN),) if targets else (),
    )


class _Loader:
    def __init__(self, bundle: AgentBundle) -> None:
        self.bundle = bundle

    async def load(self, _tid: uuid.UUID, _agent: uuid.UUID | None = None) -> AgentBundle:
        return self.bundle


def _router(provider: _Scripted) -> LLMRouter:
    return LLMRouter(
        provider=provider,
        classify_model="anthropic/haiku",
        respond_model="anthropic/sonnet",
        fallback_model="openai/gpt-4o",
    )


def _state(tenant_id: uuid.UUID, intent: str) -> dict[str, Any]:
    return {
        "tenant_id": str(tenant_id),
        "customer_id": str(uuid.uuid4()),
        "channel_type": "whatsapp",
        "intent": intent,
        "user_message": "quiero comprar al por mayor",
        "history": [],
    }


def _call() -> LLMResponse:
    return LLMResponse(
        text="",
        tool_calls=(
            ToolCall(
                id="call_1",
                name=HANDOFF,
                arguments={"to_agent_id": str(SALES), "summary": "Compra al por mayor."},
            ),
        ),
    )


def _stub(monkeypatch: pytest.MonkeyPatch, *, handed_off: bool) -> None:
    async def _fake(
        registry: MCPRegistry,
        call: ToolCall,
        available_names: tuple[str, ...],
        intent: str,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "tool": call.name,
            "intent": intent,
            "status": "ok",
            "args": dict(call.arguments),
            "result": {
                "handed_off": handed_off,
                "outcome": "handed_off" if handed_off else "target_unavailable",
                "to_agent": "Ventas mayoristas" if handed_off else None,
                "hop": 1 if handed_off else 0,
                "note": "",
            },
        }

    async def _empty(*_: Any) -> str:
        return ""

    async def _nothing_gated(*_: Any) -> frozenset[str]:
        # Without the DB the gate cannot be read, and an unread gate is closed
        # (T217): this test is not about gating, so the tenant gated nothing.
        return frozenset()

    monkeypatch.setattr(pipeline, "_dispatch_tool", _fake)
    monkeypatch.setattr(pipeline, "_load_kg_snapshot_text", _empty)
    monkeypatch.setattr(pipeline, "_load_gated_tools", _nothing_gated)


def _registry() -> MCPRegistry:
    registry = MCPRegistry()
    registry.register(ReceptionHandoff())
    return registry


@pytest.mark.asyncio
@pytest.mark.parametrize("intent", ["info", "escalate", "fallback", "book"])
async def test_a_handoff_ends_receptions_turn_without_a_word_of_its_own(
    monkeypatch: pytest.MonkeyPatch, intent: str
) -> None:
    _stub(monkeypatch, handed_off=True)
    provider = _Scripted(responses=[_call()])
    bundle = _bundle()
    handler = make_handler_node(intent, _Loader(bundle), _router(provider), _registry())

    out = await handler(_state(bundle.tenant_id, intent))

    assert provider.calls == 1, "contesta el destino: Recepción no hace otra ronda"
    assert HANDOFF in provider.seen_tools[0], f"la herramienta no se ofrece en {intent}"
    assert out["response"] == "", "ni la respuesta de reserva"
    assert out["turn_failure"] is None
    assert out["reception_handoff"] == {"to_agent_id": str(SALES), "hop": 1}
    # Su lista, justo después de su prompt: nombre, id y cuándo.
    note = provider.seen_messages[0][1]["content"]
    assert "Ventas mayoristas" in note and str(SALES) in note and WHEN in note


@pytest.mark.asyncio
async def test_a_refused_handoff_lets_reception_keep_the_conversation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub(monkeypatch, handed_off=False)
    provider = _Scripted(responses=[_call(), LLMResponse(text="Te ayudo yo con el pedido.")])
    bundle = _bundle()
    handler = make_handler_node("info", _Loader(bundle), _router(provider), _registry())

    out = await handler(_state(bundle.tenant_id, "info"))

    assert provider.calls == 2
    assert out["response"] == "Te ayudo yo con el pedido."
    assert out["reception_handoff"] == {}


@pytest.mark.asyncio
async def test_no_list_no_note(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub(monkeypatch, handed_off=False)
    provider = _Scripted(responses=[LLMResponse(text="Hola.")])
    bundle = _bundle(targets=False)
    handler = make_handler_node("info", _Loader(bundle), _router(provider), _registry())

    await handler(_state(bundle.tenant_id, "info"))

    assert not any(
        "Derivar a otro agente" in str(m.get("content")) for m in provider.seen_messages[0]
    )


@pytest.mark.asyncio
async def test_the_judge_does_not_grade_the_pass_that_handed_over() -> None:
    class _Grader:
        async def grade(self, **_: Any) -> Any:  # pragma: no cover - no debe llamarse
            raise AssertionError("graduó la pasada de Recepción")

    node = make_grade_outcome_node(
        grader=_Grader(),  # type: ignore[arg-type]
        llm_router=_router(_Scripted()),
    )
    out = await node(
        {  # type: ignore[arg-type]
            "tenant_id": str(uuid.uuid4()),
            "response": "",
            "agent_runtime_flags": {"outcome_grader": True, "grader_mode": "always"},
            "reception_handoff": {"to_agent_id": str(SALES), "hop": 1},
        }
    )
    assert out["outcome_overall"] == "skipped"
