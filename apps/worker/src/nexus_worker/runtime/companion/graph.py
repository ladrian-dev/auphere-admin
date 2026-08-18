"""Grafo mínimo del Companion — entender → investigar → responder (CO-01).

Sin herramientas (CO-02), sin escrituras, sin HITL (CO-04). Lo que sí tiene
desde el primer día:

- **Fases explícitas.** La máquina de estados del §7 es del motor, no del
  prompt: el modelo elige el CONTENIDO de cada fase, no si la fase ocurre.
  ``investigate`` está cableado y vacío a propósito — es donde aterrizan las
  herramientas de lectura de CO-02, y emitir ya su ``phase.changed`` hace
  que la píldora de estado del cajón sea honesta desde el principio.
- **Checkpoint en cada frontera de nodo.** El hilo sobrevive a un F5 y al
  reinicio del proceso.
- **Un hueco preparado para el ``interrupt()``.** :func:`await_confirmation`
  existe, está documentado y **no está cableado**. Cuando CO-04 lo enchufe,
  el nodo no debe hacer NADA más que el ``interrupt()``: LangGraph reanuda
  re-ejecutando el nodo entero desde la primera línea, así que cualquier
  escritura anterior al ``interrupt()`` dentro del mismo nodo se aplicaría
  dos veces (Parte II, C2). La persistencia va en el nodo de antes, con id
  determinista y UPSERT.

Los eventos salen por ``adispatch_custom_event`` y no por los eventos de
modelo de LangChain. No es una preferencia: el runtime llama a LiteLLM
directamente y **nunca** hay un ``on_chat_model_stream`` que traducir.
"""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, Any

import structlog

from nexus_worker.runtime.companion.prompt import COMPANION_THINKING, build_messages
from nexus_worker.runtime.companion.state import (
    PHASE_DONE,
    PHASE_INVESTIGATE,
    PHASE_LABELS,
    PHASE_RESPOND,
    PHASE_UNDERSTAND,
    CompanionState,
)

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver

    from nexus_worker.runtime.llm import LLMProvider

log = structlog.get_logger(__name__)

#: Rol de modelo del Companion. Tiene binding propio (migración 0090) para
#: poder atarlo a un modelo distinto —y más caro— que el de los agentes de
#: cliente sin afectar a nadie: el Companion es la cara de Auphere ante el
#: partner y aquí no se ahorra.
COMPANION_ROLE = "companion"

#: Tenant sintético de las llamadas del Companion. La firma del proveedor
#: exige uno (todo lo demás en la plataforma es de un cliente), pero un hilo
#: del Companion puede no tener cliente todavía. Es un UUID fijo y
#: reconocible: aparece en los logs como "esto no es de nadie".
COMPANION_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-00000000c0a1")


async def _emit(event: str, payload: dict[str, Any]) -> None:
    """Publica un evento del protocolo hacia el stream, si hay stream.

    Fuera de ``astream_events`` (tests que llaman a un nodo a pelo) la
    llamada lanza; se traga porque emitir es telemetría del turno, no el
    turno. Mismo criterio que el escritor de auditoría del playground.
    """
    try:
        from langchain_core.callbacks.manager import adispatch_custom_event

        await adispatch_custom_event(event, payload)
    except Exception:
        pass


async def _phase(phase: str) -> None:
    await _emit("phase.changed", {"phase": phase, "label": PHASE_LABELS.get(phase, phase)})


async def _max_context_for(model: str) -> int | None:
    """Ventana del modelo, del catálogo (``model_profiles.max_context``).

    Dato de base y no constante de código: cuando un proveedor amplía la
    ventana se actualiza una fila. Si el modelo no está en el catálogo se
    devuelve ``None`` y el medidor **no se emite** — una barra al 0% sería
    peor que ninguna barra, porque la gente la creería.
    """
    try:
        from nexus_worker.metering.pricing import get_catalog

        catalog = await get_catalog()
        row = catalog.get(model)
        return row.max_context if row is not None else None
    except Exception as exc:  # pragma: no cover - defensivo
        log.warning("companion.max_context_unavailable", model=model, error=str(exc))
        return None


# ── nodos ──────────────────────────────────────────────────────────────


async def understand(state: CompanionState) -> dict[str, Any]:
    """Marca el arranque del turno. Sin llamada al modelo: en CO-01 no hay
    nada que clasificar (no hay ramas ni herramientas) y una llamada extra
    solo añadiría coste y latencia para producir una etiqueta que nadie lee.
    Cuando CO-02 traiga el catálogo, aquí se decide qué leer."""
    await _phase(PHASE_UNDERSTAND)
    return {"phase": PHASE_UNDERSTAND}


async def investigate(state: CompanionState) -> dict[str, Any]:
    """Leer el estado REAL antes de opinar.

    Vacío en CO-01 — **y cableado a propósito**. Es el sitio exacto donde
    entran las 14 herramientas de lectura de CO-02, y tener ya la fase en el
    protocolo evita que el cajón tenga que cambiar cuando lleguen. El prompt
    ya le dice al modelo que hoy no puede afirmar datos del sistema, así que
    el hueco no se disfraza de capacidad.
    """
    await _phase(PHASE_INVESTIGATE)
    return {"phase": PHASE_INVESTIGATE}


