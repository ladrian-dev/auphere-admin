"""Valoración del consumo contra ``model_profiles`` (WP-19).

Es la mitad que le faltaba a B3: WP-17 cuenta tokens, WP-18 los persiste y
esto los convierte en dinero. Hasta ahora ``usage_records.cost_usd`` era
NULL para todo (ver 0071) y no se podía mirar el margen.

Por qué el catálogo se lee de la base y no del código:

- Cuando un proveedor cambia tarifas, se actualiza una fila y el consumo
  de la hora siguiente ya se valora bien. Con el precio en el código, cada
  cambio de tarifa es un despliegue — y mientras tanto se factura mal.
- El catálogo cabe entero en memoria (decenas de filas) y cambia casi
  nunca, así que se cachea con TTL en lugar de consultarlo por fila. El
  TTL es el retraso máximo en adoptar una tarifa nueva; ``invalidate()``
  lo fuerza a cero cuando hace falta.

Y por qué un modelo desconocido NO se valora a cero: un cero dice "esto no
costó nada" y se suma silenciosamente en cualquier panel de margen. NULL
dice "medido, sin precio", que es la verdad, y ``WHERE cost_usd IS NULL``
lo encuentra después. Lo mismo para un medidor sin tarifa cargada.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
import structlog
from nexus_api.db.base import get_sessionmaker

log = structlog.get_logger(__name__)

# Un catálogo servido hasta 5 min viejo. Es el retraso máximo en adoptar
# una tarifa nueva y el coste de equivocarse es proporcional a 5 minutos
# de consumo, no a un despliegue.
CATALOG_TTL_S = 300.0

_MTOK = Decimal(1_000_000)
# 8 decimales = la escala de ``usage_records.cost_usd``. Se cuantiza aquí
# para que el número que se afirma en los tests sea el que entra en la
# base, y no uno que Postgres redondea por su cuenta.
_COST_SCALE = Decimal("0.00000001")


@dataclass(frozen=True)
class ModelPrice:
    """Tarifas de un modelo. Cualquier campo puede ser None: modelo en
    catálogo pero sin tarifa cargada."""

    model_id: str
    input_per_mtok: Decimal | None = None
    output_per_mtok: Decimal | None = None
    cache_read_per_mtok: Decimal | None = None
    cache_write_per_mtok: Decimal | None = None
    per_minute: Decimal | None = None
    cache_min_tokens: int | None = None


# Medidor → (atributo de tarifa, unidad). ``mtok`` divide entre un millón;
# ``unit`` multiplica directo (la voz se factura por minuto).
_METER_PRICING: dict[str, tuple[str, str]] = {
    "llm.input_tokens": ("input_per_mtok", "mtok"),
    "llm.output_tokens": ("output_per_mtok", "mtok"),
    "llm.cache_read": ("cache_read_per_mtok", "mtok"),
    "llm.cache_write": ("cache_write_per_mtok", "mtok"),
    "voice.minutes": ("per_minute", "unit"),
}

_CATALOG_SQL = sa.text(
    """
    SELECT model_id,
           price_input_per_mtok,
           price_output_per_mtok,
           price_cache_read_per_mtok,
           price_cache_write_per_mtok,
           price_per_minute,
           cache_min_tokens
      FROM model_profiles
    """
)

_cache: dict[str, ModelPrice] | None = None
_cached_at: float = 0.0
_lock = asyncio.Lock()


async def load_catalog() -> dict[str, ModelPrice]:
    """Lee ``model_profiles`` entero. Sin ámbito de tenant a propósito:
    es catálogo de plataforma y no lleva RLS."""
    sm = get_sessionmaker()
    async with sm() as session:
        rows = (await session.execute(_CATALOG_SQL)).all()

    catalog: dict[str, ModelPrice] = {}
    for model_id, inp, out, cread, cwrite, per_min, cache_min in rows:
        catalog[model_id] = ModelPrice(
            model_id=model_id,
            input_per_mtok=inp,
            output_per_mtok=out,
            cache_read_per_mtok=cread,
            cache_write_per_mtok=cwrite,
            per_minute=per_min,
            cache_min_tokens=cache_min,
        )
    return catalog


async def get_catalog(*, force: bool = False) -> dict[str, ModelPrice]:
    global _cache, _cached_at
    now = time.monotonic()
    if not force and _cache is not None and (now - _cached_at) < CATALOG_TTL_S:
        return _cache
    async with _lock:
        # Otro corutina pudo refrescarlo mientras esperábamos el lock.
        if not force and _cache is not None and (time.monotonic() - _cached_at) < CATALOG_TTL_S:
            return _cache
        try:
            _cache = await load_catalog()
            _cached_at = time.monotonic()
            log.info("pricing.catalog_loaded", models=len(_cache))
        except Exception as exc:
            # Un catálogo viejo vale infinitamente más que ninguno: seguir
            # valorando con tarifas de hace 6 minutos es mejor que dejar de
            # valorar. Sin catálogo previo, se devuelve vacío y las filas
            # entran sin precio — recuperables con el backfill.
            log.error("pricing.catalog_load_failed", error=str(exc), stale=_cache is not None)
            if _cache is None:
                return {}
        return _cache


def invalidate() -> None:
    """Fuerza la relectura en la siguiente valoración."""
    global _cache, _cached_at
    _cache = None
    _cached_at = 0.0


async def cheapest_model() -> str | None:
    """El modelo con la entrada más barata del catálogo (WP-20).

    Se ordena por precio de ENTRADA y no por el de salida porque en estos
    agentes el prompt domina el turno con diferencia: el sistema, el
    historial y las envolturas de herramienta se reenvían enteros en cada
    llamada, mientras que la respuesta son un par de frases.

    Devuelve None si no hay ningún modelo con precio — degradar a un
    modelo del que no sabemos el coste no degradaría nada.
    """
    catalog = await get_catalog()
    priced = [p for p in catalog.values() if p.input_per_mtok is not None]
    if not priced:
        return None
    return min(priced, key=lambda p: (p.input_per_mtok, p.model_id)).model_id


def price_row(row: dict[str, Any], catalog: dict[str, ModelPrice]) -> Decimal | None:
    """Coste en USD de una fila de consumo, o None si no se puede valorar.

    None cuando: la fila no dice de qué modelo salió, el modelo no está en
    catálogo, el medidor no tiene tarifa asociada, o el modelo está en
    catálogo pero sin esa tarifa cargada. En los cuatro casos la fila entra
    con ``cost_usd NULL`` y se puede reprecificar después; valorarla a cero
    la haría indistinguible de un evento que de verdad es gratis.
    """
    model = row.get("model")
    if not model:
        return None
    price = catalog.get(model)
    if price is None:
        return None

    pricing = _METER_PRICING.get(row["meter"])
    if pricing is None:
        return None
    attr, unit = pricing

    rate: Decimal | None = getattr(price, attr)
    if rate is None:
        return None

    quantity = row["quantity"]
    if not isinstance(quantity, Decimal):
        quantity = Decimal(str(quantity))

    cost = quantity * rate
    if unit == "mtok":
        cost = cost / _MTOK
    return cost.quantize(_COST_SCALE)
