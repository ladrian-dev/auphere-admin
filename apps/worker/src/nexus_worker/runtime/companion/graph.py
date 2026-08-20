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

# ``nexus_api`` es la primera dependencia declarada del worker
# (``apps/worker/pyproject.toml``), y ``guardrails.untrusted`` es un módulo
# puro —su único import es ``__future__``—, así que traerlo no arrastra la
# API. Vive allí y no aquí para que el vallado del Companion y el del bloque
# de conocimiento del agente de cliente sigan siendo el MISMO tratamiento,
# que es lo que el test de paridad comprueba.
from nexus_api.core.guardrails.untrusted import TAG_TOOL_RESULT, fence_only

from nexus_worker.runtime.companion.grounding import is_unsupported
from nexus_worker.runtime.companion.intake import (
    TOOL_BY_WORK_KIND,
    WORK_PUBLISH,
    blocking_slots,
    ledger_note,
    missing_slots,
    record_answers,
    record_asked,
)
from nexus_worker.runtime.companion.prompt import (
    budget_note,
    build_messages,
    closing_note,
    thinking_extra,
)
from nexus_worker.runtime.companion.state import (
    PHASE_AWAITING,
    PHASE_DONE,
    PHASE_EXECUTE,
    PHASE_INTAKE,
    PHASE_INVESTIGATE,
    PHASE_PLAN,
    PHASE_PUBLISH,
    PHASE_RESPOND,
    PHASE_UNDERSTAND,
    PHASE_VERIFY,
    RUN_SCOPED_DEFAULTS,
    CompanionState,
    PhaseTracker,
)
from nexus_worker.runtime.companion.tools import supports_actions, to_wire, wire_tools

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver

    from nexus_worker.runtime.companion.tools import ActionPort, Toolbelt
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


#: Los ``kind`` que dejan un BORRADOR, no un cambio vivo. Son los que pueden
#: desembocar en una publicación (§2.4 de PLAN-CO-06).
DRAFT_KINDS: frozenset[str] = frozenset({"prompt", "policy", "tools", "skills"})

#: Trabajo → herramienta, al revés: es lo que necesita el bucle para saber
#: qué llamada alimenta el expediente.
_WORK_KIND_BY_TOOL: dict[str, str] = {tool: work for work, tool in TOOL_BY_WORK_KIND.items()}


def _tracker(state: CompanionState, *, fresh: bool = False) -> PhaseTracker:
    """La máquina de fases de este run, continuada desde el estado.

    ``fresh`` la arranca de cero: es lo que hace el primer nodo del turno,
    porque el estado del hilo trae la fase del turno ANTERIOR y sin esto un
    turno nuevo empezaría "más adelante" de donde está.
    """
    return PhaseTracker(_emit, current=None if fresh else state.get("phase"))


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
    """Marca el arranque del turno y **borra el rastro del run anterior**.

    Sin llamada al modelo: en CO-01 no hay nada que clasificar (no hay ramas
    ni herramientas) y una llamada extra solo añadiría coste y latencia para
    producir una etiqueta que nadie lee. Cuando CO-02 trajo el catálogo,
    aquí se decide qué leer.

    La limpieza es de CO-06 y arregla un defecto medido: el checkpointer
    está indexado por ``thread_id``, así que el ``hitl`` y la ``verify`` de
    una confirmación anterior seguían en el estado al empezar el turno
    siguiente — y el nodo de cierre respondía **dos veces**, una por el
    bucle y otra informando de una acción que ya se había contado.

    Lo que **no** se borra es el expediente (``intake``): ese es del hilo, y
    borrarlo sería volver a preguntar lo que la persona ya contestó (§3.4
    del contrato v2).

    ``understand`` no corre en un ``resume`` —el grafo retoma en
    ``confirm``—, así que esta limpieza no toca al run de continuación.
    """
    await _tracker(state, fresh=True).enter(PHASE_UNDERSTAND)
    return {**RUN_SCOPED_DEFAULTS, "phase": PHASE_UNDERSTAND}


async def investigate(state: CompanionState) -> dict[str, Any]:
    """Sin herramientas conectadas no hay nada que investigar.

    El nodo real es :func:`make_investigate`; esto es lo que se compila
    cuando el grafo se construye sin ``toolbelt`` — los tests que solo
    ejercitan el prompt, y cualquier despliegue donde las herramientas no
    estén disponibles.
    """
    await _tracker(state).enter(PHASE_INVESTIGATE)
    return {"phase": PHASE_INVESTIGATE, "tool_calls_made": 0, "reads_done": 0}


