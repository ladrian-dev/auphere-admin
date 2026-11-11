"""La política de venta por modelo — spec 059 (requisitos 3.1 a 3.11; research D7 y D8).

El partner paga **unidades de cuota** a ``CREDIT_USD_PER_MILLION`` (10 US$) el
millón, y un token de cada carril cuesta ``peso`` unidades (``metering.quota``).
Así que, por carril:

- **venta por millón** = ``peso * 10``;
- **multiplicador** sobre el coste = ``venta / coste``.

Los pesos guardados son lo que se cobra: una decisión comercial, separada del coste
(spec 007). El **multiplicador objetivo** es el múltiplo del coste con el que se
**proponen** y se **comprueban**. Hasta la spec 059 era la constante 2,2; ahora es
el ajuste ``platform_settings.sale_multiplier`` (0231), que Auphere cambia desde el
panel. El **suelo** (``QUOTA_FLOOR_MULTIPLIER``, 1,5) no es un ajuste: ni un peso ni
el objetivo pueden quedar por debajo.

Si el ajuste no se puede leer, ``target_multiplier()`` devuelve None, nunca un número
inventado: el panel enseña los modelos sin propuesta (4.7).
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Final

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.base import get_sessionmaker
from nexus_api.metering.pricing_policy import LANES, QUOTA_FLOOR_MULTIPLIER

log = structlog.get_logger(__name__)

#: Lo que vale un millón de unidades de cuota: ``billing.pricing.CREDIT_USD_PER_MILLION``.
#: Copia y no import: ``metering`` es camino del turno y no puede depender del cobro
#: (``tests/unit/test_billing_boundary.py``). ``test_sale_policy`` fija que coincidan.
SELL_USD_PER_MILLION: Final = Decimal(10)
FLOOR: Final = QUOTA_FLOOR_MULTIPLIER
SETTING_KEY: Final = "sale_multiplier"
#: Como el catálogo del medidor: el retraso máximo en ver un cambio de otro proceso.
CACHE_TTL_S: Final = 300.0
#: La escala de ``model_profiles.quota_weight_*`` (``NUMERIC(12,6)``).
_WEIGHT_SCALE: Final = Decimal("0.000001")
#: Un peso a menos de esto de su propuesta está en el objetivo.
_TOLERANCE: Final = Decimal("0.000001")

_cache: tuple[float, Decimal | None] | None = None


class SalePolicyError(ValueError):
    """Lo que la política de venta no deja hacer, con su código."""

    def __init__(self, code: str, detail: str, *, lanes: list[str] | None = None) -> None:
        super().__init__(detail)
        self.code = code
        self.lanes = lanes or []


def invalidate() -> None:
    global _cache
    _cache = None


async def target_multiplier() -> Decimal | None:
    """El multiplicador objetivo, o None si no se puede leer."""
    global _cache
    if _cache is not None and time.monotonic() - _cache[0] < CACHE_TTL_S:
        return _cache[1]
    value: Decimal | None = None
    try:
        async with get_sessionmaker()() as session:
            raw = await session.scalar(
                sa.text("SELECT value FROM platform_settings WHERE key = :k"), {"k": SETTING_KEY}
            )
        if raw is not None:
            value = Decimal(str(raw if not isinstance(raw, str) else json.loads(raw)))
    except Exception as exc:
        log.warning("sale_policy.unreadable", error=type(exc).__name__)
        return None
    _cache = (time.monotonic(), value)
    return value


def check_target(value: Decimal) -> None:
    if value < FLOOR:
        raise SalePolicyError("below_floor", f"el objetivo no puede bajar de {FLOOR}")


async def store_target(session: AsyncSession, value: Decimal, *, actor: str) -> Decimal | None:
    """Guarda el objetivo en la transacción de ``session``. Devuelve el anterior."""
    check_target(value)
    before = await session.scalar(
        sa.text("SELECT value FROM platform_settings WHERE key = :k FOR UPDATE"),
        {"k": SETTING_KEY},
    )
    await session.execute(
        sa.text(
            "INSERT INTO platform_settings (key, value, updated_at, updated_by) "
            "VALUES (:k, CAST(:v AS jsonb), now(), :a) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, "
            "updated_at = now(), updated_by = EXCLUDED.updated_by"
        ),
        {"k": SETTING_KEY, "v": json.dumps(float(value)), "a": actor},
    )
    return None if before is None else Decimal(str(before))


# ── cálculos puros ─────────────────────────────────────────────────────────


def propose(costs: Mapping[str, Decimal | None], target: Decimal) -> dict[str, Decimal] | None:
    """Los pesos que corresponden a ``target`` sobre ``costs``, o None si algún
    carril no tiene coste (van los tres o ninguno)."""
    if any(costs.get(lane) is None for lane in LANES):
        return None
    return {
        lane: (target * Decimal(costs[lane]) / SELL_USD_PER_MILLION).quantize(  # type: ignore[arg-type]
            _WEIGHT_SCALE, rounding=ROUND_HALF_UP
        )
        for lane in LANES
    }


def lane_multiplier(weight: Decimal | None, cost: Decimal | None) -> Decimal | None:
    if weight is None or cost is None or cost <= 0:
        return None
    return Decimal(weight) * SELL_USD_PER_MILLION / Decimal(cost)


def lanes_below_floor(
    weights: Mapping[str, Decimal | None], costs: Mapping[str, Decimal | None]
) -> list[str]:
    """Los carriles cuya venta queda por debajo del suelo, en el orden de ``LANES``."""
    out: list[str] = []
    for lane in LANES:
        multiplier = lane_multiplier(weights.get(lane), costs.get(lane))
        if multiplier is not None and multiplier < FLOOR:
            out.append(lane)
    return out


def _fmt(value: Decimal | None, places: str = "0.000001") -> str | None:
    return None if value is None else str(Decimal(value).quantize(Decimal(places)))


def sale_view(
    *,
    costs: Mapping[str, Decimal | None],
    weights: Mapping[str, Decimal | None],
    target: Decimal | None,
    per_minute: bool = False,
) -> dict[str, Any]:
    """El bloque ``sale`` de una fila de Modelos (``contracts/admin-api.md`` §1)."""
    lanes = {
        lane: {
            "cost": _fmt(costs.get(lane)),
            "weight": _fmt(weights.get(lane)),
            "sale": _fmt(
                None if weights.get(lane) is None else Decimal(weights[lane]) * SELL_USD_PER_MILLION  # type: ignore[arg-type]
            ),
            "multiplier": _fmt(lane_multiplier(weights.get(lane), costs.get(lane)), "0.01"),
        }
        for lane in LANES
    }
    proposed = None if target is None or per_minute else propose(costs, target)
    weighted = all(weights.get(lane) is not None for lane in LANES)
    has_cost = any(costs.get(lane) is not None for lane in LANES)
    if per_minute:
        state = "per_minute"
    elif not has_cost:
        state = "no_cost"
    elif not weighted:
        state = "unweighted"
    elif lanes_below_floor(weights, costs):
        state = "below_floor"
    elif target is None:
        state = "unknown"
    elif proposed is not None and any(
        abs(Decimal(weights[lane]) - proposed[lane]) > _TOLERANCE  # type: ignore[arg-type]
        for lane in LANES
    ):
        state = "drift"
    else:
        state = "on_target"
    return {
        "state": state,
        "lanes": lanes,
        "proposed": None if proposed is None else {k: _fmt(v) for k, v in proposed.items()},
    }


def policy_view(target: Decimal | None) -> dict[str, Any]:
    """El bloque ``sale_policy`` del listado (``contracts/admin-api.md`` §1 y §7)."""
    return {
        "multiplier": None if target is None else str(target),
        "floor": str(FLOOR),
        "sell_usd_per_million": str(SELL_USD_PER_MILLION),
    }


__all__ = [
    "FLOOR",
    "SELL_USD_PER_MILLION",
    "SalePolicyError",
    "check_target",
    "invalidate",
    "lane_multiplier",
    "lanes_below_floor",
    "policy_view",
    "propose",
    "sale_view",
    "store_target",
    "target_multiplier",
]
