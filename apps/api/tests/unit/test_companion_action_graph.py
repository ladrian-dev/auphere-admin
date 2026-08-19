"""El carril de HITL del grafo, y la corrección C2 (CO-04).

Lo que se prueba es el **motor**: que la persistencia y el evento van en el
nodo anterior al ``interrupt()``, que reanudar no duplica nada, que la
secuencia de eventos es la del §4.3 del contrato y que un turno que solo
leyó no pasa por aquí.

El proveedor es ``InMemoryProvider`` y el puerto de acciones un doble que
cuenta llamadas. Ni red, ni base de datos, ni LangGraph de verdad más allá
de lo que hace falta para que ``interrupt()`` funcione — que es un
``MemorySaver``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from nexus_worker.runtime.companion import build_companion_graph
from nexus_worker.runtime.companion.state import PHASE_LABELS
from nexus_worker.runtime.llm import InMemoryProvider

pytestmark = pytest.mark.unit

MODEL = "anthropic/claude-sonnet-4-6"


@dataclass
class FakeProposal:
    kind: str = "prompt"
    title: str = "Ajustar el prompt de boreal"
    client_ref: str | None = "boreal"
    risk: str = "low"


@dataclass
class FakeActionBelt:
    """Doble del juego de herramientas CON camino de escritura.

    Cuenta lo que importa para C2: cuántas veces se persistió la acción y
    cuántas se aplicó. Si el nodo del ``interrupt()`` hiciera algo más que
    interrumpir, estos contadores llegarían a dos.
    """

    proposals: list[FakeProposal] = field(default_factory=list)
    staged: int = 0
    applied: int = 0
    verified: int = 0
    verify_result: dict[str, Any] = field(
        default_factory=lambda: {
            "action_id": "a1",
            "checks": [{"name": "draft_prompt", "expected": "x", "actual": "x", "ok": True}],
            "ok": True,
        }
    )
    apply_ok: bool = True
    action_id: str = "11111111-1111-4111-8111-111111111111"

    # ── Toolbelt ───────────────────────────────────────────────────────
    calls_made: int = 0

    @property
    def calls_left(self) -> int:
        return 25 - self.calls_made

    @property
    def reads_done(self) -> int:
        return 1

    def specs(self) -> list[dict[str, Any]]:
        return []

    async def call(self, name: str, arguments: dict[str, Any]) -> Any:  # pragma: no cover
        raise AssertionError("el nodo execute usa apply_confirmed, no call")

    # ── ActionPort ─────────────────────────────────────────────────────
    @property
    def pending(self) -> list[FakeProposal]:
        return self.proposals

    def plan_steps(self) -> list[dict[str, Any]]:
        return [
            {
                "index": i + 1,
                "kind": p.kind,
                "tool": f"console.propose_{p.kind}",
                "title": p.title,
                "client_ref": p.client_ref,
                "reversible": True,
            }
            for i, p in enumerate(self.proposals)
        ]

    def plan_risk(self) -> str:
        return "low"

    async def stage(self, step_index: int) -> dict[str, Any] | None:
        if not self.proposals:
            return None
        self.staged += 1
        p = self.proposals[0]
        return {
            "action_id": self.action_id,
            "kind": p.kind,
            "title": p.title,
            "preview": {"client_ref": p.client_ref, "summary": "1 línea"},
            "diff": [{"op": "add", "line": 1, "after": "hola"}],
            "impact": [{"key": "publishes", "value": "false", "severity": "info"}],
            "expires_at": "2026-08-18T14:33:00+00:00",
        }

    async def apply_confirmed(self, action_id: Any) -> Any:
        self.applied += 1

        @dataclass
        class Result:
            ok: bool

        return Result(ok=self.apply_ok)

    async def verify(self, action_id: Any) -> dict[str, Any] | None:
        self.verified += 1
        return self.verify_result


@dataclass
class FakeReadBelt:
    """Doble SIN camino de escritura: el juego de CO-02, intacto."""

    calls_made: int = 0

    @property
    def calls_left(self) -> int:
        return 25

    @property
    def reads_done(self) -> int:
        return 1

    def specs(self) -> list[dict[str, Any]]:
        return []

    async def call(self, name: str, arguments: dict[str, Any]) -> Any:  # pragma: no cover
        raise AssertionError("no debería llamarse")


def graph_with(belt: Any, *, answer: str = "listo") -> Any:
    provider = InMemoryProvider(responder=lambda _call: answer)
    return build_companion_graph(
        provider=provider, model=MODEL, checkpointer=MemorySaver(), toolbelt=belt
    )


def base_state() -> dict[str, Any]:
    return {
        "thread_id": str(uuid.uuid4()),
        "principal": {"role": "owner", "partner": "p", "permissions": []},
        "page_context": None,
        "history": [],
        "user_message": "cambia el prompt",
        "total_input_tokens": 0,
        "total_output_tokens": 0,
    }


async def run(graph: Any, entry: Any, config: dict[str, Any]) -> list[tuple[str, Any]]:
    """Los eventos personalizados del turno, en orden."""
    seen: list[tuple[str, Any]] = []
    async for event in graph.astream_events(entry, config=config, version="v2"):
        if event.get("event") == "on_custom_event":
            seen.append((str(event.get("name")), event.get("data")))
    return seen


# ── C2 · el nodo del interrupt no hace nada más ────────────────────────


async def test_the_turn_stops_at_the_interrupt_and_persists_exactly_once() -> None:
    belt = FakeActionBelt(proposals=[FakeProposal()])
    graph = graph_with(belt)
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    events = await run(graph, base_state(), config)
    names = [n for n, _ in events]

    assert "plan.proposed" in names and "hitl.requested" in names
    assert belt.staged == 1
    # El grafo está parado: nada de lo que viene después del ``interrupt()``
    # ha corrido todavía.
    assert belt.applied == 0 and belt.verified == 0
    assert "hitl.resolved" not in names and "verify.result" not in names


async def test_resuming_does_not_persist_the_action_a_second_time() -> None:
    """**La corrección C2, medida.** ``interrupt()`` reanuda re-ejecutando
    su nodo desde la primera línea; con la persistencia dentro, ``staged``
    llegaría a dos y la fila entraría duplicada en cada confirmación."""
    belt = FakeActionBelt(proposals=[FakeProposal()])
    graph = graph_with(belt)
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    await run(graph, base_state(), config)
    assert belt.staged == 1

    after = await run(
        graph,
        Command(resume={"decision": "confirm", "note": None, "by": "u1", "at": "2026-08-18"}),
        config,
    )
    names = [n for n, _ in after]

    assert belt.staged == 1, "la acción se persistió dos veces: C2 rota"
    # Y el evento tampoco se repite: el cajón no pinta dos tarjetas.
    assert "hitl.requested" not in names
    assert "plan.proposed" not in names


async def test_the_resume_run_follows_the_contract_sequence() -> None:
    """§4.3: ``hitl.resolved`` primero, luego ejecutar, luego verificar,
    luego responder. La interfaz pinta en ese orden."""
    belt = FakeActionBelt(proposals=[FakeProposal()])
    graph = graph_with(belt)
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    await run(graph, base_state(), config)

    events = await run(
        graph,
        Command(resume={"decision": "confirm", "note": None, "by": "u1", "at": "2026-08-18"}),
        config,
    )
    names = [n for n, _ in events]

    assert names[0] == "hitl.resolved"
    order = [n for n in names if n in {"hitl.resolved", "verify.result", "text.delta"}]
    assert order[0] == "hitl.resolved"
    assert order.index("verify.result") < order.index("text.delta")
    phases = [d.get("phase") for n, d in events if n == "phase.changed"]
    assert phases[: phases.index("respond") + 1] == ["execute", "verify", "respond"]
    assert belt.applied == 1 and belt.verified == 1


async def test_the_interrupt_node_is_a_single_unconditional_call() -> None:
    """Se lee del código, porque es la única forma de fijar «no hace nada
    más». Un ``try/except`` alrededor se tragaría la pausa —``interrupt()``
    pausa lanzando— y el grafo seguiría de largo como si le hubieran dicho
    que sí."""
    import inspect

    from nexus_worker.runtime.companion.graph import await_confirmation

    body = inspect.getsource(await_confirmation)
    code = body.split('"""')[2]  # lo que hay tras el docstring

    assert code.count("interrupt(") == 1, "una sola llamada, y en orden estable"
    assert "try" not in code and "except" not in code
    assert "if " not in code.split("interrupt(")[0], "la llamada es incondicional"


