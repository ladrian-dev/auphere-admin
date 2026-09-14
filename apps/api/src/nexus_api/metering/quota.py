"""Política de cuota: **un peso por carril**, no uno por modelo (spec 007).

Un hecho = una llamada = los campos nativos (input, output, cache_read,
cache_write). Los dos puntos que debitan —el del Companion y el del canal—
tienen que producir la MISMA cifra; si cada uno inventa la suya, el libro no
puede cuadrarse.

    cuota = redondeo( entrada_no_cacheada x w_in
                    + lectura_de_caché    x w_cache
                    + salida              x w_out )

    entrada_no_cacheada = max(0, prompt_tokens - cache_read)

**Qué cambió respecto de la 004, y por qué.** Antes había un solo peso por
modelo, aplicado al total, y la caché llevaba un ``0,1`` plano delante. Un factor
único no puede representar tres precios: los proveedores cobran la salida entre
5x y 6x la entrada, y la caché a una décima parte en Anthropic y en la familia
GPT-5.6 pero a **la mitad** en ``gpt-4o``. El resultado era que el multiplicador
sobre el coste salía distinto en cada carril, y en el carril caro salía **por
debajo de uno**: cinco de los seis modelos del catálogo vendían la salida por
debajo de coste, y el sexto incumplía el suelo en caché.

El ``0,1`` global **ya no existe**. Era la aproximación de un carril con un
número; ahora el carril tiene su peso, que resulta ser una décima parte en unos
modelos y la mitad en otros. Lo que era una coincidencia afortunada —y la
migración 0114 la dejó escrita como tal— ahora es un dato.

**Un solo redondeo.** Antes había dos encadenados: el aporte de la caché se
cuantizaba y luego el total ponderado otra vez. Tres productos homogéneos se
suman antes de cuantizar, y eso es menos deriva, no más. ``ROUND_HALF_UP``,
mitad se aleja de cero; ``round()`` de Python es banker's (2,5 → 2) y no se usa
aquí.

**La propiedad que esto compra.** El cociente entre lo que cobramos y lo que
cuesta es el mismo en los tres carriles, y por tanto **el margen no depende de la
mezcla** de trabajo que haga el partner. La 004 creía tener esta propiedad: la
tenía sólo en su punto de calibración (30 K de prompt, 80 % de acierto de caché,
1,5 K de salida). Con el trabajo de teammate —pesado en salida, y el que la
bolsa incluida paga— el coste real de agotar un pool variaba un 78 % entre
modelos. Ahora varía menos de un 2 %, y lo que queda es redondeo.

Cuota ≠ coste. ADR-007 / ``price_row`` siguen valorando las cantidades nativas.
Esta función sólo responde "cuántas unidades comen el tope".
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from nexus_api.metering.pricing_policy import LaneWeights

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
    """Unidad entera, mitad se aleja de cero. ``2.5 → 3``, no el ``2`` de ``round()``."""
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def uncached_input_tokens(prompt_tokens: int, cache_read: int) -> int:
    """Entrada que no vino de caché. Suelo cero si el vendor parte la cuenta.

    **Nativo, sin ponderar.** Desde la spec 007 esto es lo que el grafo del
    Companion acumula y lo que se persiste: medir y tarifar son dos cosas, y
    mezclarlas es lo que hacía que un cambio de tarifa fuera un cambio en cuatro
    módulos.
    """
    return max(0, _as_int(prompt_tokens) - max(0, _as_int(cache_read)))


def quota_tokens(
    *,
    prompt_tokens: int = 0,
    cache_read: int = 0,
    output_tokens: int = 0,
    cache_write: int = 0,
    weights: LaneWeights,
) -> int:
    """Tope de una llamada. ``cache_write`` se acepta para no olvidarlo: vale 0.

    ``weights`` son los tres pesos del modelo **de esta llamada**. Una tarea que
    encadena llamadas a cerebros distintos se pondera llamada a llamada, nunca
    turno a turno: ponderar el turno entero con un solo juego de pesos cobraría
    mal la mitad.

    **No tiene valor por defecto, a propósito.** Un defecto convertiría cada
    llamada que se olvidara de pasarlo en un cobro silencioso a la baja — el modo
    de fallo que esta spec elimina en todos los demás sitios. Que falte tiene que
    ser un ``TypeError`` en la primera ejecución, no un agujero en el margen
    descubierto cuadrando una factura.
    """
    del cache_write
    uncached = uncached_input_tokens(prompt_tokens, cache_read)
    cached = max(0, _as_int(cache_read))
    output = max(0, _as_int(output_tokens))
    total = (
        Decimal(uncached) * weights.input
        + Decimal(cached) * weights.cache_read
        + Decimal(output) * weights.output
    )
    return round_tokens_half_away(total)


def billable_qty_for_meter(
    meter: str,
    quantity: Any,
    *,
    weights: LaneWeights,
    prompt_tokens: int | None = None,
    cache_read: int = 0,
) -> float:
    """``billable_qty`` de UNA fila nativa. No colapsa el desglose.

    - ``llm.input_tokens``: uncached x ``w_in`` (el cache va en su propia fila).
    - ``llm.cache_read``: nativo x ``w_cache``.
    - ``llm.output_tokens``: nativo x ``w_out``.
    - ``llm.cache_write``: 0 (fuera del tope).
    - resto: la cantidad medida, como hasta ahora.

    **Es informativo: quien fija el débito es ``quota_tokens()``.** La suma del
    desglose puede diferir del débito en menos de una unidad, porque el débito se
    cuantiza una vez y el desglose una vez por fila. La asimetría ya existía y se
    declara en vez de repartirse: repartir el redondeo entre carriles exigiría
    una regla que nadie podría defender.
    """
    qty = quantity
    if meter == _LLM_INPUT:
        prompt = _as_int(prompt_tokens if prompt_tokens is not None else qty)
        uncached = uncached_input_tokens(prompt, cache_read)
        return float(round_tokens_half_away(Decimal(uncached) * weights.input))
    if meter == _LLM_CACHE_READ:
        native = max(0, _as_int(qty))
        return float(round_tokens_half_away(Decimal(native) * weights.cache_read))
    if meter == _LLM_CACHE_WRITE:
        return 0.0
    if meter == _LLM_OUTPUT:
        native = max(0, _as_int(qty))
        return float(round_tokens_half_away(Decimal(native) * weights.output))
    if isinstance(qty, (int, float)) and not isinstance(qty, bool):
        return float(qty)
    if isinstance(qty, Decimal):
        return float(qty)
    try:
        return float(qty)
    except (TypeError, ValueError):
        return 0.0
