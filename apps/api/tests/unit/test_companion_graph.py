"""El grafo del Companion — prompt, pensamiento y ventana de contexto (CO-01).

Cada prueba de aquí defiende una de las cinco correcciones de la Parte II
de la investigación, o la regla del §12.3. Ninguna toca la red: el
proveedor es ``InMemoryProvider``.
"""

from __future__ import annotations

import uuid

import pytest
from langgraph.checkpoint.memory import MemorySaver
from nexus_worker.runtime.companion import build_companion_graph
from nexus_worker.runtime.companion.prompt import (
    COMPANION_THINKING,
    SYSTEM_PROMPT,
    build_messages,
    page_context_message,
)
from nexus_worker.runtime.llm import InMemoryProvider

# ``asyncio_mode = "auto"``: los tests async se recogen solos y este módulo
# mezcla síncronos (el prompt es una constante) con asíncronos.
PAGE_CONTEXT = {"route": "/clients/boreal/agent", "client_ref": "boreal", "tab": "prompt"}


async def _run(provider: InMemoryProvider, **state):
    graph = build_companion_graph(
        provider=provider, model="anthropic/claude-sonnet-4-6", checkpointer=MemorySaver()
    )
    events: list[tuple[str, dict]] = []
    async for ev in graph.astream_events(
        {"user_message": "hola", "history": [], **state},
        config={"configurable": {"thread_id": str(uuid.uuid4())}},
        version="v2",
    ):
        if ev.get("event") == "on_custom_event":
            events.append((str(ev.get("name")), dict(ev.get("data") or {})))
    return events


# ── C4 · el page_context no puede tocar el prefijo cacheado ────────────


def test_the_system_prompt_is_a_constant_with_no_interpolation() -> None:
    """El caché de Anthropic es un encaje de prefijo: un byte que cambie al
    principio tira todo lo que viene detrás."""
    assert "{" not in SYSTEM_PROMPT and "}" not in SYSTEM_PROMPT
    assert (
        build_messages(history=[], user_message="a", page_context=PAGE_CONTEXT)[0]
        == (build_messages(history=[], user_message="b", page_context=None)[0])
    )


def test_page_context_travels_as_a_mid_conversation_system_message() -> None:
    messages = build_messages(
        history=[], user_message="hazlo más formal", page_context=PAGE_CONTEXT
    )
    ctx = [m for m in messages if m["role"] == "system" and "boreal" in str(m["content"])]
    assert len(ctx) == 1, "el contexto de página no viaja como mensaje de sistema"
    # Después del prefijo estable y ANTES del turno del usuario: es una
    # instrucción con autoridad de operador, no algo que el usuario escribió.
    assert messages.index(ctx[0]) > 0
    assert messages[-1]["role"] == "user"
    assert "boreal" not in SYSTEM_PROMPT


def test_no_page_context_means_no_extra_message() -> None:
    assert page_context_message(None) is None
    assert page_context_message({}) is None
    assert len(build_messages(history=[], user_message="x", page_context=None)) == 2


def test_the_same_page_context_renders_the_same_text() -> None:
    """Dos representaciones distintas del mismo estado serían dos entradas
    de caché distintas para nada."""
    a = page_context_message({"route": "/x", "tab": "y"})
    b = page_context_message({"tab": "y", "route": "/x"})
    assert a == b


# ── C3 · el pensamiento se pide explícitamente ─────────────────────────


def test_thinking_is_summarised_and_never_disabled() -> None:
    """Con ``display`` por defecto (``omitted``) los bloques llegan vacíos.
    Y con ``disabled``, Opus 5 escribe a veces la llamada a herramienta como
    texto visible: el turno termina bien, la herramienta nunca se ejecuta y
    no hay error que capturar."""
    assert COMPANION_THINKING == {"type": "adaptive", "display": "summarized"}
    assert COMPANION_THINKING.get("type") != "disabled"


async def test_the_provider_really_receives_the_thinking_parameter() -> None:
    provider = InMemoryProvider(responder=lambda c: "listo")
    await _run(provider)
    assert provider.calls[0].extra["thinking"] == COMPANION_THINKING


async def test_reasoning_is_streamed_but_never_returned_as_state() -> None:
    """El razonamiento sale por el stream y muere con la sesión: es caro de
    guardar y sus divagaciones se leen luego como compromisos (§8.2)."""
    provider = InMemoryProvider(responder=lambda c: "respuesta", thinking_text="dudando")
    events = await _run(provider)
    reasoning = [d for n, d in events if n == "reasoning.delta"]
    assert reasoning and reasoning[0]["text"] == "dudando"


# ── C5 · la verificación es código, no una instrucción al modelo ───────


