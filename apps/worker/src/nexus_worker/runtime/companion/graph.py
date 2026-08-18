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
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import structlog

from nexus_worker.runtime.companion.grounding import is_unsupported
from nexus_worker.runtime.companion.prompt import (
    COMPANION_THINKING,
    budget_note,
    build_messages,
)
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

    from nexus_worker.runtime.companion.tools import Toolbelt
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

#: Pasos de modelo por turno. Cada paso es una llamada al proveedor: o pide
#: herramientas, o escribe la respuesta. El tope existe porque un modelo que
#: se atasca alternando dos lecturas no se detiene solo, y a la doceava
#: llamada el usuario ya se fue.
MAX_MODEL_STEPS = 12

#: Presupuesto de tokens del turno que el modelo VE como cuenta atrás
#: (§23.3). Detrás sigue el tope mensual del partner, que es el que de
#: verdad protege la factura; esto es para que cierre con elegancia en vez
#: de que lo corten.
TURN_TOKEN_BUDGET = 120_000


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
    """Sin herramientas conectadas no hay nada que investigar.

    El nodo real es :func:`make_investigate`; esto es lo que se compila
    cuando el grafo se construye sin ``toolbelt`` — los tests que solo
    ejercitan el prompt, y cualquier despliegue donde las herramientas no
    estén disponibles.
    """
    await _phase(PHASE_INVESTIGATE)
    return {"phase": PHASE_INVESTIGATE, "tool_calls_made": 0, "reads_done": 0}


def make_investigate(
    provider: LLMProvider, *, model: str, toolbelt: Toolbelt
) -> Callable[[CompanionState], Awaitable[dict[str, Any]]]:
    """El bucle de herramientas: leer el estado REAL antes de opinar.

    Un paso = una llamada al proveedor en streaming, con el catálogo puesto.
    Si el paso pide herramientas, se ejecutan y el bucle sigue; si no pide
    ninguna, lo que escribió **es** la respuesta y el bucle termina. No hay
    una segunda llamada "para redactar": pagarla sería duplicar el coste del
    turno para repetir lo que el bucle ya produjo.

    Dos reglas que van en el motor y no en el prompt:

    - **La fase sigue a lo que está pasando.** El pill dice *Investigando*
      mientras corre una herramienta y *Respondiendo* mientras salen
      palabras. Sin herramientas la secuencia sigue siendo
      ``understand → investigate → respond``.
    - **Los topes son duros.** Pasos, llamadas y presupuesto. El modelo ve
      una cuenta atrás (``budget_note``) para poder cerrar con elegancia,
      pero si la ignora, el bucle para igual.

    Sobre el pensamiento: los bloques del asistente vuelven al proveedor tal
    cual en el paso siguiente. Con pensamiento activo, Anthropic **exige**
    que acompañen a los resultados de herramienta; perderlos es un 400.
    """

    async def _investigate(state: CompanionState) -> dict[str, Any]:
        await _phase(PHASE_INVESTIGATE)
        phase = PHASE_INVESTIGATE

        base = build_messages(
            history=state.get("history"),
            user_message=state.get("user_message", ""),
            page_context=state.get("page_context"),
        )
        messages: list[dict[str, Any]] = [*base, *(state.get("tool_messages") or [])]
        specs = toolbelt.specs()

        message_id = str(uuid.uuid4())
        chunks: list[str] = []
        input_tokens = 0
        output_tokens = 0
        last_input_tokens = 0

        for _step in range(MAX_MODEL_STEPS):
            note = budget_note(
                calls_left=toolbelt.calls_left,
                tokens_left=TURN_TOKEN_BUDGET - input_tokens - output_tokens,
                tokens_total=TURN_TOKEN_BUDGET,
            )
            if note is not None:
                messages.append(note)

            step_text: list[str] = []
            requested: list[dict[str, Any]] = []
            assistant: dict[str, Any] | None = None

            async for kind, piece in provider.astream_with_tools(
                tenant_id=COMPANION_TENANT_ID,
                role=COMPANION_ROLE,
                model=model,
                messages=messages,
                tools=specs,
                extra={"thinking": COMPANION_THINKING},
            ):
                if kind == "text":
                    if phase != PHASE_RESPOND:
                        # Está escribiendo para la persona: eso es responder,
                        # lo diga el nodo o no.
                        phase = PHASE_RESPOND
                        await _phase(PHASE_RESPOND)
                    step_text.append(piece)
                    await _emit("text.delta", {"message_id": message_id, "text": piece})
                elif kind == "thinking":
                    await _emit("reasoning.delta", {"message_id": message_id, "text": piece})
                elif kind == "tool_call":
                    requested.append(json.loads(piece))
                elif kind == "assistant":
                    assistant = json.loads(piece)
                elif kind == "usage":
                    usage = _usage(piece)
                    last_input_tokens = int(usage.get("prompt_tokens") or 0)
                    input_tokens += last_input_tokens
                    output_tokens += int(usage.get("completion_tokens") or 0)

            chunks.extend(step_text)

            if not requested:
                break

            if phase != PHASE_INVESTIGATE:
                phase = PHASE_INVESTIGATE
                await _phase(PHASE_INVESTIGATE)

            messages.append(assistant or _assistant_from(step_text, requested))
            for call in requested:
                messages.append(await _run_tool(toolbelt, call))

        return {
            # La fase REAL en la que terminó el bucle. Si nunca llegó a
            # escribir —tope de pasos alcanzado, por ejemplo— sigue siendo
            # ``investigate``, y el nodo de cierre lo verá y anunciará el
            # cambio. Devolver siempre ``respond`` sería emitir la fase dos
            # veces en el camino normal.
            "phase": phase,
            "answer": "".join(chunks),
            "model": model,
            "tool_messages": messages[len(base) :],
            "tool_calls_made": _calls_made(toolbelt),
            "reads_done": toolbelt.reads_done,
            "last_input_tokens": last_input_tokens,
            "total_input_tokens": state.get("total_input_tokens", 0) + input_tokens,
            "total_output_tokens": state.get("total_output_tokens", 0) + output_tokens,
        }

    return _investigate


