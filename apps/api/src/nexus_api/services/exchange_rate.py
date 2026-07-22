"""Exchange-rate service — CLP→USD via the Chilean Central Bank's
"dólar observado", read from the free public API ``mindicador.cl``.

Used by the monthly partner receipt: sales are captured in the store's own
currency (CLP) and converted to USD on the day the receipt is issued. We
take the most recently published observed dollar (``serie[0]``) rather than a
specific calendar date, so issuing on a weekend/holiday — when no rate is
published — still resolves to the latest business-day rate.

A tiny in-process cache keyed by (source, YYYY-MM-DD) means the receipt run
hits the network once per day at most.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)

_MINDICADOR_DOLAR_URL = "https://mindicador.cl/api/dolar"
_TIMEOUT_S = 20.0

# (source, iso-date) -> CLP per USD. Cleared implicitly by date change.
_cache: dict[tuple[str, str], Decimal] = {}


class ExchangeRateUnavailable(RuntimeError):
    """The observed-dollar rate could not be fetched or parsed."""


def _parse_observed_dollar(payload: dict[str, Any]) -> Decimal:
    """Pull the most recent observed-dollar value (CLP per USD)."""
    serie = payload.get("serie")
    if not isinstance(serie, list) or not serie:
        raise ExchangeRateUnavailable("mindicador response has no 'serie'")
    first = serie[0]
    valor = first.get("valor") if isinstance(first, dict) else None
    if valor is None:
        raise ExchangeRateUnavailable("mindicador 'serie[0]' has no 'valor'")
    rate = Decimal(str(valor))
    if rate <= 0:
        raise ExchangeRateUnavailable(f"non-positive rate: {rate}")
    return rate


async def get_clp_per_usd(*, on: date | None = None) -> Decimal:
    """Return CLP per 1 USD (the observed dollar). Cached per calendar day."""
    day = (on or date.today()).isoformat()
    key = ("mindicador_dolar", day)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            resp = await client.get(_MINDICADOR_DOLAR_URL)
            resp.raise_for_status()
            rate = _parse_observed_dollar(resp.json())
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise ExchangeRateUnavailable(f"mindicador fetch failed: {exc}") from exc
    _cache[key] = rate
    log.info("exchange_rate.fetched", source="mindicador_dolar", clp_per_usd=str(rate))
    return rate


def clp_to_usd(clp: Decimal, *, clp_per_usd: Decimal) -> Decimal:
    """Convert a CLP amount to USD at the given rate, rounded to cents."""
    if clp_per_usd <= 0:
        raise ExchangeRateUnavailable(f"non-positive rate: {clp_per_usd}")
    return (clp / clp_per_usd).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
