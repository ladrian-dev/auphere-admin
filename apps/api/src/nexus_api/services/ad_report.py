"""El informe de anuncios de un cliente — spec 076, requisito 3.

Por anuncio (``source_id`` del clic):

- **conversaciones**: las conversaciones distintas con un clic de ese anuncio en
  el periodo;
- **reservas**: las del agente (``origin = 'agent'``), no canceladas, creadas en
  el periodo y atribuidas al último clic de su contacto **en el número de su
  conversación** anterior a la reserva, aunque el clic sea de antes del periodo.
  Es la misma regla que al encolar un evento para Meta (research D7);
- **importe**: la suma de esas reservas por moneda. Sin precio, cuentan como
  reserva y no suman.

La sesión llega con el tenant del cliente (RLS): el informe no ve otro negocio.
No devuelve nombres ni teléfonos: solo el anuncio, que es texto del anunciante.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

PERIODS: Final = (7, 30, 90)

_CONVERSATIONS = sa.text(
    """
    SELECT source_id, count(DISTINCT conversation_id) AS n
    FROM customer_ad_referrals
    WHERE clicked_at >= :since
    GROUP BY source_id
    """
)

_BOOKINGS = sa.text(
    """
    SELECT ref.source_id, r.price_minor, r.currency
    FROM reservations r
    JOIN conversations c ON c.id = r.conversation_id
    JOIN LATERAL (
        SELECT x.source_id
        FROM customer_ad_referrals x
        WHERE x.customer_id = c.customer_id
          AND x.channel_id = c.channel_id
          AND x.clicked_at <= r.created_at
        ORDER BY x.clicked_at DESC
        LIMIT 1
    ) ref ON true
    WHERE r.origin = 'agent'
      AND r.status <> 'cancelled'
      AND r.created_at >= :since
    """
)

_ADS = sa.text(
    """
    SELECT DISTINCT ON (source_id) source_id, source_type, headline, source_url
    FROM customer_ad_referrals
    WHERE source_id = ANY(CAST(:ids AS varchar[])) OR (source_id IS NULL AND :with_null)
    ORDER BY source_id, clicked_at DESC
    """
)


@dataclass
class AdRow:
    ad_id: str | None
    ad_kind: str = "ad"
    ad_headline: str | None = None
    ad_url: str | None = None
    conversations: int = 0
    bookings: int = 0
    amounts: dict[str, int] = field(default_factory=dict)


async def ads_report(
    session: AsyncSession, *, days: int, now: datetime | None = None
) -> list[AdRow]:
    """Las filas del informe, ordenadas por reservas y después por conversaciones."""
    since = (now or datetime.now(UTC)) - timedelta(days=days)
    rows: dict[str | None, AdRow] = {}

    def row(ad_id: str | None) -> AdRow:
        if ad_id not in rows:
            rows[ad_id] = AdRow(ad_id=ad_id)
        return rows[ad_id]

    for ad_id, n in (await session.execute(_CONVERSATIONS, {"since": since})).all():
        row(ad_id).conversations = int(n)

    amounts: dict[str | None, dict[str, int]] = defaultdict(dict)
    for ad_id, price, currency in (await session.execute(_BOOKINGS, {"since": since})).all():
        row(ad_id).bookings += 1
        if price is not None and currency:
            amounts[ad_id][currency] = amounts[ad_id].get(currency, 0) + int(price)
    for ad_id, by_currency in amounts.items():
        rows[ad_id].amounts = by_currency

    if rows:
        ids = [a for a in rows if a is not None]
        found = await session.execute(_ADS, {"ids": ids, "with_null": None in rows})
        for ad_id, kind, headline, url in found.all():
            if ad_id in rows:
                rows[ad_id].ad_kind = kind
                rows[ad_id].ad_headline = headline
                rows[ad_id].ad_url = url

    return sorted(rows.values(), key=lambda r: (-r.bookings, -r.conversations, r.ad_id or ""))