# ── decisiones que no aplican ──────────────────────────────────────────


@pytest.mark.parametrize("decision", ["cancel", "edit"])
async def test_a_refusal_applies_nothing_and_returns_the_reason(decision: str) -> None:
    """El ``deny_message`` de Managed Agents: el motivo vuelve al modelo
    para que ajuste el plan, no solo para que pare."""
    belt = FakeActionBelt(proposals=[FakeProposal()])
    graph = graph_with(belt)
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    await run(graph, base_state(), config)

    events = await run(
        graph,
        Command(
            resume={
                "decision": decision,
                "note": "Mejor sin tocar el horario.",
                "by": "u1",
                "at": "2026-08-18",
            }
        ),
        config,
    )
    resolved = next(d for n, d in events if n == "hitl.resolved")

    assert resolved["decision"] == decision
    assert resolved["note"] == "Mejor sin tocar el horario."
    assert belt.applied == 0
    # Ni se verifica: verificar algo que nadie aplicó daría una tabla en
    # rojo que no significa nada, y el rojo tiene que seguir significando.
    assert belt.verified == 0
    assert "verify.result" not in [n for n, _ in events]


async def test_a_failed_apply_skips_verification_and_says_so() -> None:
    """R4: parar al primer fallo. Verificar tras un fallo produciría rojo
    sobre rojo y taparía cuál fue la causa."""
    belt = FakeActionBelt(proposals=[FakeProposal()], apply_ok=False)
    graph = graph_with(belt)
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    await run(graph, base_state(), config)

    events = await run(
        graph,
        Command(resume={"decision": "confirm", "note": None, "by": "u1", "at": "x"}),
        config,
    )
    assert belt.applied == 1 and belt.verified == 0
    assert "verify.result" not in [n for n, _ in events]


