"""Spec 007 · el suelo, contra el catálogo REAL.

**Este fichero no lleva ninguna lista de modelos, y es lo único que lo hace
útil.** Un test que enumera los seis de hoy pasa en verde el día que alguien
añade el séptimo y no lo actualiza — que es exactamente el fallo que hay que
impedir. La fuente es ``model_profiles``, y crece sola.

El invariante se comprueba **sobre el valor almacenado**, después del redondeo
de la columna (R2.2): lo que cobramos es lo que hay en la fila, no lo que la
fórmula habría dado con precisión infinita.

Cuando esto falla, tiene que decir **qué modelo y qué carril**. En producción,
quien lo lea a las tres de la mañana necesita saber qué fila mirar.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa

from nexus_api.billing.pricing import CREDIT_USD_PER_MILLION
from nexus_api.db.base import get_sessionmaker

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

#: La regla del dueño: nunca por debajo de un 50 % sobre el precio de proveedor,
#: en CADA carril y CADA modelo, nunca en promedio.
FLOOR = Decimal("1.50")
#: Lo que la spec fija. El suelo es lo que no se puede cruzar; el objetivo es lo
#: que se cobra. Son dos números distintos a propósito.
TARGET = Decimal("2.2")

_LANES = (
    ("entrada", "quota_weight_input", "price_input_per_mtok"),
    ("caché", "quota_weight_cache_read", "price_cache_read_per_mtok"),
    ("salida", "quota_weight_output", "price_output_per_mtok"),
)

_SQL = sa.text(
    "SELECT model_id, quota_weight_input, quota_weight_cache_read, quota_weight_output,"
    "       price_input_per_mtok, price_cache_read_per_mtok, price_output_per_mtok"
    "  FROM model_profiles"
    " WHERE quota_weight_input IS NOT NULL"
)


async def _servable_rows() -> list[dict]:
    async with get_sessionmaker()() as s:
        return [dict(r) for r in (await s.execute(_SQL)).mappings().all()]


async def test_the_catalog_actually_has_weighted_models() -> None:
    """Guarda contra el verde por vacío.

    Sin esto, un catálogo sin sembrar haría pasar todos los casos de abajo por
    no tener nada que recorrer, y el suelo quedaría «comprobado» sin comprobar
    nada. Es el modo de fallo más barato de escribir y el más caro de descubrir.
    """
    rows = await _servable_rows()
    assert rows, "ningún modelo tiene pesos por carril: los casos del suelo no miran nada"


async def test_no_lane_of_any_model_is_sold_below_the_floor() -> None:
    """R2.1, R2.2, R2.3 — por carril y por modelo, sobre el valor almacenado."""
    rows = await _servable_rows()
    assert rows

    offenders: list[str] = []
    for row in rows:
        for lane, weight_col, price_col in _LANES:
            price, weight = row[price_col], row[weight_col]
            if price is None:
                offenders.append(f"{row['model_id']} · {lane}: tiene peso y no tiene tarifa")
                continue
            multiplier = Decimal(weight) * CREDIT_USD_PER_MILLION / Decimal(price)
            if multiplier < FLOOR:
                offenders.append(
                    f"{row['model_id']} · carril {lane}: {multiplier:.4f}x "
                    f"(suelo {FLOOR}x) — peso {weight}, tarifa {price} USD/Mtok"
                )
    assert not offenders, "carriles por debajo del suelo:\n  " + "\n  ".join(offenders)


async def test_every_lane_hits_the_target_within_the_rounding_of_the_column() -> None:
    """R2.4 — no basta pasar el suelo: el objetivo se alcanza de verdad.

    Es la diferencia entre «no perdemos dinero» y «cobramos lo que decidimos
    cobrar». Con la escala de las tarifas, el carril más barato del catálogo
    (0,0044) cabe exacto; la tolerancia cubre el error de redondeo residual.
    """
    rows = await _servable_rows()
    assert rows

    drift: list[str] = []
    for row in rows:
        for lane, weight_col, price_col in _LANES:
            price = row[price_col]
            if price is None:
                continue
            multiplier = Decimal(row[weight_col]) * CREDIT_USD_PER_MILLION / Decimal(price)
            if abs(multiplier - TARGET) > Decimal("0.01"):
                drift.append(f"{row['model_id']} · {lane}: {multiplier:.4f}x (objetivo {TARGET}x)")
    assert not drift, "carriles fuera del objetivo:\n  " + "\n  ".join(drift)
