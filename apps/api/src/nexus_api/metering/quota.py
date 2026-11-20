"""Política de cuota: **un peso por carril**, no uno por modelo (spec 007).

Un hecho = una llamada = los campos nativos (input, output, cache_read,
cache_write). Los dos puntos que debitan —el del Companion y el del canal—
tienen que producir la MISMA cifra; si cada uno inventa la suya, el libro no
puede cuadrarse.

    cuota = redondeo( entrada              x w_in
                    + lectura_de_caché     x w_cache
                    + escritura_en_caché   x w_write
                    + salida               x w_out )

    entrada = max(0, prompt_tokens - cache_read - cache_write)   si w_write > 0
    entrada = max(0, prompt_tokens - cache_read)                 si w_write = 0

**El cuarto carril (spec 065, research.md §D14).** Lo escrito en caché lo facturan
Anthropic y GPT-5.6 a 1,25 veces la entrada; hasta la 065 se cobraba dentro de la entrada,
a 1x, y el multiplicador de ese carril quedaba por debajo del objetivo. Un modelo con peso
de escritura lo saca de la entrada y lo cobra con su peso; uno sin tarifa de escritura
(peso 0) se cobra como antes, con lo escrito dentro de la entrada. ``prompt_tokens`` trae
las dos cachés dentro en las dos familias (``test_cache_write_on_the_wire``), así que la
resta no cuenta nada dos veces.

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
cuantizaba y luego el total ponderado otra vez. Cuatro productos homogéneos se
suman antes de cuantizar, y eso es menos deriva, no más. ``ROUND_HALF_UP``,
mitad se aleja de cero; ``round()`` de Python es banker's (2,5 → 2) y no se usa
aquí.

**La propiedad que esto compra.** El cociente entre lo que cobramos y lo que
cuesta es el mismo en los cuatro carriles, y por tanto **el margen no depende de la
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


def priced_input_tokens(prompt_tokens: int, cache_read: int, cache_write: int = 0) -> int:
    """Entrada que se valora a precio de entrada, en dólares (INC-70).

    LiteLLM da ``prompt_tokens`` con todo dentro: lo leído de caché y lo escrito,
    en Anthropic y en GPT-5.6 (``test_cache_write_on_the_wire``). Las dos cosas se
    pagan en su propia fila, a su tarifa, así que aquí salen las dos.

    Desde la spec 065 es también la entrada de la cuota de un modelo con peso de
    escritura (:func:`lane_quantities`); en uno sin él, la cuota deja lo escrito
    dentro de la entrada, como antes.
    """
    return max(0, uncached_input_tokens(prompt_tokens, cache_read) - max(0, _as_int(cache_write)))


def lane_quantities(
    prompt_tokens: int, cache_read: int, cache_write: int, *, weights: LaneWeights
) -> tuple[int, int, int]:
    """``(entrada, lectura, escritura)`` nativas que cobra cada carril con estos pesos.

    La regla del cuarto carril en un solo sitio, para que ``quota_tokens`` y
    ``billable_qty_for_meter`` no puedan divergir (spec 065):

    - peso de escritura mayor que 0: la entrada sin las dos cachés y lo escrito en su carril;
    - peso 0 (sin tarifa de escritura): lo escrito dentro de la entrada, como antes de la 065.
    """
    cached = max(0, _as_int(cache_read))
    if weights.weighs_writes:
        written = max(0, _as_int(cache_write))
        return priced_input_tokens(prompt_tokens, cache_read, written), cached, written
    return uncached_input_tokens(prompt_tokens, cache_read), cached, 0


def quota_tokens(
    *,
    prompt_tokens: int = 0,
    cache_read: int = 0,
    output_tokens: int = 0,
    cache_write: int = 0,
    weights: LaneWeights,
) -> int:
    """Tope de una llamada, con los cuatro carriles (spec 065).

    ``weights`` son los pesos del modelo **de esta llamada**. Una tarea que
    encadena llamadas a cerebros distintos se pondera llamada a llamada, nunca
    turno a turno: ponderar el turno entero con un solo juego de pesos cobraría
    mal la mitad.

    **El tramo no se aplica aquí.** Lo decide el prompt de UNA llamada, y el copiloto
    llama con los totales del turno: el tramo sobre un total cobraría x5 a un turno
    de varias llamadas cortas. Quien cobra por llamada pasa
    ``weights.for_prompt(prompt_tokens)``.

    **No tiene valor por defecto, a propósito.** Un defecto convertiría cada
    llamada que se olvidara de pasarlo en un cobro silencioso a la baja — el modo
    de fallo que esta spec elimina en todos los demás sitios. Que falte tiene que
    ser un ``TypeError`` en la primera ejecución, no un agujero en el margen
    descubierto cuadrando una factura.
    """
    entry, cached, written = lane_quantities(
        prompt_tokens, cache_read, cache_write, weights=weights
    )
    output = max(0, _as_int(output_tokens))
    total = (
        Decimal(entry) * weights.input
        + Decimal(cached) * weights.cache_read
        + Decimal(written) * weights.cache_write
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
    cache_write: int = 0,
) -> float:
    """``billable_qty`` de UNA fila nativa. No colapsa el desglose.

    - ``llm.input_tokens``: la entrada de :func:`lane_quantities` x ``w_in`` (las
      cachés van en sus filas).
    - ``llm.cache_read``: nativo x ``w_cache``.
    - ``llm.cache_write``: nativo x ``w_write`` (spec 065); 0 si el modelo no
      tiene tarifa de escritura, porque entonces va dentro de la entrada.
    - ``llm.output_tokens``: nativo x ``w_out``.
    - resto: la cantidad medida, como hasta ahora.

    Como ``quota_tokens``, sin tramo: quien desglosa por llamada pasa los pesos de
    ``weights.for_prompt``.

    **Es informativo: quien fija el débito es ``quota_tokens()``.** La suma del
    desglose puede diferir del débito en menos de una unidad, porque el débito se
    cuantiza una vez y el desglose una vez por fila. La asimetría ya existía y se
    declara en vez de repartirse: repartir el redondeo entre carriles exigiría
    una regla que nadie podría defender.
    """
    qty = quantity
    if meter == _LLM_INPUT:
        prompt = _as_int(prompt_tokens if prompt_tokens is not None else qty)
        entry, _cached, _written = lane_quantities(prompt, cache_read, cache_write, weights=weights)
        return float(round_tokens_half_away(Decimal(entry) * weights.input))
    if meter == _LLM_CACHE_READ:
        native = max(0, _as_int(qty))
        return float(round_tokens_half_away(Decimal(native) * weights.cache_read))
    if meter == _LLM_CACHE_WRITE:
        if not weights.weighs_writes:
            return 0.0
        native = max(0, _as_int(qty))
        return float(round_tokens_half_away(Decimal(native) * weights.cache_write))
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