def _calls_made(toolbelt: Toolbelt) -> int:
    return int(getattr(toolbelt, "calls_made", 0))


def _usage(piece: str) -> dict[str, Any]:
    try:
        parsed = json.loads(piece)
    except ValueError:  # pragma: no cover - defensivo
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _assistant_from(text: list[str], calls: list[dict[str, Any]]) -> dict[str, Any]:
    """Reconstrucción de emergencia del mensaje del asistente.

    El proveedor real lo entrega ya montado (``kind == "assistant"``); esto
    cubre a un doble de test que no lo haga. Sin mensaje del asistente, los
    resultados de herramienta que vienen detrás quedan huérfanos y el
    proveedor rechaza la petición entera.
    """
    return {
        "role": "assistant",
        "content": "".join(text) or None,
        "tool_calls": [
            {
                "id": c.get("id") or "",
                "type": "function",
                "function": {
                    "name": c.get("name") or "",
                    "arguments": json.dumps(c.get("arguments") or {}),
                },
            }
            for c in calls
        ],
    }


async def _run_tool(toolbelt: Toolbelt, call: dict[str, Any]) -> dict[str, Any]:
    """Ejecuta una llamada y emite sus tres eventos.

    Los eventos los emite el GRAFO y no el ejecutor: el protocolo del cajón
    es del runtime, y así el paquete de herramientas no depende de LangChain
    ni el grafo de la API.

    ``args`` en ``tool.call.started`` lleva solo lo que el modelo escribió
    —una referencia de cliente, unos días—, nunca contenido leído. Es lo que
    permite que el evento pase el catálogo cerrado de C8.
    """
    call_id = str(call.get("id") or uuid.uuid4().hex[:12])
    name = str(call.get("name") or "")
    arguments = call.get("arguments") or {}
    if not isinstance(arguments, dict):
        arguments = {}

    await _emit(
        "tool.call.started",
        {
            "tool_call_id": call_id,
            "name": name,
            "label": name,
            "args": json.dumps(arguments, ensure_ascii=False, sort_keys=True),
        },
    )
    result = await toolbelt.call(name, arguments)
    citation = getattr(result, "citation", None)
    payload: dict[str, Any] = {
        "tool_call_id": call_id,
        "name": name,
        "ok": bool(result.ok),
        "latency_ms": int(result.latency_ms),
    }
    if result.error_code:
        payload["error"] = result.error_code
    if citation is not None:
        payload["citation_id"] = citation.citation_id
    await _emit("tool.call.completed", payload)
    if citation is not None:
        await _emit("citation", citation.as_payload())

    return {
        "role": "tool",
        "tool_call_id": call_id,
        "name": name,
        "content": result.content,
    }


