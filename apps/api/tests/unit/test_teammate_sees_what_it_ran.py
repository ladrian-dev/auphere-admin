"""Lo que el comando escribió tiene que llegar al modelo que responde.

El nodo ``execute`` aplicaba la acción confirmada y se quedaba **solo con el
booleano**: `{"ok": applied}`. El `content` del resultado —que para
``shell_local`` es lo que el programa imprimió— se descartaba ahí mismo. El
modelo pasaba a ``respond`` sabiendo que algo salió bien o mal, pero no **qué**.

Esa es la diferencia entre un agente que ejecuta y uno que trabaja: sin la
salida no puede leer un error de compilación, ni encadenar un segundo paso, ni
decirle a la persona qué pasó sin inventárselo.

**Lo que este arreglo NO hace, y es deliberado:** la salida no se persiste. Va
en ``tool_messages``, que vive en el estado del turno. La auditoría sigue
diciendo qué se ejecutó y nunca qué dijo el comando (§III de la constitución, y
la condición que legitima guardar el hilo — migración 0090).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from nexus_worker.runtime.companion.graph import build_companion_graph
from nexus_worker.runtime.llm import InMemoryProvider

from .test_companion_action_graph import FakeActionBelt, FakeProposal

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

MODEL = "anthropic/claude-sonnet-5"

#: Lo que un `make` fallido escribe de verdad: el error va por stderr y es la
#: única línea que importa.
COMMAND_OUTPUT = (
    "src/main.c:42:5: error: 'nombre' undeclared (first use in this function)\n"
    "make: *** [Makefile:12: build] Error 1\n"
)


class MachineBelt(FakeActionBelt):
    """El doble de siempre, con una sola diferencia: `apply_confirmed` devuelve
    lo que el programa imprimió, que es lo que hace `shell_local`."""

    async def apply_confirmed(self, action_id: Any) -> Any:
        self.applied += 1

        @dataclass
        class Result:
            ok: bool
            content: str
            name: str = "shell_local"

        return Result(ok=True, content=COMMAND_OUTPUT)


def _belt() -> MachineBelt:
    return MachineBelt(proposals=[FakeProposal(kind="local_exec", title="Ejecutar make")])


def _graph(belt: Any) -> Any:
    provider = InMemoryProvider(responder=lambda _call: "el build falla en main.c")
    return build_companion_graph(
        provider=provider, model=MODEL, checkpointer=MemorySaver(), toolbelt=belt
    )


def _entry() -> dict[str, Any]:
    return {
        "thread_id": str(uuid.uuid4()),
        "principal": {"role": "owner", "partner": "p", "permissions": []},
        "page_context": None,
        "history": [],
        "user_message": "corre el build y dime por qué falla",
        "total_input_tokens": 0,
        "total_output_tokens": 0,
    }


async def _drive(graph: Any, config: dict[str, Any]) -> Any:
    """Turno completo: propone, se para en el interrupt, confirma y ejecuta."""
    async for _ in graph.astream_events(_entry(), config=config, version="v2"):
        pass
    async for _ in graph.astream_events(
        Command(resume={"decision": "confirm", "note": None, "by": "u1", "at": "2026-09-20"}),
        config=config,
        version="v2",
    ):
        pass
    return await graph.aget_state(config)


async def test_the_output_of_the_command_reaches_the_model() -> None:
    belt = _belt()
    graph = _graph(belt)
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    snapshot = await _drive(graph, config)

    assert belt.applied == 1
    messages = snapshot.values.get("tool_messages") or []
    blob = "".join(str(m.get("content", "")) for m in messages)
    assert "undeclared" in blob, (
        "el modelo respondió sin ver lo que imprimió el comando: "
        "ejecuta a ciegas y solo puede inventarse el motivo"
    )


async def test_the_output_is_marked_as_data_not_instructions() -> None:
    """§III: lo que escribe un programa es dato. Si el modelo lo lee como si
    fueran órdenes, un repositorio con un README hostil manda en la máquina."""
    belt = _belt()
    graph = _graph(belt)
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    snapshot = await _drive(graph, config)

    messages = snapshot.values.get("tool_messages") or []
    carrying = [m for m in messages if "undeclared" in str(m.get("content", ""))]
    assert carrying, "no llegó nada que marcar"
    for m in carrying:
        assert m.get("untrusted") is True, (
            "la salida de un programa viaja sin marcar: §III pide lo contrario"
        )
