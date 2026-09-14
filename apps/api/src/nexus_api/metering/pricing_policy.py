"""Qué medidor se valora por dónde (spec 004, R1.6).

Hay **dos** formas de ponerle precio a un medidor en esta plataforma, y la
diferencia no es de implementación sino de naturaleza:

- **Por modelo** — ``model_profiles`` (migración 0072) guarda una tarifa por
  millón de tokens, o por minuto para la voz. Vale para lo que tiene un modelo
  detrás.
- **Por unidad** — ``meter_prices`` (migración 0083) guarda un precio plano por
  unidad, para lo que **no tiene modelo**: un adjunto no corre en ningún
  cerebro, es una unidad.

Un medidor que no esté en ninguna de las dos se mide y **no se valora**, y
``SUM(cost_usd)`` lo ignora en silencio: aporta un cero perfectamente creíble a
cualquier panel de margen y nadie tiene motivo para dudar de él. Por eso la
tercera lista existe. No valorar algo es una decisión legítima; no haberse dado
cuenta, no. La diferencia entre las dos se escribe aquí.

**Un medidor no puede estar en las dos primeras listas.** Valorarlo por modelo
y por unidad a la vez lo cobra dos veces, o toma el que la consulta lea primero
—que no es determinista—, y ninguno de los dos casos levanta un error.

> **Nota sobre el ítem C2 de `PLAN-PENDIENTE-CORTE-2026-09-08`.** Pedía «filas
> de `meter_prices` para `llm.input_tokens`, `llm.output_tokens`,
> `llm.cache_read` y `channel.message`». Los tres primeros **no deben tenerla**:
> ya se valoran contra `model_profiles`, y darles además un precio unitario es
> exactamente la doble valoración que el párrafo de arriba describe. Se cumple
> el espíritu del ítem —que ningún medidor quede sin cuenta— por el camino que
> no cobra dos veces.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

#: Se valoran contra ``model_profiles``: llevan un modelo detrás.
#: ``llm.cache_write`` está aquí aunque en los proveedores de OpenAI del
#: catálogo cerrado la tarifa sea NULL: el sitio donde se valoraría es
#: ``model_profiles``, y que la tarifa esté ausente es otra cuestión.
MODEL_PRICED_METERS: frozenset[str] = frozenset(
    {
        "llm.input_tokens",
        "llm.output_tokens",
        "llm.cache_read",
        "llm.cache_write",
        "voice.minutes",
    }
)

#: Medidos a propósito y **no valorados**, con el motivo. Cada entrada de aquí
#: es una decisión que alguien tomó, no una fila que se quedó sin precio.
NOT_VALUED_METERS: frozenset[str] = frozenset(
    {
        # Lo que cuesta un mensaje de canal lo factura Meta, y ese importe ya
        # vive en ``messages.cost_usd``. Ponerle además un precio unitario aquí
        # lo contaría dos veces en el mismo panel.
        "channel.message",
        # Actividad, no coste. Un paso de workflow y una llamada a herramienta
        # cuestan exactamente los ``llm.*`` que generan, y ésos ya se valoran.
        # Cobrarlos aparte sería cobrar dos veces el mismo turno.
        "workflow.step",
        "tool.call",
        # Éste SÍ tiene coste real (S3), y no hay cifra verificada. Se deja sin
        # valorar en vez de sembrar un número plausible: el criterio de 0072 es
        # que NULL dice la verdad y un número inventado ensucia el margen sin
        # que nadie lo note. Entra aquí el día que se mida, no antes.
        "storage.gb_month",
    }
)


class UnweightedModel(RuntimeError):
    """El modelo está en el catálogo y no tiene peso de cuota declarado.

    Spec 004, R3.4. Se **rechaza el turno** en vez de atenderlo con un peso
    supuesto: un peso neutro nos come el margen en silencio y el del modelo más
    caro le cobra de más al partner por un olvido que no es suyo. Además no es
    un modo de fallo nuevo — la plataforma ya rechaza un modelo que no está en
    el catálogo, y esto es la misma clase de error de configuración, a una fila
    de arreglarse.
    """


def lane_needs_weight(meter: str) -> bool:
    """¿Pasa este medidor por la cuota de LLM, y por tanto necesita peso?

    **Solo los medidores de token.** ``voice.minutes`` se mide por minutos y
    ``media.*`` por unidades; ninguno pasa por ``quota_tokens()``, así que a
    ``openai/whisper-1`` no le hace falta peso y **debe seguir funcionando** sin
    él. Está escrito aquí, y no solo en un comentario, porque es exactamente lo
    que alguien "arregla" dentro de seis meses poniéndole un 1,0 a whisper y
    rompiendo la invarianza sin que salte un test.
    """
    return meter in MODEL_PRICED_METERS and meter != "voice.minutes"


def weight_for(model_id: str, weights: Mapping[str, Decimal | None]) -> Decimal:
    """El peso único de un modelo, o ``UnweightedModel`` con su nombre dentro.

    **DEPRECADA (spec 007).** La sustituye ``weights_for``, que devuelve el peso
    de cada carril. Se conserva mientras quede algún llamante; se retira cuando
    no quede ninguno, no antes: quitarla de golpe convertiría un cambio de
    fórmula en un cambio de fórmula **y** una cascada de imports rotos, y las dos
    cosas juntas se revisan peor que por separado.
    """
    weight = weights.get(model_id)
    if weight is None:
        raise UnweightedModel(
            f"{model_id} has no quota_weight: it is in the catalog but cannot be "
            "charged against a pool. Load its weight in model_profiles."
        )
    return Decimal(weight)


#: Los tres carriles que llevan peso. ``cache_write`` **no está**, y no es un
#: olvido: la escritura en caché no come tope y no gana un cuarto multiplicador.
LANES: tuple[str, ...] = ("input", "cache_read", "output")


@dataclass(frozen=True)
class LaneWeights:
    """Cuántas unidades de cuota cuesta un token de cada carril (spec 007, R1).

    Cada uno se deriva de la tarifa de **su propio carril**, de modo que el
    cociente entre lo cobrado y lo que cuesta sea el mismo en los tres. Esa es
    la propiedad entera: **el margen deja de depender de la mezcla** de entrada,
    caché y salida que produzca el trabajo del partner.
    """

    input: Decimal
    cache_read: Decimal
    output: Decimal


def weights_for(
    model_id: str,
    weights: Mapping[str, Mapping[str, Decimal | None] | None],
) -> LaneWeights:
    """Los tres pesos de un modelo, o ``UnweightedModel`` diciendo qué falta.

    **Los tres o ninguno.** Un modelo con dos pesos y uno nulo se rechaza igual
    que uno sin ninguno, y el modo de fallo peligroso es justamente ése: parece
    configurado, y el carril que falta es el que nadie mira hasta que cuadra una
    factura. El esquema lo impide con un ``CHECK`` (0120) y esto lo impide sin
    depender de la base — porque un catálogo se sirve desde una caché en memoria
    y un ``CHECK`` no protege lo que ya está cargado.

    El error **nombra el modelo y el carril**: en producción, quien lo lea tiene
    que saber qué fila mirar sin abrir un depurador.
    """
    lanes = weights.get(model_id)
    if lanes is None:
        raise UnweightedModel(
            f"{model_id} has no quota lane weights: it is in the catalog but cannot "
            "be charged against a pool. Load its three weights in model_profiles."
        )
    missing = [lane for lane in LANES if lanes.get(lane) is None]
    if missing:
        raise UnweightedModel(
            f"{model_id} is missing the quota weight for {', '.join(missing)}: "
            "a model is weighted on all three lanes or on none. Load the missing "
            "one in model_profiles."
        )
    return LaneWeights(
        input=Decimal(lanes["input"]),  # type: ignore[arg-type]
        cache_read=Decimal(lanes["cache_read"]),  # type: ignore[arg-type]
        output=Decimal(lanes["output"]),  # type: ignore[arg-type]
    )


#: Lo que se cobra sobre el coste de proveedor (spec 007). El **objetivo** puede
#: moverse por decisión comercial; el **suelo** es la regla que hace que esa
#: decisión no pueda ser un descuido.
QUOTA_TARGET_MULTIPLIER = Decimal("2.2")
QUOTA_FLOOR_MULTIPLIER = Decimal("1.50")


@dataclass(frozen=True)
class WeightDrift:
    """Un carril cuyo peso ya no corresponde a su tarifa (spec 007, R6)."""

    model_id: str
    lane: str
    stored: Decimal
    expected: Decimal
    multiplier: Decimal

    @property
    def below_floor(self) -> bool:
        """¿La divergencia hunde el carril por debajo del suelo?

        Un peso que se quedó viejo y sigue sobre el suelo es una imprecisión;
        uno que lo cruza es dinero saliendo. No pueden dar el mismo aviso.
        """
        return self.multiplier < QUOTA_FLOOR_MULTIPLIER


def weight_drift(
    prices: Mapping[str, Mapping[str, Decimal | None]],
    weights: Mapping[str, Mapping[str, Decimal | None] | None],
    *,
    sell_usd_per_million: Decimal,
    tolerance: Decimal = Decimal("0.000001"),
) -> list[WeightDrift]:
    """Carriles cuyo peso guardado no corresponde ya a su tarifa.

    **Por qué esto existe y no se deriva el peso en cada llamada.** Derivarlo
    haría imposible la divergencia —lo que no se duplica no puede divergir— pero
    acoplaría dos cosas deliberadamente independientes: la tarifa es un hecho
    externo que cambia cuando el proveedor quiere, y el peso es una decisión
    comercial nuestra. Con la derivación como fórmula, cualquier subida de tarifa
    se trasladaría al partner el mismo minuto, sin que nadie lo decidiera, y el
    contador se movería solo — que es justo lo que ``model_profile.py`` lleva
    advirtiendo desde la 004.

    Así que la derivación se conserva **como comprobación**: lo bueno de la idea
    sin el acoplamiento. Se ejecuta al cargar el catálogo y no bloquea nada — una
    divergencia no puede tumbar la plataforma, pero tampoco puede ser invisible.
    """
    lane_prices = {"input": "input", "cache_read": "cache_read", "output": "output"}
    drifts: list[WeightDrift] = []
    for model_id, lanes in weights.items():
        if lanes is None or any(lanes.get(lane) is None for lane in LANES):
            continue
        model_prices = prices.get(model_id) or {}
        for lane in LANES:
            price = model_prices.get(lane_prices[lane])
            stored = lanes.get(lane)
            if price is None or stored is None or Decimal(price) <= 0:
                continue
            expected = QUOTA_TARGET_MULTIPLIER * Decimal(price) / sell_usd_per_million
            if abs(Decimal(stored) - expected) <= tolerance:
                continue
            drifts.append(
                WeightDrift(
                    model_id=model_id,
                    lane=lane,
                    stored=Decimal(stored),
                    expected=expected,
                    multiplier=Decimal(stored) * sell_usd_per_million / Decimal(price),
                )
            )
    return drifts


__all__ = [
    "LANES",
    "MODEL_PRICED_METERS",
    "NOT_VALUED_METERS",
    "QUOTA_FLOOR_MULTIPLIER",
    "QUOTA_TARGET_MULTIPLIER",
    "LaneWeights",
    "UnweightedModel",
    "WeightDrift",
    "lane_needs_weight",
    "weight_drift",
    "weight_for",
    "weights_for",
]