def make_respond(
    provider: LLMProvider, *, model: str
) -> Callable[[CompanionState], Awaitable[dict[str, Any]]]:
    """Cierra el turno: medidores y regla R1.

    En CO-01 este nodo hacía la llamada al modelo. Desde CO-02 esa llamada
    vive en el bucle de ``investigate`` —donde el último mensaje del
    asistente sin herramientas YA es la respuesta—, y aquí queda lo que
    tiene que pasar exactamente una vez por turno, después de todo.

    Sigue recibiendo el proveedor porque un grafo sin ``toolbelt`` no tiene
    bucle: en ese caso este nodo hace la llamada él mismo, que es el
    comportamiento de CO-01 intacto.
    """

    async def respond(state: CompanionState) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        if not state.get("tool_messages") and not state.get("answer"):
            # Grafo sin herramientas: el camino de CO-01.
            updates = await _answer_without_tools(provider, model=model, state=state)
        elif state.get("phase") != PHASE_RESPOND:
            # El bucle terminó sin llegar a escribir (tope de pasos, o un
            # último paso que solo pidió herramientas). Se anuncia el cambio
            # aquí; en el camino normal ya lo anunció el bucle y repetirlo
            # haría parpadear el pill del cajón.
            await _phase(PHASE_RESPOND)

        merged: dict[str, Any] = {**state, **updates}
        input_tokens = int(merged.get("last_input_tokens") or 0)
        await _emit(
            "cost.updated",
            {
                "input_tokens": int(merged.get("total_input_tokens") or 0),
                "output_tokens": int(merged.get("total_output_tokens") or 0),
                "model": model,
            },
        )
        # Ventana de contexto honesta: el ``input_tokens`` de la ÚLTIMA
        # llamada ES el tamaño real del prefijo consumido, medido por el
        # proveedor. Estimarlo por caracteres en el navegador dejaría fuera
        # el prompt de sistema, las definiciones de herramientas y los
        # resultados de las herramientas — que en este agente son la mayor
        # parte.
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

        answer = str(merged.get("answer") or "")
        unsupported = is_unsupported(answer, reads_done=int(merged.get("reads_done") or 0))
        if unsupported:
            # No se tira el turno: se marca. La barrera dura son las
            # escrituras, que no existen fuera de propose→confirm (CO-04).
            log.info("companion.turn.unsupported", model=model)
        # ``answer`` se devuelve aunque no haya cambiado: la salida de este
        # nodo es lo que el driver lee, y un turno cerrado tiene que poder
        # leerse entero de un sitio.
        return {**updates, "answer": answer, "phase": PHASE_DONE, "unsupported": unsupported}

    return respond


async def _answer_without_tools(
    provider: LLMProvider, *, model: str, state: CompanionState
) -> dict[str, Any]:
    """El camino de CO-01: una sola llamada en streaming, sin catálogo."""
    await _phase(PHASE_RESPOND)
    messages = build_messages(
        history=state.get("history"),
        user_message=state.get("user_message", ""),
        page_context=state.get("page_context"),
    )
    message_id = str(uuid.uuid4())
    chunks: list[str] = []
    usage: dict[str, Any] = {}
    async for kind, piece in provider.astream_complete(
        tenant_id=COMPANION_TENANT_ID,
        role=COMPANION_ROLE,
        model=model,
        messages=messages,
        extra={"thinking": COMPANION_THINKING},
    ):
        if kind == "text":
            chunks.append(piece)
            await _emit("text.delta", {"message_id": message_id, "text": piece})
        elif kind == "thinking":
            await _emit("reasoning.delta", {"message_id": message_id, "text": piece})
        elif kind == "usage":
            usage = _usage(piece)
    input_tokens = int(usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("completion_tokens") or 0)
    return {
        "answer": "".join(chunks),
        "model": model,
        "last_input_tokens": input_tokens,
        "total_input_tokens": state.get("total_input_tokens", 0) + input_tokens,
        "total_output_tokens": state.get("total_output_tokens", 0) + output_tokens,
    }


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
    toolbelt: Toolbelt | None = None,
) -> Any:
    """Compila el grafo del Companion.

    ``checkpointer`` opcional: en producción es el ``AsyncPostgresSaver``
    del proceso (``core/qa_checkpointer.py``, esquema ``langgraph``); los
    tests pasan un ``MemorySaver``.

    ``toolbelt`` opcional y **por turno**: lleva el sujeto de las llamadas y
    el contador de consultas, así que no se puede compartir entre runs. Sin
    él, el grafo se comporta como en CO-01 — una llamada, sin lecturas — y
    R1 marcará el turno si afirma datos del sistema.
    """
    from langgraph.graph import END, START, StateGraph

    graph: Any = StateGraph(CompanionState)
    graph.add_node("understand", understand)
    graph.add_node(
        "investigate",
        investigate
        if toolbelt is None
        else make_investigate(provider, model=model, toolbelt=toolbelt),
    )
    graph.add_node("respond", make_respond(provider, model=model))
    graph.add_edge(START, "understand")
    graph.add_edge("understand", "investigate")
    graph.add_edge("investigate", "respond")
    graph.add_edge("respond", END)
    return graph.compile(checkpointer=checkpointer)


__all__ = [
    "COMPANION_ROLE",
    "COMPANION_TENANT_ID",
    "MAX_MODEL_STEPS",
    "TURN_TOKEN_BUDGET",
    "await_confirmation",
    "build_companion_graph",
    "investigate",
    "make_investigate",
    "make_respond",
    "understand",
]