# ── el carril no existe cuando no hay nada que escribir ────────────────


async def test_a_read_only_turn_never_sees_a_confirmation_card() -> None:
    """Lo decide el MOTOR mirando si hay propuesta, no el modelo diciendo
    «y ahora confírmamelo»."""
    belt = FakeActionBelt(proposals=[])
    graph = graph_with(belt)
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    names = [n for n, _ in await run(graph, base_state(), config)]

    assert "hitl.requested" not in names and "plan.proposed" not in names
    assert belt.staged == 0


async def test_a_read_only_toolbelt_compiles_the_co_02_graph_unchanged() -> None:
    """CO-01 y CO-02 tienen que seguir funcionando exactamente igual: sin
    nodos de HITL y, sobre todo, sin un ``interrupt()`` que nadie va a
    reanudar."""
    graph = graph_with(FakeReadBelt())
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    names = [n for n, _ in await run(graph, base_state(), config)]

    assert "hitl.requested" not in names
    assert "text.delta" in names


# ── las cuatro fases nuevas ────────────────────────────────────────────


def test_the_four_new_phases_have_a_label() -> None:
    """El enum del §2.8 del contrato, cerrado. La interfaz mantiene su
    propia tabla de traducción, pero un ``phase`` sin entrada aquí es un
    identificador que nadie declaró."""
    for phase in ("intake", "plan", "execute", "verify"):
        assert phase in PHASE_LABELS
    assert set(PHASE_LABELS) == {
        "understand",
        "investigate",
        "intake",
        "plan",
        "awaiting",
        "execute",
        "verify",
        "respond",
        "done",
    }
