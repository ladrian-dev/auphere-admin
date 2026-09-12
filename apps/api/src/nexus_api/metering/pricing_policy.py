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

__all__ = ["MODEL_PRICED_METERS", "NOT_VALUED_METERS"]