def make_respond(provider: LLMProvider, *, model: str):
    """Nodo de respuesta, con el proveedor y el modelo ya elegidos.

    Fábrica y no nodo suelto para que el grafo se pueda compilar con un
    proveedor en memoria en las pruebas sin tocar red ni monkeypatchear un
    import.
    """

    async def respond(state: CompanionState) -> dict[str, Any]:
        await _phase(PHASE_RESPOND)
        messages = build_messages(
            history=state.get("history"),
            user_message=state.get("user_message", ""),
            page_context=state.get("page_context"),
        )
        message_id = str(uuid.uuid4())
        chunks: list[str] = []
        usage: dict[str, int] = {}

        async for kind, piece in provider.astream_complete(
            tenant_id=COMPANION_TENANT_ID,
            role=COMPANION_ROLE,
            model=model,
            messages=messages,
            # El pensamiento se pide EXPLÍCITAMENTE. Sin esto los bloques
            # llegan vacíos y el "pensamiento colapsable" del cajón no tiene
            # nada que colapsar (Parte II, C3).
            extra={"thinking": COMPANION_THINKING},
        ):
            if kind == "text":
                chunks.append(piece)
                await _emit("text.delta", {"message_id": message_id, "text": piece})
            elif kind == "thinking":
                # El razonamiento viaja por el stream y NO se persiste: es
                # caro de guardar y es la parte más propensa a contener
                # divagaciones que luego se leen como compromisos (§8.2).
                await _emit("reasoning.delta", {"message_id": message_id, "text": piece})
            elif kind == "usage":
                try:
                    usage = json.loads(piece)
                except ValueError:  # pragma: no cover - defensivo
                    usage = {}

        input_tokens = int(usage.get("prompt_tokens") or 0)
        output_tokens = int(usage.get("completion_tokens") or 0)
        await _emit(
            "cost.updated",
            {"input_tokens": input_tokens, "output_tokens": output_tokens, "model": model},
        )

        # Ventana de contexto honesta: el ``input_tokens`` de ESTA llamada
        # ES el tamaño real del prefijo consumido, medido por el proveedor.
        # Estimarlo por caracteres en el navegador dejaría fuera el prompt
        # de sistema, las definiciones de herramientas y los resultados de
        # las herramientas — que en este agente son la mayor parte.
        max_context = await _max_context_for(model)
        if max_context:
            await _emit(
                "context.updated",
                {
                    "input_tokens": input_tokens,
                    "max_context": max_context,
                    "percent": round(input_tokens * 100.0 / max_context, 2),
                    "compacted": False,
                    "model": model,
                },
            )

        return {
            "phase": PHASE_DONE,
            "answer": "".join(chunks),
            "model": model,
            "last_input_tokens": input_tokens,
            "total_input_tokens": state.get("total_input_tokens", 0) + input_tokens,
            "total_output_tokens": state.get("total_output_tokens", 0) + output_tokens,
        }

    return respond


async def await_confirmation(state: CompanionState) -> dict[str, Any]:  # pragma: no cover
    """RESERVADO para CO-04. No cableado.

    Cuando se enchufe, este nodo contendrá **una sola línea**: la llamada a
    ``interrupt()``. Nada de persistir la acción ni de emitir el evento
    aquí — LangGraph reanuda re-ejecutando el nodo desde la primera línea,
    y ese diseño (el de la Parte I §10) inserta la fila de
    ``companion.actions`` dos veces y emite ``hitl.requested`` dos veces por
    cada confirmación.

    Reglas que van con él, todas de la Parte II C2:
      - la persistencia va en el nodo ANTERIOR, con ``action_id``
        determinista (hash de ``run_id`` + índice de paso) y UPSERT;
      - ``interrupt()`` **nunca** dentro de un ``try/except`` genérico:
        pausa lanzando una excepción y un ``except Exception`` se la traga;
      - las llamadas a ``interrupt()`` deben ser incondicionales y en orden
        estable — la correspondencia con los valores de reanudación es por
        índice, y saltarse una según una condición desalinea todo.
    """
    raise NotImplementedError("HITL llega en CO-04; ver docs/companion/PLAN-CO-01.md")


# ── compilación ────────────────────────────────────────────────────────


def build_companion_graph(
    *,
    provider: LLMProvider,
    model: str,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> Any:
    """Compila el grafo del Companion.

    ``checkpointer`` opcional: en producción es el ``AsyncPostgresSaver``
    del proceso (``core/qa_checkpointer.py``, esquema ``langgraph``); los
    tests pasan un ``MemorySaver``.
    """
    from langgraph.graph import END, START, StateGraph

    graph: Any = StateGraph(CompanionState)
    graph.add_node("understand", understand)
    graph.add_node("investigate", investigate)
    graph.add_node("respond", make_respond(provider, model=model))
    graph.add_edge(START, "understand")
    graph.add_edge("understand", "investigate")
    graph.add_edge("investigate", "respond")
    graph.add_edge("respond", END)
    return graph.compile(checkpointer=checkpointer)


__all__ = [
    "COMPANION_ROLE",
    "COMPANION_TENANT_ID",
    "await_confirmation",
    "build_companion_graph",
    "investigate",
    "make_respond",
    "understand",
]
