"""La máquina de estados del §7 y la garantía E2 (CO-06).

El modelo elige el CONTENIDO de cada fase; que la fase **ocurra** lo decide
el grafo. Aquí se fija que ocurre en el orden del §7 y que ``phase.changed``
no salta hacia atrás dentro de un run, por ningún camino: solo lectura,
expediente incompleto, confirmación, cancelación, fallo al aplicar y
publicación.

También se fija lo que la máquina destapó al escribirla: que un turno nuevo
no arrastra el ``hitl`` del anterior. El checkpointer está indexado por hilo,
así que sin limpiarlo el turno siguiente respondía dos veces.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from nexus_worker.runtime.companion import build_companion_graph
from nexus_worker.runtime.companion.state import (
    PHASE_LABELS,
    PHASE_ORDER,
    PHASE_RANK,
    PhaseTracker,
    PhaseViolation,
)
from nexus_worker.runtime.llm import InMemoryProvider, ToolCall

from tests.unit.test_companion_action_graph import (
    FakeActionBelt,
    FakeProposal,
    base_state,
)

pytestmark = pytest.mark.unit

MODEL = "anthropic/claude-sonnet-4-6"

CONFIRM = {"decision": "confirm", "note": None, "by": "u1", "at": "2026-08-19"}


def _phases(events: list[tuple[str, dict[str, Any]]]) -> list[str]:
    return [d["phase"] for n, d in events if n == "phase.changed"]


def _assert_monotonic(phases: list[str]) -> None:
    """**Garantía E2.** Todas del enum y sin retroceder."""
    assert phases, "un run sin ninguna fase no dice nada"
    for phase in phases:
        assert phase in PHASE_RANK, f"fase fuera del enum cerrado: {phase!r}"
    ranks = [PHASE_RANK[p] for p in phases]
    assert ranks == sorted(ranks), f"la fase saltó hacia atrás: {phases}"
    assert len(set(phases)) == len(phases), f"una fase se emitió dos veces: {phases}"


async def _run(graph: Any, entry: Any, config: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    seen: list[tuple[str, dict[str, Any]]] = []
    async for ev in graph.astream_events(entry, config=config, version="v2"):
        if ev.get("event") == "on_custom_event":
            seen.append((str(ev.get("name")), dict(ev.get("data") or {})))
    return seen


def _graph(belt: Any, provider: InMemoryProvider, saver: MemorySaver | None = None) -> Any:
    return build_companion_graph(
        provider=provider, model=MODEL, checkpointer=saver or MemorySaver(), toolbelt=belt
    )


# ── el enum ────────────────────────────────────────────────────────────


def test_the_enum_is_the_ten_of_the_contract_in_order() -> None:
    assert PHASE_ORDER == (
        "understand",
        "investigate",
        "intake",
        "plan",
        "awaiting",
        "execute",
        "verify",
        "publish",
        "respond",
        "done",
    )
    assert set(PHASE_ORDER) == set(PHASE_LABELS)


# ── el tracker, a solas ────────────────────────────────────────────────


async def test_a_backwards_phase_is_never_emitted() -> None:
    """Es E2 hecha mecanismo. El bucle de herramientas pedía volver a
    *Investigando* después de escribir; ahora esa petición se ignora en vez
    de producir un salto hacia atrás en el timeline."""
    seen: list[str] = []

    async def emit(_event: str, payload: dict[str, Any]) -> None:
        seen.append(str(payload["phase"]))

    tracker = PhaseTracker(emit)
    assert await tracker.enter("understand") is True
    assert await tracker.enter("investigate") is True
    assert await tracker.enter("respond") is True
    assert await tracker.enter("investigate") is False
    assert seen == ["understand", "investigate", "respond"]
    assert tracker.current == "respond"


async def test_the_same_phase_twice_does_not_make_the_pill_blink() -> None:
    seen: list[str] = []

    async def emit(_event: str, payload: dict[str, Any]) -> None:
        seen.append(str(payload["phase"]))

    tracker = PhaseTracker(emit)
    await tracker.enter("investigate")
    assert await tracker.enter("investigate") is False
    assert seen == ["investigate"]


async def test_writing_without_having_asked_is_an_engine_failure() -> None:
    """R3 en el motor: no se entra en ``execute`` sin haber pasado por
    ``awaiting``. Hoy es inalcanzable por construcción del grafo, y esa es
    la razón de tenerlo — un reordenado de nodos que se saltara la
    confirmación rompería el turno en vez de escribir sin preguntar."""

    async def emit(_event: str, _payload: dict[str, Any]) -> None:  # pragma: no cover
        return None

    tracker = PhaseTracker(emit, current="verify")
    with pytest.raises(PhaseViolation):
        await tracker.enter("execute")

    ok = PhaseTracker(emit, current="awaiting")
    assert await ok.enter("execute") is True


async def test_an_unknown_phase_is_refused() -> None:
    async def emit(_event: str, _payload: dict[str, Any]) -> None:  # pragma: no cover
        return None

    with pytest.raises(PhaseViolation):
        await PhaseTracker(emit).enter("thinking")


# ── E2 en cada camino del grafo ────────────────────────────────────────


async def test_a_read_only_turn_is_monotonic() -> None:
    belt = FakeActionBelt(proposals=[])
    graph = _graph(belt, InMemoryProvider(responder=lambda _c: "listo"))
    events = await _run(graph, base_state(), {"configurable": {"thread_id": str(uuid.uuid4())}})
    _assert_monotonic(_phases(events))


async def test_a_turn_with_tools_never_goes_back_to_investigating() -> None:
    """El caso que rompía E2: el modelo escribe un preámbulo y después pide
    herramientas. Antes eso emitía ``respond`` y luego ``investigate``.

    El juego es de solo lectura a propósito: ``FakeActionBelt`` no sabe
    ejecutar herramientas, y usarlo aquí mediría otra cosa."""
    belt = BudgetBelt()
    called = {"n": 0}

    def tool_caller(_call: Any) -> list[ToolCall]:
        if called["n"] >= 2:
            return []
        called["n"] += 1
        return [ToolCall(id=f"t{called['n']}", name="console.get_usage", arguments={})]

    graph = _graph(
        belt, InMemoryProvider(responder=lambda _c: "voy a mirarlo", tool_caller=tool_caller)
    )
    events = await _run(graph, base_state(), {"configurable": {"thread_id": str(uuid.uuid4())}})
    phases = _phases(events)

    _assert_monotonic(phases)
    assert phases == ["understand", "investigate", "respond"]


async def test_the_hitl_lane_is_monotonic_across_both_runs() -> None:
    """El run aparcado y el de continuación son dos tramos de la misma
    máquina: ``awaiting`` cierra el primero y ``execute`` abre el segundo."""
    belt = FakeActionBelt(proposals=[FakeProposal()])
    graph = _graph(belt, InMemoryProvider(responder=lambda _c: "hecho"))
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    first = _phases(await _run(graph, base_state(), config))
    assert first == ["understand", "investigate", "plan", "awaiting"]
    _assert_monotonic(first)

    second = _phases(await _run(graph, Command(resume=CONFIRM), config))
    assert second == ["execute", "verify", "respond"]
    _assert_monotonic(first + second)


@pytest.mark.parametrize("decision", ["cancel", "edit"])
async def test_a_refusal_is_monotonic(decision: str) -> None:
    belt = FakeActionBelt(proposals=[FakeProposal()])
    graph = _graph(belt, InMemoryProvider(responder=lambda _c: "vale"))
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    first = _phases(await _run(graph, base_state(), config))
    second = _phases(
        await _run(graph, Command(resume={**CONFIRM, "decision": decision, "note": "no"}), config)
    )
    assert second == ["respond"]
    _assert_monotonic(first + second)


async def test_a_failed_apply_is_monotonic() -> None:
    belt = FakeActionBelt(proposals=[FakeProposal()], apply_ok=False)
    graph = _graph(belt, InMemoryProvider(responder=lambda _c: "no se pudo"))
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    first = _phases(await _run(graph, base_state(), config))
    second = _phases(await _run(graph, Command(resume=CONFIRM), config))
    assert second == ["execute", "respond"]
    _assert_monotonic(first + second)


# ── la fase publish (§2 del contrato v2) ───────────────────────────────


async def test_publishing_gets_its_own_phase_after_a_green_verify() -> None:
    belt = FakeActionBelt(proposals=[FakeProposal(kind="publish", title="Publicar la v8")])
    belt.verify_result = {
        "action_id": "a1",
        "checks": [{"name": "active_version", "expected": "8", "actual": "8", "ok": True}],
        "ok": True,
    }
    graph = _graph(belt, InMemoryProvider(responder=lambda _c: "publicada"))
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    await _run(graph, base_state(), config)

    phases = _phases(await _run(graph, Command(resume=CONFIRM), config))
    assert phases == ["execute", "verify", "publish", "respond"]


async def test_a_turn_that_only_changes_a_prompt_never_enters_publish() -> None:
    """El contrato es literal en esto: *un turno que solo cambia un prompt
    nunca entra en `publish`*."""
    belt = FakeActionBelt(proposals=[FakeProposal(kind="prompt")])
    graph = _graph(belt, InMemoryProvider(responder=lambda _c: "cambiado"))
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    await _run(graph, base_state(), config)

    phases = _phases(await _run(graph, Command(resume=CONFIRM), config))
    assert "publish" not in phases


async def test_a_red_verify_does_not_reach_publish() -> None:
    """*solo si 7 fue verde* (§7, paso 8)."""
    belt = FakeActionBelt(proposals=[FakeProposal(kind="publish")])
    belt.verify_result = {
        "action_id": "a1",
        "checks": [{"name": "active_version", "expected": "8", "actual": "7", "ok": False}],
        "ok": False,
    }
    graph = _graph(belt, InMemoryProvider(responder=lambda _c: "no cuadra"))
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    await _run(graph, base_state(), config)

    phases = _phases(await _run(graph, Command(resume=CONFIRM), config))
    assert "publish" not in phases
    assert phases == ["execute", "verify", "respond"]


async def test_the_publish_phase_tells_the_model_that_publishing_is_apart() -> None:
    """R5 · el motor no encadena la publicación solo: la ofrece."""
    belt = FakeActionBelt(proposals=[FakeProposal(kind="publish")])
    provider = InMemoryProvider(responder=lambda _c: "publicada")
    graph = _graph(belt, provider)
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    await _run(graph, base_state(), config)
    await _run(graph, Command(resume=CONFIRM), config)

    briefs = [
        m
        for call in provider.calls
        for m in call.messages
        if m["role"] == "system" and "acto APARTE" in str(m["content"])
    ]
    assert briefs


# ── R4 · lo que quedó aplicado, dicho ──────────────────────────────────


async def test_a_failed_apply_is_reported_as_nothing_applied() -> None:
    """R4 pedía dos cosas y solo estaba la primera: parar, **y decirlo**.
    "Algo salió mal" es lo que obliga a la persona a ir a mirarlo a mano."""
    belt = FakeActionBelt(proposals=[FakeProposal()], apply_ok=False)
    provider = InMemoryProvider(responder=lambda _c: "no se aplicó")
    graph = _graph(belt, provider)
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    await _run(graph, base_state(), config)
    await _run(graph, Command(resume=CONFIRM), config)

    briefs = [
        m
        for call in provider.calls
        for m in call.messages
        if m["role"] == "system" and "NO SE APLICÓ" in str(m["content"])
    ]
    assert briefs


# ── el rastro del run anterior ─────────────────────────────────────────


async def test_a_new_turn_does_not_inherit_the_previous_hitl() -> None:
    """El defecto que destapó escribir la máquina, medido.

    El checkpointer está indexado por ``thread_id``, así que ``hitl`` y
    ``verify`` de una confirmación anterior seguían en el estado al empezar
    el turno siguiente — y el nodo de cierre entraba por el camino de
    continuación: respondía **dos veces**, una por el bucle y otra
    informando de una acción que ya se había contado.
    """
    belt = FakeActionBelt(proposals=[FakeProposal()])
    provider = InMemoryProvider(responder=lambda _c: "hecho")
    graph = _graph(belt, provider)
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    await _run(graph, base_state(), config)
    await _run(graph, Command(resume=CONFIRM), config)

    belt.proposals = []
    third = await _run(graph, {**base_state(), "user_message": "¿y cuántos clientes hay?"}, config)

    snapshot = await graph.aget_state(config)
    assert not snapshot.values.get("hitl")
    assert not snapshot.values.get("verify")
    assert not snapshot.values.get("action_id")

    # Un solo mensaje del asistente en el turno, no dos.
    message_ids = {d["message_id"] for n, d in third if n == "text.delta"}
    assert len(message_ids) == 1
    assert _phases(third) == ["understand", "investigate", "respond"]


async def test_the_resume_run_keeps_what_it_needs() -> None:
    """La limpieza es del turno nuevo, no del run de continuación:
    ``understand`` no corre en un ``resume``."""
    belt = FakeActionBelt(proposals=[FakeProposal()])
    graph = _graph(belt, InMemoryProvider(responder=lambda _c: "hecho"))
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    await _run(graph, base_state(), config)

    events = await _run(graph, Command(resume=CONFIRM), config)
    resolved = next(d for n, d in events if n == "hitl.resolved")
    assert resolved["decision"] == "confirm"
    assert belt.applied == 1 and belt.verified == 1


async def test_the_expediente_survives_the_run_cleanup() -> None:
    """Lo que se limpia es el rastro del run; el expediente es del HILO."""
    belt = FakeActionBelt(proposals=[])
    graph = _graph(belt, InMemoryProvider(responder=lambda _c: "ok"))
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    await _run(graph, base_state(), config)
    await graph.aupdate_state(
        config, {"intake": {"answers": {"create_client": {"name": "Boreal"}}, "asked": {}}}
    )
    await _run(graph, {**base_state(), "user_message": "otra cosa"}, config)

    snapshot = await graph.aget_state(config)
    assert snapshot.values["intake"]["answers"]["create_client"]["name"] == "Boreal"


# ── E3 · el turno que se agota cierra ──────────────────────────────────


@dataclass
class BudgetBelt:
    """Doble de solo lectura con un catálogo cualquiera."""

    calls_made: int = 0
    calls: list[str] = field(default_factory=list)

    @property
    def calls_left(self) -> int:
        return 999

    @property
    def reads_done(self) -> int:
        return 1

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

    async def call(self, name: str, arguments: dict[str, Any]) -> Any:
        self.calls_made += 1
        self.calls.append(name)

        @dataclass
        class Result:
            name: str
            label: str
            ok: bool
            content: str
            latency_ms: int = 1
            error_code: str | None = None
            citation: Any = None

        return Result(name, name, True, "{}")


def _never_finishes() -> InMemoryProvider:
    """Un modelo que pide herramientas y no escribe nunca la respuesta."""
    return InMemoryProvider(
        responder=lambda _c: "",
        tool_caller=lambda _c: [
            ToolCall(id=uuid.uuid4().hex[:8], name="console.get_usage", arguments={})
        ],
    )


async def test_an_exhausted_turn_closes_instead_of_going_mute() -> None:
    """**Garantía E3.** Al agotarse, el turno cierra y reporta dónde está.
    Antes devolvía una respuesta vacía, que en el cajón es una burbuja en
    blanco."""
    belt = BudgetBelt()
    provider = _never_finishes()
    graph = _graph(belt, provider)
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    events = await _run(graph, base_state(), config)
    snapshot = await graph.aget_state(config)

    assert snapshot.values["answer"].strip(), "el turno se cortó sin decir nada"
    assert [n for n, _ in events if n == "text.delta"]
    _assert_monotonic(_phases(events))
    assert _phases(events)[-1] == "respond"


async def test_the_closing_step_declares_tools_but_forbids_them() -> None:
    """No se empieza nada nuevo — pero eso **no** es ir sin catálogo.

    Ir sin catálogo con un historial que lleva ``tool_calls`` es el 400 del
    §19.1. La forma de decir "ya no llames a nada" es ``tool_choice``, y hace
    falta por sí misma: sin él el modelo puede volver a llamar y el paso de
    cierre deja de serlo."""
    provider = _never_finishes()
    graph = _graph(BudgetBelt(), provider)
    await _run(graph, base_state(), {"configurable": {"thread_id": str(uuid.uuid4())}})

    last = provider.calls[-1]
    assert last.tools, "la llamada de cierre fue sin `tools`: 400 garantizado"
    assert (last.extra or {}).get("tool_choice") == "none"
    assert any(m["role"] == "system" and "Cierra ahora" in str(m["content"]) for m in last.messages)


async def test_the_close_survives_a_model_that_says_nothing() -> None:
    """E3 no puede depender de que el proveedor coopere."""
    provider = InMemoryProvider(
        responder=lambda _c: "",
        tool_caller=lambda _c: [
            ToolCall(id=uuid.uuid4().hex[:8], name="console.get_usage", arguments={})
        ],
    )
    graph = _graph(BudgetBelt(), provider)
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    await _run(graph, base_state(), config)

    answer = (await graph.aget_state(config)).values["answer"]
    assert "sin margen" in answer
    # Sin cifras: un número aquí marcaría de ``unsupported`` una frase que
    # escribió el motor.
    assert not any(ch.isdigit() for ch in answer)


async def test_the_token_gate_stops_before_the_next_model_call() -> None:
    """La puerta va ANTES de la llamada, no después de sumar: es lo único
    que garantiza que quede margen para cerrar."""
    from nexus_worker.runtime.companion.graph import MAX_MODEL_STEPS, TURN_TOKEN_BUDGET

    provider = _never_finishes()
    # Cada paso consume el presupuesto entero: al segundo, la puerta salta.
    provider.stream_usage = {"prompt_tokens": TURN_TOKEN_BUDGET, "completion_tokens": 0}
    graph = _graph(BudgetBelt(), provider)
    await _run(graph, base_state(), {"configurable": {"thread_id": str(uuid.uuid4())}})

    # Los pasos de trabajo son los que NO llevan ``tool_choice``: desde el
    # §19.1 el cierre también declara el catálogo.
    working = [c for c in provider.calls if (c.extra or {}).get("tool_choice") is None]
    assert len(working) == 1, "siguió llamando al modelo con el presupuesto agotado"
    assert len(working) < MAX_MODEL_STEPS
    assert (provider.calls[-1].extra or {}).get("tool_choice") == "none", "no hubo cierre"