def test_the_prompt_never_asks_the_model_to_check_its_own_work() -> None:
    """La guía de migración a Opus 5 va contra el consejo habitual: borrar
    las instrucciones de auto-verificación. El modelo ya verifica solo."""
    lowered = SYSTEM_PROMPT.lower()
    for banned in (
        "verifica tu",
        "revisa tu trabajo",
        "double-check",
        "comprueba tu respuesta",
        "subagente",
        "paso final de verificación",
    ):
        assert banned not in lowered, f"el prompt pide auto-verificación: {banned!r}"


def test_the_prompt_says_it_proposes_but_does_not_apply() -> None:
    """Una capacidad inventada es una promesa rota con el cliente del
    partner, y una capacidad NEGADA que sí existe hace que el agente se
    niegue a usar sus herramientas.

    Desde CO-04 la verdad cambió: hay lectura **y** propuesta, y lo que no
    hay es aplicar por su cuenta. El "todavía no puedes cambiar nada" de
    CO-02 tenía que irse por el mismo motivo por el que se fue el "no puedes
    consultar el estado real" de CO-01 — con las nueve ``propose_*`` puestas
    habría hecho que el agente se negara a usarlas.
    """
    lowered = SYSTEM_PROMPT.lower()
    assert "herramientas de **lectura**" in lowered
    assert "herramientas de **propuesta**" in lowered
    # No aplica: entre proponer y aplicar hay una persona, y el prompt lo
    # dice en voz alta.
    assert "una propuesta **no cambia nada todavía**" in lowered
    assert "no llames a console.apply por" in lowered
    # Y los dos párrafos que ya no son ciertos no pueden volver.
    assert "no puedes consultar el estado real" not in lowered
    assert "todavía **no puedes cambiar nada**" not in lowered


def test_the_prompt_names_the_closed_list_of_what_it_cannot_do() -> None:
    """§6.5. Decirlo en voz alta es más barato que dejar que lo descubra
    chocándose: un "no se puede" tras dos lecturas es una conversación
    perdida."""
    lowered = SYSTEM_PROMPT.lower()
    for forbidden in ("borrar clientes", "facturación", "claves de api", "revelación de ia"):
        assert forbidden in lowered, forbidden


def test_the_prompt_never_mentions_subagents() -> None:
    """Opus 5 delega con demasiada facilidad; el Companion v1 no tiene
    subagentes y nombrarlos solo invita a intentarlo."""
    assert "subagente" not in SYSTEM_PROMPT.lower()


# ── fases y medidores ──────────────────────────────────────────────────


async def test_the_three_phases_are_announced_in_order() -> None:
    provider = InMemoryProvider(responder=lambda c: "ok")
    events = await _run(provider)
    phases = [d["phase"] for n, d in events if n == "phase.changed"]
    assert phases == ["understand", "investigate", "respond"]


async def test_cost_comes_from_the_provider_not_from_a_guess() -> None:
    provider = InMemoryProvider(
        responder=lambda c: "ok", stream_usage={"prompt_tokens": 1234, "completion_tokens": 56}
    )
    events = await _run(provider)
    cost = next(d for n, d in events if n == "cost.updated")
    assert cost["input_tokens"] == 1234
    assert cost["output_tokens"] == 56


async def test_the_context_meter_is_input_tokens_over_max_context() -> None:
    """Estimar la ventana por caracteres en el navegador dejaría fuera el
    prompt de sistema, las definiciones de herramientas y sus resultados —
    que en este agente son la mayor parte. Es mentira y se nota (§12.3)."""
    provider = InMemoryProvider(
        responder=lambda c: "ok", stream_usage={"prompt_tokens": 5000, "completion_tokens": 10}
    )
    events = await _run(provider)
    ctx = next(d for n, d in events if n == "context.updated")
    assert ctx["input_tokens"] == 5000
    assert ctx["max_context"] > 0
    assert ctx["percent"] == pytest.approx(5000 * 100.0 / ctx["max_context"], rel=1e-3)
    assert ctx["compacted"] is False


