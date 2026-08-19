"""El conductor de un caso del Companion (CO-07).

Corre el caso por el **grafo de verdad** (``build_companion_graph``) con el
**juego de herramientas de verdad** (``CompanionToolbelt`` contra la
aplicación ASGI en proceso). Lo único de mentira es el modelo, y esa es la
línea que define el modo offline:

    el modo offline no prueba que el modelo se porte bien; prueba que aunque
    se porte mal no pueda hacer daño, y que el medidor que lo vigila sigue
    midiendo.

Lo que sí es real en offline, y es lo que hace que el dataset valga algo:

- las lecturas van al router ``/console/*`` real, con el principal real,
  contra la base real — así que "respuesta conocida" significa que el dato
  salió de la base;
- el 404 del cliente de otro partner lo produce ``client_scope``, no un
  doble;
- el veredicto de R1 lo calcula ``grounding.is_unsupported``, la misma
  función que corre en producción;
- los topes (llamadas por turno, lectura repetida) los aplica el ejecutor
  real.

En modo live se sustituye el proveedor guionizado por el de LiteLLM y
entonces la trayectoria del caso se descarta: lo que se juzga es lo que
produzca el modelo.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from nexus_api.services.evals.companion.dataset import CompanionCase, Step


@dataclass
class ScriptedModel:
    """Proveedor guionizado: devuelve la trayectoria del caso, paso a paso.

    Un paso = una llamada al proveedor. Los pasos de herramienta emiten la
    llamada; el paso de texto no emite ninguna y escribe, que es como el
    bucle del grafo sabe que el turno terminó.
    """

    steps: tuple[Step, ...]
    index: int = 0
    #: Lo que devolvió cada llamada al proveedor, para el informe.
    seen: list[str] = field(default_factory=list)

    def _next(self) -> Step | None:
        if self.index >= len(self.steps):
            return None
        step = self.steps[self.index]
        self.index += 1
        return step

    def tool_caller(self, _call: Any) -> list[Any]:
        from nexus_worker.runtime.llm import ToolCall

        step = self._peek_tool()
        if step is None:
            return []
        self.index += 1
        self.seen.append(f"tool:{step.tool}")
        return [ToolCall(id=f"call_{self.index}", name=step.tool or "", arguments=dict(step.args))]

    def _peek_tool(self) -> Step | None:
        if self.index >= len(self.steps):
            return None
        step = self.steps[self.index]
        return step if step.is_tool else None

    def responder(self, _call: Any) -> str:
        step = self._next()
        if step is None or step.text is None:
            return ""
        self.seen.append("text")
        return step.text


@dataclass
class TurnResult:
    """Lo que pasó de verdad en el turno."""

    answer: str
    reads_ok: int
    calls_made: int
    unsupported: bool
    outcomes: list[Any] = field(default_factory=list)
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    phases: list[str] = field(default_factory=list)

    @property
    def last_body(self) -> str:
        return str(self.outcomes[-1].content) if self.outcomes else ""

    @property
    def last_error_code(self) -> str | None:
        return self.outcomes[-1].error_code if self.outcomes else None

    @property
    def tool_calls(self) -> list[dict[str, Any]]:
        """En la forma que espera el aplicador compartido de aserciones."""
        return [{"name": o.name} for o in self.outcomes]


class _RecordingBelt:
    """Envuelve el juego de herramientas real y guarda cada resultado.

    Delega todo. Existe porque el grafo no devuelve los ``ToolOutcome`` —
    los convierte en mensajes para el modelo— y las aserciones necesitan el
    código de error y el cuerpo tal cual salieron.
    """

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.outcomes: list[Any] = []

    @property
    def calls_left(self) -> int:
        return int(self.inner.calls_left)

    @property
    def reads_done(self) -> int:
        return int(self.inner.reads_done)

    @property
    def calls_made(self) -> int:
        return int(getattr(self.inner, "calls_made", 0))

    def specs(self) -> list[dict[str, Any]]:
        return list(self.inner.specs())

    async def call(self, name: str, arguments: dict[str, Any]) -> Any:
        outcome = await self.inner.call(name, arguments)
        self.outcomes.append(outcome)
        return outcome


async def run_case(
    case: CompanionCase,
    *,
    belt: Any,
    model: str = "anthropic/claude-sonnet-4-6",
    provider: Any = None,
) -> TurnResult:
    """Corre un caso y devuelve lo que pasó.

    ``provider`` sin dar = proveedor guionizado (offline). Con el proveedor
    real dentro, el mismo código corre el modo live: la trayectoria se
    ignora porque nadie llama a ``tool_caller``.
    """
    from langgraph.checkpoint.memory import MemorySaver
    from nexus_worker.runtime.companion import build_companion_graph
    from nexus_worker.runtime.llm import InMemoryProvider

    recording = _RecordingBelt(belt)
    if provider is None:
        script = ScriptedModel(steps=case.trajectory)
        provider = InMemoryProvider(responder=script.responder, tool_caller=script.tool_caller)

    graph = build_companion_graph(
        provider=provider,
        model=model,
        checkpointer=MemorySaver(),
        toolbelt=recording,
    )

    events: list[tuple[str, dict[str, Any]]] = []
    phases: list[str] = []
    final: dict[str, Any] = {}
    state: dict[str, Any] = {
        "thread_id": str(uuid.uuid4()),
        "user_message": case.user_message,
        "history": [],
        "principal": {"role": "owner"},
    }
    if case.untrusted_text:
        state["page_context"] = {"untrusted": _fenced(case.untrusted_text)}

    async for event in graph.astream_events(
        state,
        config={"configurable": {"thread_id": state["thread_id"]}},
        version="v2",
    ):
        if event.get("event") == "on_custom_event":
            name = str(event.get("name"))
            payload = dict(event.get("data") or {})
            events.append((name, payload))
            if name == "phase.changed":
                phases.append(str(payload.get("phase")))
        elif event.get("event") == "on_chain_end" and event.get("name") in (
            "investigate",
            "respond",
        ):
            # Los dos nodos aportan la mitad de lo que se mide: el bucle
            # deja ``reads_done`` y ``tool_calls_made``, el cierre deja el
            # veredicto de R1. Se fusionan en orden de ejecución.
            out = (event.get("data") or {}).get("output")
            if isinstance(out, dict):
                final.update(out)

    return TurnResult(
        answer=str(final.get("answer") or ""),
        reads_ok=int(final.get("reads_done") or 0),
        calls_made=int(final.get("tool_calls_made") or 0),
        unsupported=bool(final.get("unsupported")),
        outcomes=recording.outcomes,
        events=events,
        phases=phases,
    )


def _fenced(text: str) -> str:
    """Todo texto de terceros entra vallado. Es la capa 2 del §9.1."""
    from nexus_api.core.guardrails.untrusted import TAG_KNOWLEDGE, fenced_block

    return fenced_block([(None, text)], tag=TAG_KNOWLEDGE)


async def candidates_for(belt: Any, query: str) -> int:
    """Cuántos clientes encajan con ``query``. Es el hecho que hace que un
    caso de la familia 2 sea de verdad ambiguo: no una impresión, una
    lectura contra la base."""
    outcome = await belt.call("console.list_clients", {"q": query})
    if not outcome.ok:
        return 0
    try:
        payload = json.loads(outcome.content)
    except ValueError:  # pragma: no cover - defensivo
        return 0
    items = payload.get("items") if isinstance(payload, dict) else payload
    return len(items) if isinstance(items, list) else 0


__all__ = ["ScriptedModel", "TurnResult", "candidates_for", "run_case"]