def make_investigate(
    provider: LLMProvider, *, model: str, toolbelt: Toolbelt, effort: str | None = None
) -> Callable[[CompanionState], Awaitable[dict[str, Any]]]:
    """El bucle de herramientas: leer el estado REAL antes de opinar.

    Un paso = una llamada al proveedor en streaming, con el catálogo puesto.
    Si el paso pide herramientas, se ejecutan y el bucle sigue; si no pide
    ninguna, lo que escribió **es** la respuesta y el bucle termina. No hay
    una segunda llamada "para redactar": pagarla sería duplicar el coste del
    turno para repetir lo que el bucle ya produjo.

    Tres reglas que van en el motor y no en el prompt:

    - **La fase no retrocede** (garantía E2). Hasta CO-06 el bucle ponía
      *Respondiendo* con el primer trozo de texto y volvía a *Investigando*
      si después había herramientas: un salto hacia atrás, y una píldora que
      parpadeaba una vez por paso. Ahora el bucle **no anuncia ``respond``**
      —el texto sale por ``text.delta`` igual de pronto que antes—: lo
      anuncia quien sabe adónde va el turno, que es el nodo de cierre. Y
      tiene que ser así: un turno que termina proponiendo va a ``plan`` y a
      ``awaiting``, y anunciar *Respondiendo* antes las dejaría fuera.
    - **Los topes son duros, y cierran.** El modelo ve una cuenta atrás
      (``budget_note``) para poder cerrar con elegancia; si la ignora, hay
      una **puerta antes de cada llamada** y, cuando salta, un paso de
      cierre que dice dónde quedó el trabajo (R6, garantía E3). Un turno que
      se corta a mitad de frase es lo que E3 prohíbe.
    - **El expediente se alimenta de lo que el modelo entrega.** Cada
      ``console.propose_*`` deja en el expediente del hilo los datos que
      trajo, y esos ya no se vuelven a preguntar (§3.4 del contrato v2).

    Sobre el pensamiento: los bloques del asistente vuelven al proveedor tal
    cual en el paso siguiente. Con pensamiento activo, Anthropic **exige**
    que acompañen a los resultados de herramienta; perderlos es un 400. Ni
    la nota de expediente ni la de presupuesto tocan eso: se **añaden** al
    final, no reordenan nada.
    """

    async def _investigate(state: CompanionState) -> dict[str, Any]:
        tracker = _tracker(state)
        await tracker.enter(PHASE_INVESTIGATE)

        base = build_messages(
            history=state.get("history"),
            user_message=state.get("user_message", ""),
            page_context=state.get("page_context"),
        )
        messages: list[dict[str, Any]] = [*base, *(state.get("tool_messages") or [])]
        # §17 del contrato v2.1: el proveedor no admite el punto en el nombre
        # de una herramienta. Se traduce **aquí**, en el límite, y el resto
        # del sistema sigue viendo ``console.get_usage``.
        specs, catalog_name = wire_tools(_specs(toolbelt))
        ledger: dict[str, Any] = dict(state.get("intake") or {})

        message_id = str(uuid.uuid4())
        chunks: list[str] = []
        input_tokens = 0
        output_tokens = 0
        last_input_tokens = 0
        cache_read = 0
        cache_write = 0
        steps_used = 0
        #: Por qué paró el bucle: ``None`` = escribió la respuesta.
        exhausted: str | None = None
        #: La última nota de expediente puesta. Se vuelve a poner solo si
        #: cambió: repetirla en cada paso es ruido, y el modelo deja de
        #: leerla — el mismo criterio que la nota de presupuesto.
        last_ledger_note: str | None = None

        for _step in range(MAX_MODEL_STEPS):
            # La puerta va ANTES de la llamada, no después de sumar: es la
            # forma del §23.2, y es la única que garantiza que el turno tenga
            # margen para cerrar. La llamada que cruza el tope se completa,
            # así que el total puede pasarse por como mucho una llamada.
            if input_tokens + output_tokens >= TURN_TOKEN_BUDGET:
                exhausted = "tokens"
                break

            note = budget_note(
                calls_left=toolbelt.calls_left,
                tokens_left=TURN_TOKEN_BUDGET - input_tokens - output_tokens,
                tokens_total=TURN_TOKEN_BUDGET,
            )
            if note is not None:
                messages.append(note)
            expediente = ledger_note(ledger)
            if expediente is not None and expediente["content"] != last_ledger_note:
                messages.append(expediente)
                last_ledger_note = str(expediente["content"])

            step_text: list[str] = []
            requested: list[dict[str, Any]] = []
            assistant: dict[str, Any] | None = None

            async for kind, piece in provider.astream_with_tools(
                tenant_id=COMPANION_TENANT_ID,
                role=COMPANION_ROLE,
                model=model,
                messages=messages,
                tools=specs,
                extra=thinking_extra(effort),
            ):
                if kind == "text":
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
                    # Dos números distintos a propósito: el bruto mide la
                    # VENTANA (lo que el modelo tuvo delante) y el facturable
                    # mide el GASTO (lo que no vino de caché).
                    last_input_tokens = int(usage.get("prompt_tokens") or 0)
                    input_tokens += _billable_input(usage)
                    output_tokens += int(usage.get("completion_tokens") or 0)
                    cache_read += int(usage.get("cache_read_input_tokens") or 0)
                    cache_write += int(usage.get("cache_creation_input_tokens") or 0)
                    steps_used += 1

            chunks.extend(step_text)

            if not requested:
                break

            # El mensaje del asistente vuelve al proveedor con los nombres de
            # cable que él mismo emitió: un ``tool_use.name`` que no coincida
            # con su ``tool_result`` correlativo es otro 400, y de los que no
            # salen en ningún test con proveedor guionizado. Y sin los bloques
            # de pensamiento que no se pueden reproducir (§18).
            messages.append(
                _reproducible(assistant) if assistant else _assistant_from(step_text, requested)
            )
            for call in requested:
                wire = str(call.get("name") or "")
                resolved = {**call, "name": catalog_name.get(wire, wire)}
                ledger = _record_intake(ledger, resolved)
                messages.append(await _run_tool(toolbelt, resolved, wire_name=wire))
        else:
            exhausted = "steps"

        if exhausted is not None:
            # R6 · garantía E3. El turno se agotó sin llegar a responder: se
            # cierra diciendo dónde quedó, en vez de devolver un turno mudo.
            closing, closing_usage = await _close_the_turn(
                provider,
                model=model,
                messages=messages,
                # Con nombres de cable: el historial que va detrás los lleva.
                specs=specs,
                message_id=message_id,
                reason=exhausted,
                effort=effort,
            )
            chunks.append(closing)
            input_tokens += _billable_input(closing_usage)
            output_tokens += int(closing_usage.get("completion_tokens") or 0)
            last_input_tokens = int(closing_usage.get("prompt_tokens") or last_input_tokens)
            cache_read += int(closing_usage.get("cache_read_input_tokens") or 0)
            cache_write += int(closing_usage.get("cache_creation_input_tokens") or 0)
            steps_used += 1

        return {
            # La fase REAL en la que terminó el bucle. Si nunca llegó a
            # escribir sigue siendo ``investigate``, y el nodo de cierre lo
            # verá y anunciará el cambio. Devolver siempre ``respond`` sería
            # emitir la fase dos veces en el camino normal.
            "phase": tracker.current or PHASE_INVESTIGATE,
            "answer": "".join(chunks),
            "model": model,
            "tool_messages": messages[len(base) :],
            "tool_calls_made": _calls_made(toolbelt),
            "reads_done": toolbelt.reads_done,
            "intake": ledger,
            "last_input_tokens": last_input_tokens,
            "total_input_tokens": state.get("total_input_tokens", 0) + input_tokens,
            "total_output_tokens": state.get("total_output_tokens", 0) + output_tokens,
            "total_cache_read": state.get("total_cache_read", 0) + cache_read,
            "total_cache_write": state.get("total_cache_write", 0) + cache_write,
            "total_steps": state.get("total_steps", 0) + steps_used,
        }

    return _investigate


