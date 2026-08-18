"""El bucle de herramientas del grafo (CO-02).

Lo que se prueba aquí es el MOTOR, no el prompt: que las fases siguen a lo
que está pasando, que los topes cortan, que R1 marca lo que tiene que
marcar y —lo más fácil de romper sin darse cuenta— que el mensaje del
asistente vuelve al proveedor con sus llamadas y sus bloques de
pensamiento. Perder eso último es un 400 de Anthropic en producción y en
ningún test.

El proveedor es ``InMemoryProvider`` y el juego de herramientas un doble:
ni red ni base de datos.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
from langgraph.checkpoint.memory import MemorySaver
from nexus_worker.runtime.companion import build_companion_graph
from nexus_worker.runtime.companion.graph import MAX_MODEL_STEPS
from nexus_worker.runtime.companion.grounding import factual_claims, is_unsupported
from nexus_worker.runtime.llm import InMemoryProvider, ToolCall

pytestmark = pytest.mark.unit

MODEL = "anthropic/claude-sonnet-4-6"


@dataclass
class FakeCitation:
    citation_id: str = "c1"
    claim: str = "Consumo del partner"
    source: str = "/console/usage"
    fetched_at: str = "2026-08-18T00:00:00+00:00"

    def as_payload(self) -> dict[str, str]:
        return {
            "citation_id": self.citation_id,
            "claim": self.claim,
            "source": self.source,
            "fetched_at": self.fetched_at,
        }


@dataclass
class FakeResult:
    name: str
    label: str
    ok: bool
    content: str
    latency_ms: int = 3
    error_code: str | None = None
    citation: Any = None


@dataclass
class FakeBelt:
    """Doble del juego de herramientas. Cuenta igual que el de verdad."""

    ok: bool = True
    max_calls: int = 25
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    reads: int = 0
    calls_made: int = 0

    @property
    def calls_left(self) -> int:
        return max(0, self.max_calls - self.calls_made)

    @property
    def reads_done(self) -> int:
        return self.reads

    def specs(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "console.get_usage",
                    "description": "…",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

    async def call(self, name: str, arguments: dict[str, Any]) -> FakeResult:
        self.calls.append((name, arguments))
        self.calls_made += 1
        if not self.ok:
            return FakeResult(
                name, name, False, '{"error": "unknown_client"}', error_code="unknown_client"
            )
        self.reads += 1
        return FakeResult(name, name, True, '{"tokens": 1200}', citation=FakeCitation())


def _steps(*scripts: list[ToolCall]):
    """``tool_caller`` que devuelve un guion distinto en cada paso."""
    seen = {"n": 0}

    def _caller(_call: Any) -> list[ToolCall]:
        i = seen["n"]
        seen["n"] += 1
        return scripts[i] if i < len(scripts) else []

    return _caller


async def _run(provider: InMemoryProvider, belt: Any, **state):
    graph = build_companion_graph(
        provider=provider, model=MODEL, checkpointer=MemorySaver(), toolbelt=belt
    )
    events: list[tuple[str, dict]] = []
    final: dict[str, Any] = {}
    async for ev in graph.astream_events(
        {"user_message": "¿cuánto gastó boreal?", "history": [], **state},
        config={"configurable": {"thread_id": str(uuid.uuid4())}},
        version="v2",
    ):
        if ev.get("event") == "on_custom_event":
            events.append((str(ev.get("name")), dict(ev.get("data") or {})))
        elif ev.get("event") == "on_chain_end" and ev.get("name") == "respond":
            out = (ev.get("data") or {}).get("output")
            if isinstance(out, dict):
                final = out
    return events, final


# ── el bucle ───────────────────────────────────────────────────────────


async def test_a_tool_call_runs_and_the_answer_comes_from_the_next_step() -> None:
    """La forma de un bucle real: el paso 1 pide, el paso 2 responde. No
    hay una tercera llamada "para redactar" — sería pagar el turno dos
    veces para repetir lo que ya está escrito."""
    belt = FakeBelt()
    provider = InMemoryProvider(
        responder=lambda c: "Gastó 1.200 tokens",
        tool_caller=_steps([ToolCall(id="t1", name="console.get_usage", arguments={"days": 7})]),
    )
    _events, final = await _run(provider, belt)

    assert belt.calls == [("console.get_usage", {"days": 7})]
    assert final["answer"] == "Gastó 1.200 tokens"
    assert len(provider.calls) == 2


async def test_the_three_tool_events_are_emitted_in_order() -> None:
    belt = FakeBelt()
    provider = InMemoryProvider(
        responder=lambda c: "listo",
        tool_caller=_steps([ToolCall(id="t1", name="console.get_usage", arguments={})]),
    )
    events, _final = await _run(provider, belt)
    names = [n for n, _ in events]
    assert names.index("tool.call.started") < names.index("tool.call.completed")
    assert names.index("tool.call.completed") < names.index("citation")

    started = next(d for n, d in events if n == "tool.call.started")
    assert started["name"] == "console.get_usage"
    completed = next(d for n, d in events if n == "tool.call.completed")
    assert completed["ok"] is True and completed["citation_id"] == "c1"


async def test_a_failed_tool_produces_no_citation_but_does_complete() -> None:
    belt = FakeBelt(ok=False)
    provider = InMemoryProvider(
        responder=lambda c: "no pude leerlo",
        tool_caller=_steps([ToolCall(id="t1", name="console.get_client", arguments={})]),
    )
    events, _final = await _run(provider, belt)
    completed = next(d for n, d in events if n == "tool.call.completed")
    assert completed["ok"] is False and completed["error"] == "unknown_client"
    assert not [n for n, _ in events if n == "citation"]


async def test_the_assistant_message_and_the_tool_result_go_back_to_the_provider() -> None:
    """Sin el mensaje del asistente delante, los resultados de herramienta
    quedan huérfanos y el proveedor rechaza la petición entera."""
    belt = FakeBelt()
    provider = InMemoryProvider(
        responder=lambda c: "ok",
        tool_caller=_steps([ToolCall(id="t1", name="console.get_usage", arguments={})]),
    )
    await _run(provider, belt)

    second = provider.calls[1].messages
    assistant = next(m for m in second if m["role"] == "assistant")
    assert assistant["tool_calls"][0]["function"]["name"] == "console.get_usage"
    tool_msg = next(m for m in second if m["role"] == "tool")
    assert tool_msg["tool_call_id"] == "t1"
    assert json.loads(tool_msg["content"])["tokens"] == 1200


async def test_the_tools_are_offered_on_every_step() -> None:
    belt = FakeBelt()
    provider = InMemoryProvider(
        responder=lambda c: "ok",
        tool_caller=_steps([ToolCall(id="t1", name="console.get_usage", arguments={})]),
    )
    await _run(provider, belt)
    assert all(call.tools for call in provider.calls)


async def test_two_rounds_of_tools_both_run() -> None:
    belt = FakeBelt()
    provider = InMemoryProvider(
        responder=lambda c: "ok",
        tool_caller=_steps(
            [ToolCall(id="t1", name="console.list_clients", arguments={})],
            [ToolCall(id="t2", name="console.get_usage", arguments={})],
        ),
    )
    await _run(provider, belt)
    assert [name for name, _ in belt.calls] == ["console.list_clients", "console.get_usage"]


async def test_the_step_ceiling_stops_a_model_that_never_finishes() -> None:
    """Un modelo que se atasca alternando dos lecturas no se detiene solo, y
    a la doceava llamada el usuario ya se fue."""
    belt = FakeBelt(max_calls=999)
    provider = InMemoryProvider(
        responder=lambda c: "",
        tool_caller=lambda c: [
            ToolCall(id=uuid.uuid4().hex[:8], name="console.get_usage", arguments={})
        ],
    )
    await _run(provider, belt)
    assert len(provider.calls) == MAX_MODEL_STEPS


# ── fases ──────────────────────────────────────────────────────────────


async def test_the_phase_follows_what_is_happening() -> None:
    """El pill dice *Investigando* mientras corre una herramienta y
    *Respondiendo* mientras salen palabras."""
    belt = FakeBelt()
    provider = InMemoryProvider(
        responder=lambda c: "Gastó mucho",
        tool_caller=_steps([ToolCall(id="t1", name="console.get_usage", arguments={})]),
    )
    events, _final = await _run(provider, belt)
    phases = [d["phase"] for n, d in events if n == "phase.changed"]
    assert phases[0] == "understand"
    assert phases[1] == "investigate"
    assert phases[-1] == "respond"


async def test_without_tool_calls_the_phases_are_the_ones_co_01_fixed() -> None:
    belt = FakeBelt()
    provider = InMemoryProvider(responder=lambda c: "no necesito leer nada")
    events, _final = await _run(provider, belt)
    phases = [d["phase"] for n, d in events if n == "phase.changed"]
    assert phases == ["understand", "investigate", "respond"]
    assert belt.calls == []


# ── R1 · sin lectura no hay afirmación ─────────────────────────────────


async def test_a_turn_that_states_a_figure_without_reading_is_marked() -> None:
    belt = FakeBelt()
    provider = InMemoryProvider(responder=lambda c: "Boreal gastó 1.200.000 tokens este mes")
    _events, final = await _run(provider, belt)
    assert final["unsupported"] is True


async def test_a_turn_that_read_first_is_never_marked() -> None:
    belt = FakeBelt()
    provider = InMemoryProvider(
        responder=lambda c: "Boreal gastó 1.200 tokens",
        tool_caller=_steps([ToolCall(id="t1", name="console.get_usage", arguments={})]),
    )
    _events, final = await _run(provider, belt)
    assert final["unsupported"] is False


async def test_advice_without_figures_is_not_marked() -> None:
    """El detector es estrecho a propósito: marcar de más convierte el aviso
    en ruido y la métrica en basura."""
    belt = FakeBelt()
    provider = InMemoryProvider(
        responder=lambda c: (
            "Para publicar el agente lo llevas al playground, lo pruebas y luego "
            "pulsas publicar. Te lo explico en 3 pasos si quieres."
        )
    )
    _events, final = await _run(provider, belt)
    assert final["unsupported"] is False


@pytest.mark.parametrize(
    "answer",
    [
        "El consumo subió un 40 % este mes",
        "Van 1.200 mensajes en la semana",
        "La versión v7 está publicada",
        "El canal está activo desde ayer",
        "Se publicó el 2026-08-14",
        "Llevan 250 USD gastados",
    ],
)
def test_the_six_factual_patterns_fire(answer: str) -> None:
    assert factual_claims(answer)
    assert is_unsupported(answer, reads_done=0)
    assert not is_unsupported(answer, reads_done=1)


@pytest.mark.parametrize(
    "answer",
    [
        "Te lo cuento en 3 pasos: primero abres la pestaña, luego revisas el prompt.",
        "Depende de cómo tengas configurada la escalada.",
        "No tengo forma de saberlo sin mirarlo. ¿Quieres que lo consulte?",
    ],
)
def test_ordinary_prose_does_not_fire(answer: str) -> None:
    assert not factual_claims(answer)


# ── presupuesto visible ────────────────────────────────────────────────


async def test_the_model_is_told_when_it_is_running_out_of_calls() -> None:
    """Un agente que dice "con lo que me queda llego a leer el diagnóstico
    pero no la auditoría" es mejor que uno al que cortan en seco."""
    belt = FakeBelt(max_calls=3)
    provider = InMemoryProvider(
        responder=lambda c: "ok",
        tool_caller=_steps([ToolCall(id="t1", name="console.get_usage", arguments={})]),
    )
    await _run(provider, belt)
    notes = [
        m
        for call in provider.calls
        for m in call.messages
        if m["role"] == "system" and "consultas en este turno" in str(m["content"])
    ]
    assert notes


async def test_no_budget_note_while_there_is_room() -> None:
    """Una nota por paso es ruido, y el modelo deja de leerla."""
    belt = FakeBelt(max_calls=25)
    provider = InMemoryProvider(responder=lambda c: "ok")
    await _run(provider, belt)
    assert not [
        m
        for call in provider.calls
        for m in call.messages
        if m["role"] == "system" and "consultas en este turno" in str(m["content"])
    ]


async def test_the_budget_note_never_touches_the_cached_prefix() -> None:
    """El caché es un encaje de prefijo: la nota se AÑADE al final, nunca
    se mete en el prompt de sistema ni se reescribe una anterior."""
    from nexus_worker.runtime.companion.prompt import SYSTEM_PROMPT

    belt = FakeBelt(max_calls=2)
    provider = InMemoryProvider(
        responder=lambda c: "ok",
        tool_caller=_steps([ToolCall(id="t1", name="console.get_usage", arguments={})]),
    )
    await _run(provider, belt)
    for call in provider.calls:
        assert call.messages[0]["content"] == SYSTEM_PROMPT