async def test_the_cache_is_not_billed_but_still_fills_the_window() -> None:
    """El gasto descuenta la caché; la ventana no. Dos números a propósito.

    El prefijo del Companion —prompt de sistema más 32 definiciones de
    herramientas— ronda los 7.000 tokens y viaja en cada una de las hasta 12
    pasadas del bucle. Anthropic lo cobra a una décima parte cuando viene de
    caché, así que contarlo entero doce veces agotaba la cuota mensual en unos
    pocos turnos de trabajo real.

    Pero la ventana de contexto sí se llena con el prefijo entero, venga de
    donde venga: si el medidor descontara la caché, diría que queda sitio
    donde no queda. De ahí que ``cost.updated`` y ``context.updated`` tengan
    que discrepar, y que discrepen exactamente en los tokens cacheados.
    """
    provider = InMemoryProvider(
        responder=lambda c: "ok",
        stream_usage={
            "prompt_tokens": 10_000,
            "completion_tokens": 100,
            "cache_read_input_tokens": 9_000,
        },
    )
    events = await _run(provider)

    cost = next(d for n, d in events if n == "cost.updated")
    assert cost["input_tokens"] == 1_000, "el gasto tiene que descontar la caché"
    assert cost["output_tokens"] == 100

    ctx = next(d for n, d in events if n == "context.updated")
    assert ctx["input_tokens"] == 10_000, "la ventana la llena el prefijo entero"


async def test_the_cost_event_carries_the_cache_breakdown_and_the_steps() -> None:
    """``cost.updated`` lleva lo que hace falta para valorar el turno.

    Y tiene que sobrevivir al **catálogo cerrado** de eventos: el publicador
    elimina cualquier clave no declarada en ``COMPANION_EVENTS``, en silencio.
    Añadir el desglose al grafo sin declararlo allí dejaría los campos a cero
    sin un solo error — y el panel diría que el caché no funciona.
    """
    from nexus_api.api.companion_streaming import COMPANION_EVENTS

    provider = InMemoryProvider(
        responder=lambda c: "ok",
        stream_usage={
            "prompt_tokens": 9_000,
            "completion_tokens": 300,
            "cache_read_input_tokens": 8_000,
            "cache_creation_input_tokens": 500,
        },
    )
    events = await _run(provider)
    cost = next(d for d in (d for n, d in events if n == "cost.updated"))

    assert cost["cache_read"] == 8_000
    assert cost["cache_write"] == 500
    assert cost["steps"] >= 1
    assert cost["input_tokens"] == 1_000

    # El guardián real: lo que el grafo emite tiene que estar declarado.
    assert set(cost) <= COMPANION_EVENTS["cost.updated"], (
        "el publicador borraría estas claves: "
        f"{sorted(set(cost) - COMPANION_EVENTS['cost.updated'])}"
    )


async def test_a_provider_that_reports_cache_apart_never_bills_negative() -> None:
    """Si un proveedor reportara la caché fuera de ``prompt_tokens``, la resta
    daría negativo. Una cuota que baja al gastar es peor que una que
    sobreestima, así que el suelo es cero."""
    provider = InMemoryProvider(
        responder=lambda c: "ok",
        stream_usage={
            "prompt_tokens": 500,
            "completion_tokens": 10,
            "cache_read_input_tokens": 4_000,
        },
    )
    events = await _run(provider)
    cost = next(d for n, d in events if n == "cost.updated")
    assert cost["input_tokens"] == 0


async def test_an_unknown_model_emits_no_context_bar_at_all() -> None:
    """Una barra al 0% sería peor que ninguna barra: la gente la creería."""
    provider = InMemoryProvider(responder=lambda c: "ok")
    graph = build_companion_graph(
        provider=provider,
        model="proveedor/modelo-que-no-esta-en-el-catalogo",
        checkpointer=MemorySaver(),
    )
    names = [
        str(ev.get("name"))
        async for ev in graph.astream_events(
            {"user_message": "hola", "history": []},
            config={"configurable": {"thread_id": str(uuid.uuid4())}},
            version="v2",
        )
        if ev.get("event") == "on_custom_event"
    ]
    assert "cost.updated" in names
    assert "context.updated" not in names


# ── C2 · el hueco del interrupt() está preparado, no cableado ──────────


def test_the_confirmation_node_exists_and_is_not_wired() -> None:
    """Cuando CO-04 lo enchufe, el nodo debe contener SOLO el
    ``interrupt()``: LangGraph reanuda re-ejecutando el nodo desde la
    primera línea, y cualquier escritura anterior se aplicaría dos veces."""
    from nexus_worker.runtime.companion import graph as companion_graph

    assert hasattr(companion_graph, "await_confirmation")
    compiled = build_companion_graph(
        provider=InMemoryProvider(), model="m", checkpointer=MemorySaver()
    )
    assert "await_confirmation" not in compiled.get_graph().nodes


async def test_history_reaches_the_provider_so_the_thread_survives_a_refresh() -> None:
    provider = InMemoryProvider(responder=lambda c: "ok")
    await _run(
        provider,
        history=[
            {"role": "user", "content": "lo de antes"},
            {"role": "assistant", "content": "ya te contesté"},
        ],
    )
    contents = [str(m.get("content")) for m in provider.calls[0].messages]
    assert "lo de antes" in contents
    assert "ya te contesté" in contents
