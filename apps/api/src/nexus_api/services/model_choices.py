"""Qué modelos puede elegir un teammate, con su nota y su coste (R2.1).

El formulario pide elegir un «cerebro», y elegir sin saber qué cuesta es elegir
a ciegas. Pero un precio por millón de tokens tampoco ayuda a decidir: lo que
la persona necesita saber es **si este gasta más que aquél**.

Así que el coste se publica como una etiqueta relativa —``bajo`` · ``medio`` ·
``alto``— calculada **dentro de la oferta que esa persona ve**, no contra una
tabla de umbrales en dólares. Dos razones:

1. Un umbral fijo envejece con cada bajada de precios del proveedor y hay que
   recordarlo; una comparación entre los modelos ofrecidos sigue siendo cierta
   sola.
2. La etiqueta es un **identificador estable**, no una frase: la pantalla pone
   la palabra, aquí solo se dice cuál.

Cuando no hay tarifa cargada la etiqueta es ``desconocido``, que es una ausencia
diseñada y no un cero: valorar a cero lo que no sabemos costar es exactamente
la mentira que ``model_profiles`` evita dejando la tarifa en ``NULL``.
"""

from __future__ import annotations

import decimal
import uuid
from collections.abc import Mapping, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.partner_allowlist import read_allowlist
from nexus_api.core.respond_catalog import RESPOND_MODELS

COST_LOW = "bajo"
COST_MID = "medio"
COST_HIGH = "alto"
COST_UNKNOWN = "desconocido"
COST_LABELS: tuple[str, ...] = (COST_LOW, COST_MID, COST_HIGH, COST_UNKNOWN)


def cost_labels(prices: Mapping[str, decimal.Decimal | None]) -> dict[str, str]:
    """Precio de salida por millón → etiqueta relativa, por modelo.

    Reglas, todas comprobables: sin tarifa → ``desconocido``; si todos los que
    sí la tienen cuestan lo mismo, ninguno es más caro que otro y **todos** son
    ``medio`` (decir ``bajo`` de un empate sería inventar una diferencia); si
    no, el más barato es ``bajo``, el más caro ``alto``, y el resto ``medio``.
    """
    known = {k: v for k, v in prices.items() if v is not None}
    labels = {k: COST_UNKNOWN for k in prices}
    if not known:
        return labels
    low, high = min(known.values()), max(known.values())
    for model_id, price in known.items():
        if low == high:
            labels[model_id] = COST_MID
        elif price == low:
            labels[model_id] = COST_LOW
        elif price == high:
            labels[model_id] = COST_HIGH
        else:
            labels[model_id] = COST_MID
    return labels


async def model_choices(session: AsyncSession, partner_id: uuid.UUID) -> list[tuple[str, str, str]]:
    """``(model_id, nota, etiqueta de coste)`` para la oferta de este partner.

    La oferta es el catálogo cerrado ∩ la lista del partner —la misma
    intersección que la consola usa para el rol ``respond``, y no otra, para
    que la app no ofrezca un modelo que la consola niega—. La nota sale de
    ``model_profiles`` cuando está cargado y del catálogo en código cuando no:
    una fila sin nombre legible no ayuda a elegir.
    """
    allowed = await read_allowlist(session, partner_id)
    offered = [(mid, display) for mid, display in RESPOND_MODELS if mid in allowed]
    if not offered:
        return []
    ids = [mid for mid, _ in offered]
    rows: Sequence[sa.Row[tuple[str, str, decimal.Decimal | None]]] = (
        await session.execute(
            sa.text(
                "SELECT model_id, display_name, price_output_per_mtok "
                "FROM model_profiles WHERE model_id = ANY(:ids)"
            ),
            {"ids": ids},
        )
    ).all()
    profiles = {str(r[0]): (str(r[1]), r[2]) for r in rows}
    labels = cost_labels({mid: profiles.get(mid, (None, None))[1] for mid in ids})
    return [
        (mid, profiles.get(mid, (display, None))[0] or display, labels[mid])
        for mid, display in offered
    ]


__all__ = [
    "COST_HIGH",
    "COST_LABELS",
    "COST_LOW",
    "COST_MID",
    "COST_UNKNOWN",
    "cost_labels",
    "model_choices",
]
