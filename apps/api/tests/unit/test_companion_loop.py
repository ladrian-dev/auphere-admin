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
from langgraph.types import Command
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


def _tool_choice(call: Any) -> Any:
    return (call.extra or {}).get("tool_choice")


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


async def test_the_thinking_blocks_survive_the_notes_and_the_closing_step() -> None:
    """Perder los bloques de pensamiento al reordenar el estado es un 400 de
    Anthropic en producción y en ningún test.

    Las notas de CO-06 (presupuesto y expediente) se **añaden** al final y
    no reordenan nada; el paso de cierre reenvía ``messages`` tal cual. Aquí
    se mide justo eso: el mensaje del asistente sigue llevando sus bloques,
    y los resultados de herramienta siguen inmediatamente detrás del suyo.
    """
    belt = FakeBelt(max_calls=2)
    thinking = [{"type": "thinking", "thinking": "…", "signature": "sig"}]
    provider = InMemoryProvider(
        responder=lambda c: "",
        tool_caller=lambda c: [
            ToolCall(id=uuid.uuid4().hex[:8], name="console.get_usage", arguments={})
        ],
    )
    original = provider.astream_with_tools

    async def with_thinking(**kwargs: Any) -> Any:
        async for kind, piece in original(**kwargs):
            if kind == "assistant":
                message = json.loads(piece)
                message["thinking_blocks"] = thinking
                yield ("assistant", json.dumps(message))
            else:
                yield (kind, piece)

    provider.astream_with_tools = with_thinking  # type: ignore[method-assign]
    await _run(provider, belt)

    last = provider.calls[-1].messages
    assistants = [m for m in last if m["role"] == "assistant"]
    assert assistants, "el mensaje del asistente desapareció"
    assert all(m.get("thinking_blocks") == thinking for m in assistants)
    for i, message in enumerate(last):
        if message["role"] == "tool":
            previous = last[i - 1]
            assert previous["role"] in {"assistant", "tool"}


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
    a la doceava llamada el usuario ya se fue.

    Doce pasos con catálogo, y **una más sin él**: el paso de cierre de R6
    (garantía E3). Un turno que se corta en seco es peor que uno que cuesta
    una llamada más y dice dónde quedó."""
    belt = FakeBelt(max_calls=999)
    provider = InMemoryProvider(
        responder=lambda c: "",
        tool_caller=lambda c: [
            ToolCall(id=uuid.uuid4().hex[:8], name="console.get_usage", arguments={})
        ],
    )
    await _run(provider, belt)
    # Todas declaran el catálogo (§19.1); lo que separa los pasos de trabajo
    # del cierre es ``tool_choice``, no la ausencia de herramientas.
    working = [c for c in provider.calls if _tool_choice(c) is None]
    assert len(working) == MAX_MODEL_STEPS
    assert len(provider.calls) == MAX_MODEL_STEPS + 1


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


# ── §19.1 · la última llamada declara las herramientas ─────────────────


async def test_the_closing_call_declares_tools_and_forbids_using_them() -> None:
    """Tercer 400 del mismo camino: ``messages`` lleva mensajes de asistente
    con ``tool_calls``, y Anthropic exige que la declaración de herramientas
    siga presente —

        Anthropic doesn't support tool calling without `tools=` param specified

    Quitar las herramientas no es la forma de decir "ya no llames a nada":
    la forma es ``tool_choice``. Y hace falta por sí misma, porque sin él el
    modelo puede volver a llamar y el paso de cierre deja de serlo."""
    belt = FakeBelt(max_calls=999)
    provider = InMemoryProvider(
        responder=lambda c: "",
        tool_caller=lambda c: [
            ToolCall(id=uuid.uuid4().hex[:8], name="console.get_usage", arguments={})
        ],
    )
    await _run(provider, belt)

    closing = provider.calls[-1]
    # El historial que se reenvía SÍ lleva uso de herramientas: es lo que
    # hace obligatoria la declaración.
    assert any(m.get("tool_calls") for m in closing.messages)
    assert closing.tools, "la llamada de cierre fue sin `tools`: 400 garantizado"
    assert _tool_choice(closing) == "none"


async def test_the_answer_after_an_action_declares_tools_too() -> None:
    """El 400 apareció justo aquí: en el turno de respuesta, después de
    aplicar y verificar. Es la misma llamada final con otro nombre."""
    from tests.unit.test_companion_action_graph import (
        FakeActionBelt,
        FakeProposal,
        base_state,
    )

    belt = FakeActionBelt(proposals=[FakeProposal()])
    provider = InMemoryProvider(responder=lambda c: "hecho")
    graph = build_companion_graph(
        provider=provider, model=MODEL, checkpointer=MemorySaver(), toolbelt=belt
    )
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    async for _ in graph.astream_events(base_state(), config=config, version="v2"):
        pass
    async for _ in graph.astream_events(
        Command(resume={"decision": "confirm", "note": None, "by": "u1", "at": "x"}),
        config=config,
        version="v2",
    ):
        pass

    final = provider.calls[-1]
    assert final.tools, "el turno de respuesta fue sin `tools`"
    assert _tool_choice(final) == "none"


async def test_without_a_catalogue_the_simple_path_is_kept() -> None:
    """Un grafo sin juego de herramientas (CO-01) no tiene nada que declarar
    y tampoco tiene historial de herramientas: no se le inventa un `tools`
    vacío, que es otro cuerpo de petición sin probar."""
    provider = InMemoryProvider(responder=lambda c: "no necesito leer nada")
    graph = build_companion_graph(provider=provider, model=MODEL, checkpointer=MemorySaver())
    async for _ in graph.astream_events(
        {"user_message": "hola", "history": []},
        config={"configurable": {"thread_id": str(uuid.uuid4())}},
        version="v2",
    ):
        pass

    assert provider.calls
    assert all(not call.tools for call in provider.calls)
    assert all(_tool_choice(call) is None for call in provider.calls)


# ── §18 · el pensamiento que no se puede devolver ──────────────────────


def test_summary_thinking_blocks_never_go_back_to_the_provider() -> None:
    """Con ``display: "summarized"`` el proveedor devuelve bloques de
    *resumen*: firma vacía y texto vacío. Anthropic los rechaza al recibirlos
    de vuelta —``Invalid signature in thinking block``— y ese 400 vive en la
    intersección de pensamiento activo + herramientas + segundo paso, que es
    la casilla que ningún proveedor guionizado ocupa."""
    from nexus_worker.runtime.companion.graph import _reproducible

    assistant = {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": "t1"}],
        "thinking_blocks": [
            {"type": "thinking", "thinking": "", "signature": ""},
            {"type": "thinking", "thinking": "", "signature": ""},
        ],
    }
    ready = _reproducible(assistant)

    assert "thinking_blocks" not in ready, "una lista vacía no es lo mismo que ausencia"
    assert ready["tool_calls"] == assistant["tool_calls"]
    assert assistant["thinking_blocks"], "no se muta el mensaje original"


def test_signed_thinking_blocks_come_back_verbatim() -> None:
    """La otra mitad, y es la que evita el 400 contrario: perderlos."""
    from nexus_worker.runtime.companion.graph import _reproducible

    signed = {"type": "thinking", "thinking": "primero leo el consumo", "signature": "AbC123=="}
    assistant = {"role": "assistant", "content": None, "thinking_blocks": [signed]}

    ready = _reproducible(assistant)

    assert ready["thinking_blocks"] == [signed]
    assert ready["thinking_blocks"][0] is signed, "byte a byte: el bloque no se reconstruye"


def test_a_mixed_message_keeps_only_what_is_reproducible() -> None:
    from nexus_worker.runtime.companion.graph import _reproducible

    signed = {"type": "thinking", "thinking": "…", "signature": "sig"}
    summary = {"type": "thinking", "thinking": "", "signature": ""}
    ready = _reproducible(
        {"role": "assistant", "content": None, "thinking_blocks": [summary, signed, summary]}
    )
    assert ready["thinking_blocks"] == [signed]


async def test_the_loop_sends_back_an_assistant_the_provider_accepts() -> None:
    """El filtro va donde se arma el mensaje que vuelve a ``messages``."""
    belt = FakeBelt()
    provider = InMemoryProvider(
        responder=lambda c: "ok",
        tool_caller=_steps([ToolCall(id="t1", name="console.get_usage", arguments={})]),
    )
    original = provider.astream_with_tools

    async def summarised(**kwargs: Any) -> Any:
        async for kind, piece in original(**kwargs):
            if kind == "assistant":
                message = json.loads(piece)
                message["thinking_blocks"] = [{"type": "thinking", "thinking": "", "signature": ""}]
                yield ("assistant", json.dumps(message))
            else:
                yield (kind, piece)

    provider.astream_with_tools = summarised  # type: ignore[method-assign]
    events, _final = await _run(provider, belt)

    second = provider.calls[1].messages
    assistant = next(m for m in second if m["role"] == "assistant")
    assert "thinking_blocks" not in assistant
    # Y el pensamiento que se pinta no depende de esto: sale del stream.
    assert [n for n, _ in events if n == "tool.call.started"]


# ── §17 · el nombre de cable ───────────────────────────────────────────


def test_every_catalogue_tool_has_a_wire_name_the_provider_accepts() -> None:
    """Anthropic rechaza el punto en ``tools[].name``, y las 28 herramientas
    del catálogo lo llevan. Sin la traducción, **ningún turno con
    herramientas funciona contra el proveedor real** — y no lo ve ninguna
    suite, porque el proveedor guionizado acepta cualquier nombre."""
    from nexus_worker.runtime.companion.tools import WIRE_NAME_PATTERN, wire_tools

    from nexus_api.companion.tools.catalog import tool_specs

    specs = tool_specs(mode="build")
    assert specs, "el catálogo no puede estar vacío"
    # El punto es justamente lo que rompe: si un día desaparece del catálogo,
    # este test deja de medir nada y hay que enterarse.
    assert any("." in s["function"]["name"] for s in specs)

    translated, back = wire_tools(specs)
    for original, wired in zip(specs, translated, strict=True):
        wire = wired["function"]["name"]
        assert WIRE_NAME_PATTERN.match(wire), f"el proveedor rechazaría {wire!r}"
        assert back[wire] == original["function"]["name"], "la vuelta atrás no es exacta"
    assert len(back) == len(specs), "dos herramientas caen en el mismo nombre de cable"


def test_a_collision_breaks_when_the_table_is_built() -> None:
    """Al arrancar el turno, no en producción con una llamada despachada a
    la herramienta equivocada."""
    from nexus_worker.runtime.companion.tools import WireNameCollision, wire_tools

    def spec(name: str) -> dict[str, Any]:
        return {"type": "function", "function": {"name": name, "description": "", "parameters": {}}}

    with pytest.raises(WireNameCollision):
        wire_tools([spec("console.get_usage"), spec("console__get_usage")])


async def test_the_provider_sees_wire_names_and_the_drawer_sees_catalogue_names() -> None:
    """Los dos sentidos, y de forma consistente. El resto del sistema —los
    eventos, la cita, el ejecutor— nunca ve el nombre de cable."""
    belt = FakeBelt()
    provider = InMemoryProvider(
        responder=lambda c: "listo",
        tool_caller=_steps([ToolCall(id="t1", name="console__get_usage", arguments={})]),
    )
    events, _final = await _run(provider, belt)

    # Lo que se declara al proveedor.
    offered = {t["function"]["name"] for call in provider.calls for t in (call.tools or ())}
    assert offered == {"console__get_usage"}

    # Lo que ve el ejecutor y lo que ve el cajón: el nombre del catálogo.
    assert [name for name, _ in belt.calls] == ["console.get_usage"]
    started = next(d for n, d in events if n == "tool.call.started")
    assert started["name"] == "console.get_usage"
    completed = next(d for n, d in events if n == "tool.call.completed")
    assert completed["name"] == "console.get_usage"


async def test_the_tool_result_matches_the_name_the_model_emitted() -> None:
    """Un mensaje de asistente cuyo ``tool_use.name`` no coincida con su
    ``tool_result`` correlativo es otro 400 — y de los que no salen en
    ningún test con proveedor guionizado."""
    belt = FakeBelt()
    provider = InMemoryProvider(
        responder=lambda c: "ok",
        tool_caller=_steps([ToolCall(id="t1", name="console__get_usage", arguments={})]),
    )
    await _run(provider, belt)

    second = provider.calls[1].messages
    assistant = next(m for m in second if m["role"] == "assistant")
    tool_msg = next(m for m in second if m["role"] == "tool")
    assert assistant["tool_calls"][0]["function"]["name"] == tool_msg["name"]
    assert "." not in tool_msg["name"]


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
