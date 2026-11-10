"""El cambio de referencia del BCE — spec 047, T156 (requisito 43.2; research D26).

Un cron del worker descarga cada día hábil el cambio de referencia del BCE a
``fx_rates`` (base EUR). Un día sin publicación usa el último publicado antes. Cada
traspaso guarda el cambio y su fecha: la consola los cita («BCE {fecha}»).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Final

import httpx
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import FxRate

ECB_DAILY_URL: Final = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
BASE: Final = "EUR"
_NS: Final = {"e": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"}


class FxUnavailable(Exception):
    """No hay cambio publicado para ese par en o antes de esa fecha."""


async def rate_on(
    session: AsyncSession, day: date, from_currency: str, to_currency: str
) -> tuple[Decimal, date | None]:
    """Cuántas unidades de ``to_currency`` vale una de ``from_currency`` el día
    ``day`` (o el último día publicado antes), y la fecha de ese cambio."""
    if from_currency == to_currency:
        return Decimal(1), None
    other = to_currency if from_currency == BASE else from_currency
    if BASE not in {from_currency, to_currency}:
        raise FxUnavailable(f"{from_currency}->{to_currency}: solo EUR y USD")
    row = (
        await session.execute(
            sa.select(FxRate.rate, FxRate.date)
            .where(FxRate.base == BASE, FxRate.quote == other, FxRate.date <= day)
            .order_by(FxRate.date.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        raise FxUnavailable(f"sin cambio EUR/{other} hasta {day}")
    rate = Decimal(row.rate)
    return (rate if from_currency == BASE else Decimal(1) / rate), row.date


def convert(amount: int, rate: Decimal) -> int:
    """Un importe en unidades (cien milésimas) al otro lado del cambio."""
    return int((Decimal(amount) * rate).to_integral_value(rounding=ROUND_HALF_EVEN))


def parse_ecb(xml: str) -> tuple[date, dict[str, Decimal]]:
    root = ET.fromstring(xml)
    cube = root.find(".//e:Cube/e:Cube[@time]", _NS)
    if cube is None:
        raise FxUnavailable("el XML del BCE no trae fecha")
    day = date.fromisoformat(cube.attrib["time"])
    rates = {
        c.attrib["currency"]: Decimal(c.attrib["rate"])
        for c in cube.findall("e:Cube[@currency]", _NS)
    }
    return day, rates


async def fetch_ecb(client: httpx.AsyncClient | None = None) -> tuple[date, dict[str, Decimal]]:
    owned = client is None
    client = client or httpx.AsyncClient(timeout=20.0)
    try:
        resp = await client.get(ECB_DAILY_URL)
        resp.raise_for_status()
        return parse_ecb(resp.text)
    finally:
        if owned:
            await client.aclose()


async def store(session: AsyncSession, day: date, rates: dict[str, Decimal]) -> int:
    """Guarda (o corrige) el cambio publicado de ese día. Solo USD hoy (D26)."""
    stored = 0
    for quote in ("USD",):
        if quote not in rates:
            continue
        await session.execute(
            insert(FxRate)
            .values(date=day, base=BASE, quote=quote, rate=rates[quote])
            .on_conflict_do_update(
                index_elements=["date", "base", "quote"],
                set_={"rate": rates[quote], "fetched_at": sa.func.now()},
            )
        )
        stored += 1
    return stored


__all__ = [
    "BASE",
    "ECB_DAILY_URL",
    "FxUnavailable",
    "convert",
    "fetch_ecb",
    "parse_ecb",
    "rate_on",
    "store",
]
