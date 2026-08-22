"""Política C3 de cuota en tokens nativos del proveedor.

Un hecho = una llamada = los campos nativos (input, output, cache_read,
cache_write). Companion y el consumidor de canal tienen que debitar la
MISMA cifra; si cada uno inventa la suya, el libro de Fase 3 no puede
alimentarse.

    quota = uncached_input + 0.1 * cache_read + output
    uncached_input = max(0, prompt_tokens - cache_read)

``cache_read`` cuenta **0.1**, igual que en la factura de Anthropic.
``cache_write`` no entra en la cuota (no se inventa un quinto
multiplicador). Nunca se suma el prompt bruto + cache_read: eso
doble-cuenta el acierto de caché.

Quota ≠ coste. ADR-007 / ``price_row`` siguen valorando las cantidades
nativas. Esta función solo responde "cuántos tokens comen el tope".

Redondeo a token entero: half away from zero (``Decimal``
``ROUND_HALF_UP``). ``round()`` de Python es banker's (2.5 → 2) y no se
usa aquí.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

CACHE_READ_QUOTA_WEIGHT = Decimal("0.1")

_LLM_INPUT = "llm.input_tokens"
_LLM_OUTPUT = "llm.output_tokens"
_LLM_CACHE_READ = "llm.cache_read"
_LLM_CACHE_WRITE = "llm.cache_write"


def _as_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        return int(value)
    if isinstance(value, float):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def round_tokens_half_away(value: Decimal) -> int:
    """Token entero, mitad se aleja de cero. ``2.5 → 3``, no el ``2`` de ``round()``."""
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def uncached_input_tokens(prompt_tokens: int, cache_read: int) -> int:
    """Entrada que no vino de caché. Suelo cero si el vendor parte la cuenta."""
    return max(0, _as_int(prompt_tokens) - max(0, _as_int(cache_read)))


def cache_read_quota_tokens(cache_read: int) -> int:
    """Aporte de ``cache_read`` a la cuota: 0.1 x nativo, token entero."""
    native = max(0, _as_int(cache_read))
    return round_tokens_half_away(Decimal(native) * CACHE_READ_QUOTA_WEIGHT)


def quota_input_tokens(*, prompt_tokens: int = 0, cache_read: int = 0) -> int:
    """Entrada que come el tope: uncached + 0.1 x cache_read."""
    return uncached_input_tokens(prompt_tokens, cache_read) + cache_read_quota_tokens(cache_read)


def quota_tokens(
    *,
    prompt_tokens: int = 0,
    cache_read: int = 0,
    output_tokens: int = 0,
    cache_write: int = 0,
) -> int:
    """Tope de una llamada. ``cache_write`` se acepta para no olvidarlo: vale 0."""
    del cache_write
    return quota_input_tokens(prompt_tokens=prompt_tokens, cache_read=cache_read) + max(
        0, _as_int(output_tokens)
    )


def billable_qty_for_meter(
    meter: str,
    quantity: Any,
    *,
    prompt_tokens: int | None = None,
    cache_read: int = 0,
) -> float:
    """``billable_qty`` de UNA fila nativa. No colapsa el desglose.

    - ``llm.input_tokens``: uncached (el cache va en su propia fila).
    - ``llm.cache_read``: 0.1 x nativo.
    - ``llm.output_tokens``: nativo.
    - ``llm.cache_write``: 0 (fuera del tope).
    - resto: la cantidad medida, como hasta ahora.
    """
    qty = quantity
    if meter == _LLM_INPUT:
        prompt = _as_int(prompt_tokens if prompt_tokens is not None else qty)
        return float(uncached_input_tokens(prompt, cache_read))
    if meter == _LLM_CACHE_READ:
        return float(cache_read_quota_tokens(_as_int(qty)))
    if meter == _LLM_CACHE_WRITE:
        return 0.0
    if meter == _LLM_OUTPUT:
        return float(max(0, _as_int(qty)))
    if isinstance(qty, (int, float)) and not isinstance(qty, bool):
        return float(qty)
    if isinstance(qty, Decimal):
        return float(qty)
    try:
        return float(qty)
    except (TypeError, ValueError):
        return 0.0
