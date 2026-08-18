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
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
