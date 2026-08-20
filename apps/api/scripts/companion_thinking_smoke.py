#!/usr/bin/env python
"""Prueba de humo del pensamiento del Companion contra el proveedor real.

Riesgo asumido en CO-01 (§4.1 de ``docs/companion/PLAN-CO-01.md``): nadie
había verificado ``thinking={"type": "adaptive", "display": "summarized"}``
contra Anthropic. El test unitario solo comprueba que el parámetro sale en
los kwargs, y eso no dice nada de lo que devuelve el proveedor.

Media verificación SÍ se puede hacer sin red, y está hecha en
``tests/unit/test_companion_thinking_contract.py``: LiteLLM 1.83 declara
``thinking`` como parámetro soportado de Anthropic y lo mete **verbatim**
en el cuerpo de la petición, sin renombrarlo ni descartarlo. Lo que queda
—si el proveedor devuelve resúmenes de pensamiento con texto o bloques
vacíos— solo se sabe llamando.

Uso, desde ``apps/api``::

    ANTHROPIC_API_KEY=sk-ant-… uv run python scripts/companion_thinking_smoke.py

Sale 0 si llegó al menos un trozo de pensamiento CON texto, 1 si los
bloques llegaron vacíos (que es exactamente el fallo que CO-03 descubriría
tarde y caro), 2 si no se pudo llamar.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from typing import Any

PROMPT = (
    "Un partner tiene tres clientes y quiere saber cuál conviene publicar primero. "
    "Piensa el criterio antes de responder, y responde en dos frases."
)

#: Tenant sintético del Companion, el mismo que usa el grafo.
SMOKE_TENANT = uuid.UUID("00000000-0000-0000-0000-00000000c0a1")


async def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("falta ANTHROPIC_API_KEY en el entorno", file=sys.stderr)
        return 2

    from nexus_worker.runtime.companion.prompt import COMPANION_THINKING, SYSTEM_PROMPT
    from nexus_worker.runtime.llm import LiteLLMProvider

    model = os.environ.get("COMPANION_SMOKE_MODEL", "anthropic/claude-sonnet-4-6")
    provider = LiteLLMProvider(timeout_s=60.0)

    thinking_chars = 0
    text_chars = 0
    try:
        async for kind, piece in provider.astream_complete(
            tenant_id=SMOKE_TENANT,
            role="companion",
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": PROMPT},
            ],
            extra={"thinking": COMPANION_THINKING},
        ):
            if kind == "thinking":
                thinking_chars += len(piece)
                print(f"\033[2m{piece}\033[0m", end="", flush=True)
            elif kind == "text":
                text_chars += len(piece)
                print(piece, end="", flush=True)
            elif kind == "usage":
                print(f"\n[usage] {piece}")
    except Exception as exc:  # pragma: no cover - script
        print(f"\nla llamada falló: {exc}", file=sys.stderr)
        return 2

    print(f"\n\nmodelo={model} · pensamiento={thinking_chars} chars · texto={text_chars} chars")
    if thinking_chars == 0:
        print(
            "FALLO: el pensamiento llegó vacío. Es el riesgo C3. Comprueba que "
            "'display' se sigue llamando así en la versión de LiteLLM instalada, "
            "que el modelo lo admite, y que nadie metió {'type': 'disabled'}.",
            file=sys.stderr,
        )
        return 1
    print("OK: el proveedor devuelve resúmenes de pensamiento con texto.")

    return await _tools_roundtrip(provider, model=model)


async def _tools_roundtrip(provider: Any, *, model: str) -> int:
    """El ida y vuelta CON herramientas — las tres restricciones del D12.

    El humo de arriba corre por ``astream_complete`` y no declara herramientas,
    así que no toca el camino que escribe. Las tres restricciones que el D12
    del ADR-033 descubrió daban 400 **solo** con herramientas declaradas, y las
    tres estaban en el código desde CO-01 sin que ninguna suite las viera:

    1. **Los nombres no pueden llevar punto.** El catálogo usa
       ``console.list_clients``; al proveedor va ``console__list_clients``
       (:func:`to_wire`). Si la traducción se rompe, esta llamada da 400.
    2. **Los bloques de pensamiento resumido no se pueden devolver.** Llegan
       con firma y texto vacíos; :func:`_reproducible` descarta los
       irreproducibles y conserva los firmados. Se ejercita al reenviar el
       mensaje del asistente en la segunda llamada.
    3. **La última llamada no puede omitir ``tools``** si el historial ya
       contiene uso de herramientas. Se declaran igual y lo que cierra la
       puerta es ``tool_choice: "none"``.

    Un proveedor guionizado no puede encontrar ninguna de las tres. Por eso
    esto llama de verdad.
    """
    import json

    from nexus_worker.runtime.companion.graph import _reproducible
    from nexus_worker.runtime.companion.prompt import COMPANION_THINKING, SYSTEM_PROMPT
    from nexus_worker.runtime.companion.tools import to_wire, wire_tools

    from nexus_api.companion.tools.catalog import tool_specs

    print("\n── ida y vuelta con herramientas (D12) ──")
    # ``wire_tools`` devuelve (specs traducidas, nombre_de_cable → nombre_de_catálogo).
    specs, _catalog_by_wire = wire_tools(tool_specs(mode="build"))
    names = [s["function"]["name"] for s in specs]
    if any("." in n for n in names):
        print(f"FALLO: {sum('.' in n for n in names)} nombres llevan punto", file=sys.stderr)
        return 1
    print(f"catálogo: {len(specs)} herramientas, nombres traducidos (p. ej. {names[0]})")

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "¿Cuántos clientes tengo? Míralo."},
    ]
    assistant: dict[str, Any] | None = None
    requested: list[dict[str, Any]] = []
    try:
        async for kind, piece in provider.astream_with_tools(
            tenant_id=SMOKE_TENANT,
            role="companion",
            model=model,
            messages=messages,
            tools=specs,
            extra={"thinking": COMPANION_THINKING},
        ):
            if kind == "tool_call":
                requested.append(json.loads(piece))
            elif kind == "assistant":
                assistant = json.loads(piece)
    except Exception as exc:
        print(f"FALLO en la llamada CON herramientas: {exc}", file=sys.stderr)
        return 1

    if not requested:
        print("AVISO: el modelo no pidió ninguna herramienta; el ciclo no se completa.")
        return 0
    call = requested[0]
    print(f"el modelo pidió: {call.get('name')}")

    # Restricciones 2 y 3: el asistente vuelve saneado, el resultado detrás, y
    # las herramientas se declaran igual con la puerta cerrada.
    messages.append(_reproducible(assistant) if assistant else {"role": "assistant", "content": ""})
    messages.append(
        {
            "role": "tool",
            "tool_call_id": str(call.get("id") or "t1"),
            "name": to_wire(str(call.get("name") or "")),
            "content": '<tool_result>\n{"items": [], "total": 0}\n</tool_result>',
        }
    )
    closing = 0
    closing_thinking = 0
    extra_calls = 0
    try:
        async for kind, piece in provider.astream_with_tools(
            tenant_id=SMOKE_TENANT,
            role="companion",
            model=model,
            messages=messages,
            tools=specs,
            extra={"thinking": COMPANION_THINKING, "tool_choice": "none"},
        ):
            if kind == "text":
                closing += len(piece)
                print(piece, end="", flush=True)
            elif kind == "thinking":
                closing_thinking += len(piece)
            elif kind == "tool_call":
                extra_calls += 1
    except Exception as exc:
        print(f"\nFALLO al cerrar el turno con tool_choice=none: {exc}", file=sys.stderr)
        return 1

    print(f"\n\ncierre: texto={closing} chars · pensamiento={closing_thinking} chars")
    if extra_calls:
        # ``tool_choice: "none"`` es lo único que cierra la puerta. Si aun así
        # pide herramientas, la garantía E3 no se sostiene y el turno puede
        # no terminar nunca.
        print(f"FALLO: pidió {extra_calls} herramientas pese a tool_choice=none", file=sys.stderr)
        return 1
    if closing == 0:
        # **No es un fallo, y decirlo importa.** Con ``tool_choice: "none"`` el
        # modelo gasta a veces el turno entero en pensamiento y no emite texto
        # — reproducible contra Anthropic, y algo que un proveedor guionizado
        # nunca produce porque siempre devuelve lo que le dictan.
        #
        # El grafo ya lo cubre: ``_close_the_turn`` comprueba el texto y, si
        # viene vacío, emite ``_CLOSING_FALLBACK`` (``graph.py``, "E3 no puede
        # depender de que el proveedor coopere"). Lo que este humo aporta es
        # que esa red **se usa de verdad**, no que sea una precaución teórica.
        print(
            "AVISO: el cierre no produjo texto (todo fue pensamiento). "
            "El grafo lo cubre con el cierre determinista de _close_the_turn, "
            "así que el turno NO queda mudo en producción. Queda anotado "
            "porque confirma que ese fallback se ejercita de verdad."
        )
    else:
        print("OK: el cierre produjo texto propio.")
    print("Las tres restricciones del D12 se sostienen contra el proveedor real.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