def _record_intake(ledger: dict[str, Any], call: dict[str, Any]) -> dict[str, Any]:
    """Lo que esta llamada aporta al expediente del hilo.

    Se lee de los argumentos con los que el modelo llamó a la herramienta,
    que es lo único que consta: interpretar la prosa de la persona para
    rellenar un hueco sería adivinar, y adivinar un hueco es justo el fallo
    que el §7.1 existe para evitar.
    """
    work_kind = _WORK_KIND_BY_TOOL.get(str(call.get("name") or ""))
    if work_kind is None:
        return ledger
    arguments = call.get("arguments")
    return record_answers(ledger, work_kind, arguments if isinstance(arguments, dict) else {})


#: Cierre determinista cuando el turno se agota y ni siquiera la llamada de
#: cierre produce texto.
#:
#: Sin cifras a propósito: un número aquí dispararía el detector de R1 en un
#: turno que quizá no leyó nada, y marcaría de ``unsupported`` una frase que
#: escribió el motor.
_CLOSING_FALLBACK = (
    "Me he quedado sin margen en este turno y prefiero parar aquí antes que "
    "seguir a medias. No he cambiado nada. Dime si sigo por donde iba y "
    "retomo desde ahí."
)


async def _close_the_turn(
    provider: LLMProvider,
    *,
    model: str,
    messages: list[dict[str, Any]],
    specs: list[dict[str, Any]],
    message_id: str,
    reason: str,
    effort: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """El paso de cierre de R6 (garantía E3).

    Una última llamada que **no abre trabajo nuevo**, con una nota de
    sistema que dice qué se agotó y pide cerrar diciendo dónde quedó el
    trabajo. Una llamada más justo al agotar el presupuesto es deliberado y
    es la misma licencia del §23.2: la llamada que cruza el tope se
    completa. Un turno que cierra cuesta una llamada; un turno que se corta
    cuesta la confianza.

    "No abre trabajo nuevo" **no** es "va sin herramientas»: eso era el
    tercer 400 del §19.1. Las herramientas se declaran igual que en el resto
    del bucle y lo que cierra la puerta es ``tool_choice: "none"``. Va todo
    en :func:`_stream_final_answer`.

    Si esa llamada tampoco produce texto —o falla— hay un cierre
    determinista. E3 no puede depender de que el proveedor coopere.

    Se llama **siempre** que el turno se agota, aunque ya hubiera salido
    texto: cuando el bucle se agota, lo último que escribió el modelo fue un
    preámbulo ("voy a mirar el consumo…") y no una respuesta. Dejar eso solo
    es precisamente cortarse a mitad de frase.
    """
    closing = [*messages, closing_note(reason)]
    text = ""
    usage: dict[str, Any] = {}
    try:
        answer, usage = await _stream_final_answer(
            provider,
            model=model,
            messages=closing,
            specs=specs,
            message_id=message_id,

            effort=effort,
        )
        text = answer.strip()
    except Exception as exc:
        log.warning("companion.closing_step_failed", reason=reason, error=str(exc))
        text = ""

    if text:
        return text, usage

    await _emit("text.delta", {"message_id": message_id, "text": _CLOSING_FALLBACK})
    return _CLOSING_FALLBACK, usage


def _calls_made(toolbelt: Toolbelt) -> int:
    return int(getattr(toolbelt, "calls_made", 0))


def _usage(piece: str) -> dict[str, Any]:
    try:
        parsed = json.loads(piece)
    except ValueError:  # pragma: no cover - defensivo
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _billable_input(usage: dict[str, Any]) -> int:
    """Entrada que de verdad se paga: la que NO vino de caché.

    ``prompt_tokens`` es el prefijo entero que vio el modelo, y en este agente
    el prefijo —prompt de sistema más 32 definiciones de herramientas, del
    orden de 7.000 tokens— viaja en **cada** una de las hasta 12 pasadas del
    bucle. Contarlo a precio pleno doce veces es lo que hacía que la cuota
    mensual se agotara en unos pocos turnos de trabajo real, muy lejos de los
    "300-500 turnos" que promete el defecto de 500.000.

    Anthropic cobra los tokens leídos de caché a una décima parte. Restarlos
    no es una estimación: ``usage_fields()`` extrae ``cache_read_input_tokens``
    del proveedor —con respaldo en ``prompt_tokens_details.cached_tokens``, que
    es como Anthropic lo reporta a veces— y el dato ya viajaba hasta aquí sin
    que nadie lo mirase.

    **Esto no cambia el medidor de ventana de contexto.** Lo que llena la
    ventana es el prefijo entero, venga de caché o no, así que ese sigue
    usando ``prompt_tokens`` bruto. Son dos preguntas distintas y tienen dos
    números distintos a propósito.
    """
    prompt = int(usage.get("prompt_tokens") or 0)
    cached = int(usage.get("cache_read_input_tokens") or 0)
    # ``max(0, …)`` porque un proveedor que reporte la caché por separado en
    # vez de incluirla en ``prompt_tokens`` daría negativo, y una cuota que
    # baja al gastar es peor que una que sobreestima.
    return max(0, prompt - cached)


def _reproducible(assistant: dict[str, Any]) -> dict[str, Any]:
    """El mensaje del asistente, listo para volver al proveedor (§18).

    Anthropic exige que los bloques de pensamiento vuelvan **verbatim y
    firmados**. Con ``display: "summarized"`` lo que devuelve son bloques de
    *resumen*: llegan con ``signature`` vacía y ``thinking`` vacío, y
    devolverlos es un 400 garantizado —

    ::

        messages.1.content.0: Invalid `signature` in `thinking` block
        messages.1.content.2.thinking: each thinking block must contain thinking

    Así que se descartan los que no tengan firma **y** texto. Los que sí los
    tengan vuelven **byte a byte**: esa regla no cambia, y es la que evita el
    otro 400, el de perderlos.

    Si no queda ninguno, la clave se **omite entera**: una lista vacía no es
    lo mismo que ausencia, y no está probada contra el proveedor.

    Esto no toca ``reasoning.delta``: el pensamiento que se pinta en el cajón
    sale del *stream*, no del mensaje que vuelve.
    """
    blocks = assistant.get("thinking_blocks")
    if not isinstance(blocks, list):
        return assistant
    keep = [
        block
        for block in blocks
        if isinstance(block, dict)
        and str(block.get("signature") or "").strip()
        and str(block.get("thinking") or "").strip()
    ]
    if len(keep) == len(blocks):
        return assistant
    ready = {k: v for k, v in assistant.items() if k != "thinking_blocks"}
    if keep:
        ready["thinking_blocks"] = keep
    return ready


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


async def _run_tool(
    toolbelt: Toolbelt, call: dict[str, Any], *, wire_name: str | None = None
) -> dict[str, Any]:
    """Ejecuta una llamada y emite sus tres eventos.

    Los eventos los emite el GRAFO y no el ejecutor: el protocolo del cajón
    es del runtime, y así el paquete de herramientas no depende de LangChain
    ni el grafo de la API.

    ``call["name"]`` es el nombre **del catálogo** (con punto): es el que va
    a los eventos, a la cita y al ejecutor. ``wire_name`` es el que viaja al
    proveedor dentro del mensaje de resultado, y tiene que ser exactamente
    el que el modelo emitió en su ``tool_use`` (§17 del contrato v2.1).

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
        "name": wire_name or to_wire(name),
        # El cuerpo entra VALLADO, y este es el único sitio del runtime donde
        # un resultado de herramienta se convierte en contexto del modelo —
        # por eso el vallado vive aquí y no en el ejecutor: ``ToolOutcome
        # .content`` es el dato estructurado, que el driver de evals y media
        # docena de tests parsean con ``json.loads``. Envolverlo en origen
        # rompería a sus consumidores legítimos; envolverlo aquí no toca a
        # ninguno.
        #
        # El preámbulo no viaja con cada resultado: vive una vez en
        # ``<datos_de_terceros>`` del prompt de sistema, dentro del prefijo
        # que sí se cachea. Lo que impide que un documento se salga de su
        # caja es la neutralización de etiquetas que hace ``fence_only``.
        "content": fence_only(result.content, tag=TAG_TOOL_RESULT),
    }


def make_respond(
    provider: LLMProvider,
    *,
    model: str,
    toolbelt: Toolbelt | None = None,
    effort: str | None = None,
) -> Callable[[CompanionState], Awaitable[dict[str, Any]]]:
    """Cierra el turno: medidores y regla R1.

    En CO-01 este nodo hacía la llamada al modelo. Desde CO-02 esa llamada
    vive en el bucle de ``investigate`` —donde el último mensaje del
    asistente sin herramientas YA es la respuesta—, y aquí queda lo que
    tiene que pasar exactamente una vez por turno, después de todo.

    Sigue recibiendo el proveedor porque un grafo sin ``toolbelt`` no tiene
    bucle: en ese caso este nodo hace la llamada él mismo, que es el
    comportamiento de CO-01 intacto.

    Y recibe el ``toolbelt`` desde CO-06 por una razón que no es el bucle:
    las llamadas de este nodo tienen que **declarar el catálogo** aunque no
    vayan a usarlo (§19.1). El run de continuación replica un historial con
    ``tool_calls``, y sin ``tools=`` Anthropic lo rechaza.
    """

    async def respond(state: CompanionState) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        # Con nombres de cable, como el bucle: el historial que se reenvía
        # los lleva, y las dos cosas tienen que coincidir (§17).
        specs, _catalog_name = wire_tools(_specs(toolbelt))
        if state.get("hitl"):
            # Run de continuación (CO-04): la persona ya decidió y hay que
            # contarle qué pasó. Es una llamada nueva y no un texto armado
            # en Python a propósito: "se aplicó, versión 8 activa" lo puede
            # escribir una plantilla, pero "se aplicó y la verificación dice
            # que solo hay 2 de las 3 herramientas" necesita una frase, y
            # esa frase es el trabajo del modelo.
            updates = await _answer_after_action(provider, model=model, state=state, specs=specs, effort=effort)
        elif not state.get("tool_messages") and not state.get("answer"):
            # Grafo sin herramientas: el camino de CO-01.
            updates = await _answer_without_tools(provider, model=model, state=state, specs=specs, effort=effort)
        else:
            # El bucle terminó sin llegar a escribir (un último paso que
            # solo pidió herramientas, por ejemplo). El tracker lo anuncia
            # solo si hace falta: en el camino normal ya lo anunció el bucle
            # y repetirlo haría parpadear el pill del cajón.
            await _tracker(state).enter(PHASE_RESPOND)

        merged: dict[str, Any] = {**state, **updates}
        input_tokens = int(merged.get("last_input_tokens") or 0)
        await _emit(
            "cost.updated",
            {
                "input_tokens": int(merged.get("total_input_tokens") or 0),
                "output_tokens": int(merged.get("total_output_tokens") or 0),
                # El desglose viaja con el gasto y no en un evento aparte: es
                # la misma pregunta ("¿cuánto costó este turno?") y separarlos
                # obligaría a correlacionar dos eventos para responderla.
                "cache_read": int(merged.get("total_cache_read") or 0),
                "cache_write": int(merged.get("total_cache_write") or 0),
                "steps": int(merged.get("total_steps") or 0),
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


#: Qué se le cuenta al modelo al reanudar, por decisión. Es el
#: ``deny_message`` de Managed Agents: el motivo vuelve al agente para que
#: ajuste el plan, no solo para que diga "vale".
_RESUME_BRIEF: dict[str, str] = {
    "confirm": (
        "La persona CONFIRMÓ la acción y ya se aplicó. Cuéntale en una o dos "
        "frases qué quedó hecho y qué dice la verificación. Si la verificación "
        "falló en algo, dilo primero y sin adornos: puede ser un fallo real de "
        "la plataforma y hay que mirarlo, no darlo por bueno."
    ),
    "edit": (
        "La persona pidió EDITAR la propuesta en vez de aplicarla. No se aplicó "
        "nada. Lee su motivo, ajústate a él y propón de nuevo si tienes claro "
        "qué cambiar; si no lo tienes claro, pregunta una sola cosa concreta."
    ),
    "cancel": (
        "La persona CANCELÓ la acción. No se aplicó nada. Acúsalo en una frase "
        "corta y pregúntale qué prefiere hacer. No insistas ni vuelvas a "
        "proponer lo mismo."
    ),
}

#: Cómo se le dice al proveedor "declaro las herramientas, pero no llames a
#: ninguna" (§19.1 del contrato v2.3).
TOOL_CHOICE_NONE = "none"


async def _stream_final_answer(
    provider: LLMProvider,
    *,
    model: str,
    messages: list[dict[str, Any]],
    specs: list[dict[str, Any]],
    message_id: str,
    effort: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """La ÚLTIMA llamada del turno: no abre trabajo nuevo, pero **declara las
    herramientas igual que las demás**.

    Es el tercer 400 del mismo camino, y el menos intuitivo:

    ::

        litellm.UnsupportedParamsError: Anthropic doesn't support tool calling
        without `tools=` param specified.

    Si ``messages`` lleva mensajes de asistente con ``tool_calls`` —y los
    lleva: el turno acaba de investigar y de aplicar— Anthropic **exige** que
    la declaración de herramientas siga presente. Quitarla no es la forma de
    decir "ya no llames a nada".

    La forma es ``tool_choice: "none"``, y hace falta por sí misma: sin él el
    modelo *puede* volver a llamar, y entonces el paso de cierre deja de ser
    de cierre — nadie ejecutaría esa llamada y el turno acabaría con una
    petición colgando.

    Sin catálogo (el grafo de CO-01, sin juego de herramientas) no hay nada
    que declarar y tampoco hay historial de herramientas: ahí se llama por el
    camino simple.
    """
    chunks: list[str] = []
    usage: dict[str, Any] = {}

    if specs:
        stream = provider.astream_with_tools(
            tenant_id=COMPANION_TENANT_ID,
            role=COMPANION_ROLE,
            model=model,
            messages=messages,
            tools=specs,
            extra=thinking_extra(effort, tool_choice=TOOL_CHOICE_NONE),
        )
    else:
        stream = provider.astream_complete(
            tenant_id=COMPANION_TENANT_ID,
            role=COMPANION_ROLE,
            model=model,
            messages=messages,
            extra=thinking_extra(effort),
        )

    async for kind, piece in stream:
        if kind == "text":
            chunks.append(piece)
            await _emit("text.delta", {"message_id": message_id, "text": piece})
        elif kind == "thinking":
            await _emit("reasoning.delta", {"message_id": message_id, "text": piece})
        elif kind == "usage":
            usage = _usage(piece)
        # ``tool_call`` y ``assistant`` no se atienden a propósito: con
        # ``tool_choice: "none"`` no llegan, y si llegaran, ejecutarlos aquí
        # sería reabrir el turno que se está cerrando.

    return "".join(chunks), usage


async def _answer_after_action(
    provider: LLMProvider,
    *,
    model: str,
    state: CompanionState,
    specs: list[dict[str, Any]],
    effort: str | None = None,
) -> dict[str, Any]:
    """Cierra el turno de continuación con una llamada al modelo.

    El resultado de la verificación entra como mensaje de ``role: system``,
    no dentro de un turno de usuario: es un hecho del motor y no algo que
    nadie pueda falsificar escribiendo en la entrada (Parte II, C4).
    """
    await _tracker(state).enter(PHASE_RESPOND)
    hitl = dict(state.get("hitl") or {})
    decision = str(hitl.get("decision") or "cancel")
    verify = dict(state.get("verify") or {})
    executed = dict(state.get("execute") or {})

    brief = [_RESUME_BRIEF.get(decision, _RESUME_BRIEF["cancel"])]
    note = hitl.get("note")
    if note:
        brief.append(f"Lo que dijo al decidir: «{note}»")
    if decision == "confirm" and executed and not executed.get("ok"):
        # R4 · el "y lo dice". Un plan que falla deja el estado exacto por
        # escrito; "algo salió mal" es lo que obliga a la persona a ir a
        # mirarlo a mano, que es justo lo que el Companion existe para
        # evitar.
        brief.append(
            "LA ACCIÓN NO SE APLICÓ: la escritura falló y **no quedó nada "
            "cambiado**. Dilo primero y con esas palabras, sin suavizarlo, y "
            "di qué puede hacer la persona ahora. No lo verifiques ni lo des "
            "por hecho a medias."
        )
    if verify.get("checks"):
        brief.append(
            "Verificación (releída de la plataforma, no de lo que tú creías): "
            + json.dumps(verify, ensure_ascii=False, sort_keys=True)
        )
    elif decision == "confirm" and executed.get("ok"):
        brief.append("No se pudo verificar el resultado. Dilo; no des el cambio por bueno.")
    if state.get("phase") == PHASE_PUBLISH:
        # R5 · publicar es un acto aparte, y el motor no lo encadena solo.
        brief.append(
            "Esto desemboca en una publicación, y publicar es un acto APARTE: "
            "ofrécelo y espera a que te lo confirmen, con el diff contra la "
            "versión activa delante. No lo publiques ahora."
        )

    messages: list[dict[str, Any]] = [
        *build_messages(
            history=state.get("history"),
            user_message=state.get("user_message", ""),
            page_context=state.get("page_context"),
        ),
        *(state.get("tool_messages") or []),
        {"role": "system", "content": "\n".join(brief)},
    ]

    answer, usage = await _stream_final_answer(
        provider,
        model=model,
        messages=messages,
        specs=specs,
        message_id=str(uuid.uuid4()),

        effort=effort,
    )
    input_tokens = int(usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("completion_tokens") or 0)
    return {
        "answer": answer,
        "model": model,
        "last_input_tokens": input_tokens,
        "total_input_tokens": int(state.get("total_input_tokens") or 0) + _billable_input(usage),
        "total_output_tokens": int(state.get("total_output_tokens") or 0) + output_tokens,
        "total_cache_read": int(state.get("total_cache_read") or 0)
        + int(usage.get("cache_read_input_tokens") or 0),
        "total_cache_write": int(state.get("total_cache_write") or 0)
        + int(usage.get("cache_creation_input_tokens") or 0),
        "total_steps": int(state.get("total_steps") or 0) + 1,
    }


async def _answer_without_tools(
    provider: LLMProvider,
    *,
    model: str,
    state: CompanionState,
    specs: list[dict[str, Any]],
    effort: str | None = None,
) -> dict[str, Any]:
    """El camino de CO-01: una sola llamada en streaming.

    Aquí el turno no llegó a usar ninguna herramienta, así que el historial
    no lleva ``tool_calls`` y el 400 del §19.1 no aplica. Aun así pasa por el
    mismo helper: si hay catálogo se declara —con ``tool_choice: "none"``,
    porque este nodo es de cierre y no debe abrir trabajo nuevo—, y si no lo
    hay se llama por el camino simple. Un único sitio donde equivocarse.
    """
    await _tracker(state).enter(PHASE_RESPOND)
    messages = build_messages(
        history=state.get("history"),
        user_message=state.get("user_message", ""),
        page_context=state.get("page_context"),
    )
    answer, usage = await _stream_final_answer(
        provider,
        model=model,
        messages=messages,
        specs=specs,
        message_id=str(uuid.uuid4()),

        effort=effort,
    )
    input_tokens = int(usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("completion_tokens") or 0)
    return {
        "answer": answer,
        "model": model,
        "last_input_tokens": input_tokens,
        "total_input_tokens": state.get("total_input_tokens", 0) + _billable_input(usage),
        "total_output_tokens": state.get("total_output_tokens", 0) + output_tokens,
        "total_cache_read": state.get("total_cache_read", 0)
        + int(usage.get("cache_read_input_tokens") or 0),
        "total_cache_write": state.get("total_cache_write", 0)
        + int(usage.get("cache_creation_input_tokens") or 0),
        "total_steps": state.get("total_steps", 0) + 1,
    }


# ── CO-04 · planificar, confirmar, ejecutar, verificar ─────────────────


def make_plan(toolbelt: ActionPort) -> Callable[[CompanionState], Awaitable[dict[str, Any]]]:
    """Persiste la acción y anuncia lo que se va a hacer.

    **Este es el nodo "anterior" de la corrección C2.** Todo lo que tiene
    efecto —escribir la fila, emitir ``plan.proposed`` y
    ``hitl.requested``— pasa aquí, y aquí no hay ningún ``interrupt()``.
    LangGraph reanuda re-ejecutando el nodo interrumpido desde su primera
    línea; poniendo las dos cosas juntas, cada confirmación duplicaría la
    fila y emitiría el evento dos veces.

    Y aun así, defensa en profundidad barata: el ``action_id`` es
    determinista (``uuid5`` de ``run_id`` + índice del paso) y la escritura
    es un UPSERT. Si algún día alguien reordena los nodos, lo peor que puede
    pasar es que la fila se sobrescriba consigo misma.
    """

    async def plan(state: CompanionState) -> dict[str, Any]:
        tracker = _tracker(state)
        await tracker.enter(PHASE_PLAN)
        steps = toolbelt.plan_steps()
        await _emit(
            "plan.proposed",
            {
                "plan_id": str(uuid.uuid4()),
                "steps": steps,
                "risk": toolbelt.plan_risk(),
                # AND lógico: un plan es reversible solo si TODOS sus pasos
                # lo son. El paso irreversible manda sobre la media.
                "reversible": all(bool(s.get("reversible")) for s in steps),
                "estimated_tokens": int(state.get("total_input_tokens") or 0)
                + int(state.get("total_output_tokens") or 0),
            },
        )

        # Índice del paso dentro del run. Una acción por run (PLAN-CO-04
        # §D3), así que es 1; la fórmula se mantiene general porque el
        # ``action_id`` depende de ella y cambiarla más tarde dejaría
        # huérfanas las confirmaciones pendientes.
        staged = await toolbelt.stage(1)
        if staged is None:  # pragma: no cover - ``plan`` solo corre con propuesta
            return {"phase": PHASE_PLAN}

        await tracker.enter(PHASE_AWAITING)
        await _emit("hitl.requested", staged)
        return {
            "phase": PHASE_AWAITING,
            "action_id": staged["action_id"],
            "action_kind": staged["kind"],
        }

    return plan


async def await_confirmation(state: CompanionState) -> dict[str, Any]:
    """El nodo del ``interrupt()``. **No hace nada más, y es el punto.**

    Tres reglas, todas de la corrección C2 y todas visibles en estas líneas:

    - **una sola llamada, incondicional.** La correspondencia entre los
      valores de reanudación y los ``interrupt()`` es por índice; saltarse
      uno según una condición desalinea todo lo que venga detrás;
    - **ningún ``try/except`` alrededor.** ``interrupt()`` pausa *lanzando*
      una excepción, y un ``except Exception`` se la traga: el grafo
      seguiría de largo como si le hubieran dicho que sí;
    - **ninguna escritura antes.** Reanudar re-ejecuta este nodo desde la
      primera línea. Lo que persiste está en el nodo ``plan``.

    El valor que devuelve es lo que la API pasó en ``Command(resume=…)``:
    ``{decision, note, by, at}``. La decisión ya está escrita en la fila
    antes de llegar aquí — este nodo no decide nada, solo espera.
    """
    from langgraph.types import interrupt

    decision = interrupt({"action_id": state.get("action_id")})
    return {"hitl": decision if isinstance(decision, dict) else {"decision": str(decision)}}


def make_execute(toolbelt: ActionPort) -> Callable[[CompanionState], Awaitable[dict[str, Any]]]:
    """Aplica la acción confirmada, o recoge el motivo del rechazo.

    ``hitl.resolved`` se emite aquí y es el **primer** evento del run de
    continuación: el run anterior está parado y ya no publica nada.

    Con ``edit`` o ``cancel`` no se aplica nada y el motivo (``note``)
    vuelve al modelo dentro del estado. Es el ``deny_message`` de Managed
    Agents: un rechazo con razón deja que el modelo ajuste el plan; un "no"
    a secas solo le deja repetir la misma propuesta.
    """

    async def execute(state: CompanionState) -> dict[str, Any]:
        hitl = dict(state.get("hitl") or {})
        decision = str(hitl.get("decision") or "cancel")
        action_id = state.get("action_id")

        await _emit(
            "hitl.resolved",
            {
                "action_id": action_id,
                "decision": decision,
                "by": hitl.get("by"),
                "at": hitl.get("at"),
                "note": hitl.get("note"),
            },
        )
        if decision != "confirm" or not action_id:
            # Nada que ejecutar. Se salta también la verificación: verificar
            # algo que nadie aplicó daría una tabla en rojo que no significa
            # nada, y el rojo tiene que seguir queriendo decir algo.
            return {"phase": state.get("phase") or PHASE_AWAITING, "verify": {}, "execute": {}}

        await _tracker(state).enter(PHASE_EXECUTE)
        result = await toolbelt.apply_confirmed(action_id)
        applied = bool(getattr(result, "ok", False))
        return {
            "phase": PHASE_EXECUTE,
            # R4: parar al primer fallo. Con una acción por run es
            # automático — no hay un paso 2 que pudiera correr a ciegas. Lo
            # que faltaba era el "y lo dice": sin este hecho, el nodo de
            # cierre solo veía que no había verificación y tenía que deducir
            # el resto.
            "execute": {"ok": applied, "kind": state.get("action_kind") or ""},
            "verify": {"pending": True} if applied else {},
        }

    return execute


def make_verify(toolbelt: ActionPort) -> Callable[[CompanionState], Awaitable[dict[str, Any]]]:
    """Relee y compara. **Código determinista, corrección C5.**

    Ni un subagente ni una instrucción de "revisa tu trabajo" en ningún
    prompt: la guía de migración a Opus 5 mide que eso produce
    sobre-verificación sin ganancia, y un verificador que es el mismo modelo
    que acaba de actuar no verifica nada — repite su propia confianza.
    """

    async def verify(state: CompanionState) -> dict[str, Any]:
        pending = dict(state.get("verify") or {})
        action_id = state.get("action_id")
        if not pending.get("pending") or not action_id:
            return {"verify": {}}
        tracker = _tracker(state)
        await tracker.enter(PHASE_VERIFY)
        result = await toolbelt.verify(action_id)
        if result is None:  # pragma: no cover - la acción existe si se aplicó
            return {"verify": {}}
        await _emit("verify.result", result)
        if result.get("ok") and _leads_to_publishing(state):
            await tracker.enter(PHASE_PUBLISH)
            return {"verify": result, "phase": PHASE_PUBLISH}
        return {"verify": result, "phase": PHASE_VERIFY}

    return verify


def _leads_to_publishing(state: CompanionState) -> bool:
    """¿Este trabajo desemboca en una publicación? (§2 del contrato v2)

    La fase ``publish`` es el paso 8 del §7, y el contrato pide tres cosas a
    la vez: que la verificación del paso 7 haya salido verde, que se prepare
    la **segunda confirmación** (R5) y que *un turno que solo cambia un
    prompt nunca entre en ``publish``*. Con ``publish`` situado entre
    ``verify`` y ``respond`` en el enum, la única colocación que no
    retrocede es después de un ``verify`` verde, y se entra en dos casos,
    los dos deterministas:

    1. la acción aplicada **es** la publicación — está ocurriendo; o
    2. la acción aplicada cambió un borrador **y el expediente del hilo ya
       tiene un trabajo ``publish``**, es decir, la persona trajo la
       publicación a esta conversación. Ahí el trabajo desemboca en
       publicar y toca preparar la segunda confirmación.

    Un cambio de prompt suelto no cumple ninguno de los dos, que es lo que
    el contrato exige literalmente.
    """
    kind = str(state.get("action_kind") or "")
    if kind == "publish":
        return True
    if kind not in DRAFT_KINDS:
        return False
    ledger = state.get("intake") or {}
    answers = ledger.get("answers") or {}
    asked = ledger.get("asked") or {}
    return bool(answers.get(WORK_PUBLISH)) or bool(asked.get(WORK_PUBLISH))


# ── compilación ────────────────────────────────────────────────────────


def build_companion_graph(
    *,
    provider: LLMProvider,
    model: str,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    toolbelt: Toolbelt | None = None,
    #: Profundidad de razonamiento (``output_config.effort``). ``None`` = la
    #: del proveedor. Es la palanca de coste del D6, y se pasa aquí para que
    #: el runtime no tenga que leer los ajustes de la API.
    effort: str | None = None,
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
        else make_investigate(provider, model=model, toolbelt=toolbelt, effort=effort),
    )
    graph.add_node(
        "respond", make_respond(provider, model=model, toolbelt=toolbelt, effort=effort)
    )
    graph.add_edge(START, "understand")
    graph.add_edge("understand", "investigate")

    if toolbelt is not None and supports_actions(toolbelt):
        # El carril de escritura solo existe cuando el juego de herramientas
        # sabe escribir. Con uno de solo lectura —CO-01, CO-02, y los tests
        # del prompt— el grafo es exactamente el de antes: sin nodos de HITL
        # y, sobre todo, sin un ``interrupt()`` que nadie va a reanudar.
        port: ActionPort = toolbelt  # type: ignore[assignment]
        graph.add_node("intake", make_intake(port))
        graph.add_node("plan", make_plan(port))
        graph.add_node("confirm", await_confirmation)
        graph.add_node("execute", make_execute(port))
        graph.add_node("verify", make_verify(port))
        graph.add_conditional_edges(
            "investigate",
            _needs_confirmation(port),
            {"plan": "plan", "intake": "intake", "respond": "respond"},
        )
        graph.add_edge("intake", "respond")
        graph.add_edge("plan", "confirm")
        graph.add_edge("confirm", "execute")
        graph.add_edge("execute", "verify")
        graph.add_edge("verify", "respond")
    else:
        graph.add_edge("investigate", "respond")

    graph.add_edge("respond", END)
    return graph.compile(checkpointer=checkpointer)


def _needs_confirmation(toolbelt: ActionPort) -> Callable[[CompanionState], str]:
    """¿El turno produjo algo que escribir, y puede escribirlo ya?

    Lo decide el MOTOR mirando si hay una propuesta calculada, no el modelo
    diciendo "y ahora confírmamelo". Un turno que solo leyó va derecho a
    responder y no ve una tarjeta de confirmación vacía.

    Y desde CO-06 mira una segunda cosa: **si el expediente de ese trabajo
    está completo** (§7.1). Con un obligatorio vacío el turno se desvía a
    preguntar y el nodo ``plan`` **no corre** — sin fila persistida, sin
    ``hitl.requested`` y sin nada que confirmar. Es la garantía E1, y falla
    aquí, en el motor: ninguna frase del prompt la puede saltar.
    """

    def route(state: CompanionState) -> str:
        if toolbelt.pending:
            _work_kind, blocked = blocking_slots(
                state.get("intake"), _pending_kind(toolbelt), _specs(toolbelt)
            )
            return "intake" if blocked else "plan"
        # Preguntar gana a responder a secas, pero pierde contra una
        # propuesta ya calculada y completa: si el modelo consiguió los datos
        # en una segunda llamada dentro del mismo turno, lo que falta ya no
        # falta.
        if getattr(toolbelt, "missing_slots", None):
            return "intake"
        return "respond"

    return route


def _specs(toolbelt: Any) -> list[dict[str, Any]]:
    """El catálogo publicado en este turno, si el juego lo tiene.

    Es contra lo que se mide la satisfacibilidad del expediente: exigir un
    dato que la herramienta no acepta bloquearía el trabajo para siempre.
    """
    getter = getattr(toolbelt, "specs", None)
    if getter is None:  # pragma: no cover - defensivo
        return []
    specs = getter()
    return list(specs) if isinstance(specs, list) else []


def _pending_kind(toolbelt: ActionPort) -> str | None:
    """El ``kind`` de la propuesta en espera, sin conocer su clase.

    El grafo no importa ``nexus_api`` en ninguna parte —el worker es el
    runtime de los agentes de cliente y no tiene por qué conocer la
    superficie HTTP de la consola—, así que se lee por atributo, igual que
    el resto del puerto de acciones.
    """
    for proposal in toolbelt.pending or []:
        kind = getattr(proposal, "kind", None)
        if kind:
            return str(kind)
    return None


def make_intake(toolbelt: ActionPort) -> Callable[[CompanionState], Awaitable[dict[str, Any]]]:
    """Anuncia lo que falta para poder proponer (§7.1).

    Va **antes** de responder y no en lugar de responder: el modelo escribe
    la pregunta con sus palabras y el cajón pinta además los huecos como
    chips respondibles. Los dos canales dicen lo mismo, y eso es
    deliberado — quien lee rápido ve los chips, quien lee la frase entiende
    por qué se los piden.

    Responder un hueco **no** es un endpoint nuevo: es un turno más en el
    mismo hilo. Desde CO-06 el expediente **sí** es estado —del hilo, en el
    checkpoint— y por eso lo que se pregunta son los huecos que siguen
    faltando **según el expediente**, no los que la herramienta reportó: un
    dato dado en el turno anterior ya no falta, y volver a pedirlo es el
    ruido que erosiona la disposición de la persona a contestar lo que sí
    importa.
    """

    async def intake(state: CompanionState) -> dict[str, Any]:
        ledger = dict(state.get("intake") or {})
        work_kind, slots = blocking_slots(ledger, _pending_kind(toolbelt), _specs(toolbelt))
        if not slots:
            # Sin propuesta pendiente el aviso viene de la herramienta, que
            # sabe qué trabajo intentaba. Se filtra igual por el expediente.
            reported = list(getattr(toolbelt, "missing_slots", []) or [])
            work_kind = work_kind or _work_kind_of(reported)
            # Sin trabajo reconocible se emite lo reportado tal cual: es
            # mejor una pregunta sin etiqueta que ninguna pregunta.
            slots = missing_slots(ledger, work_kind) if work_kind is not None else reported
        if not slots or work_kind is None:
            return {}

        await _tracker(state).enter(PHASE_INTAKE)
        # ``work_kind`` es nuevo en la v2 y lo añade al catálogo el Agente E:
        # aquí se emite igualmente, porque lo que este nodo produce es lo que
        # se prueba. Lo que el publicador deja pasar es otra zona.
        await _emit("intake.missing", {"slots": slots, "work_kind": work_kind})
        return {
            "phase": PHASE_INTAKE,
            "intake": record_asked(ledger, work_kind, [str(s["key"]) for s in slots]),
        }

    return intake


def _work_kind_of(reported: list[dict[str, Any]]) -> str | None:
    """A qué trabajo pertenecen unos huecos reportados por la herramienta.

    Se deduce de los ``key``, que son estables y cerrados por trabajo (§3.3).
    No es adivinar: es la misma tabla, leída al revés.
    """
    from nexus_worker.runtime.companion.intake import WORK_KINDS, slot_keys

    keys = {str(slot.get("key")) for slot in reported}
    if not keys:
        return None
    for work_kind in WORK_KINDS:
        if keys <= set(slot_keys(work_kind)):
            return work_kind
    return None


__all__ = [
    "COMPANION_ROLE",
    "COMPANION_TENANT_ID",
    "MAX_MODEL_STEPS",
    "TURN_TOKEN_BUDGET",
    "await_confirmation",
    "build_companion_graph",
    "investigate",
    "make_execute",
    "make_intake",
    "make_investigate",
    "make_plan",
    "make_respond",
    "make_verify",
    "understand",
]
