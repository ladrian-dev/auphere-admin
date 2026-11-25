"""La puerta de la membresía — spec 077, requisito 9.

Un cliente con membresía exigida no envía nada mientras no esté activa: la API
responde 402 y el despachador marca fallido lo que estuviera en cola. Un cliente
sin membresía no pasa por aquí (requisito 6.7).

Este módulo **no importa nada de** ``nexus_api.billing`` ni llama a Stripe: lo
usan el camino de envío y el despachador, y la puerta lee solo lo guardado
(requisito 9.5, ``tests/unit/test_billing_boundary.py``).

Se llama dentro de una sesión con el contexto del cliente ya puesto: la RLS
decide qué fila se ve (garantía 1). Sin contexto no se ve ninguna y no corta.
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models.service_membership import (
    PAYER_PARTNER_WALLET,
    STATUS_ACTIVE,
    ServiceMembership,
)

#: Lo que devuelve la API y lo que queda en ``messages.failure_code``.
MEMBERSHIP_INACTIVE = "membership_inactive"


def is_active(row: ServiceMembership, *, now: datetime | None = None) -> bool:
    """Activa = estado ``active`` y, si la paga el partner de su saldo, con el
    periodo pagado sin vencer. La de Stripe se fía del estado: Stripe la pasa a
    ``past_due`` al primer cobro fallido y el aviso o la relectura lo copian."""
    if row.status != STATUS_ACTIVE:
        return False
    if row.payer == PAYER_PARTNER_WALLET:
        end = row.current_period_end
        return end is not None and end > (now or datetime.now(UTC))
    return True


async def live_membership(session: AsyncSession, *, lock: bool = False) -> ServiceMembership | None:
    """La membresía viva del cliente del contexto, o ``None``.

    ``lock`` la bloquea hasta el final de la transacción: lo usa quien decide
    qué periodo se cobra, para que dos cobros a la vez lean el mismo.
    """
    query = sa.select(ServiceMembership).where(ServiceMembership.archived_at.is_(None)).limit(1)
    if lock:
        query = query.with_for_update()
    row: ServiceMembership | None = await session.scalar(query)
    return row


async def blocks_sending(session: AsyncSession, *, now: datetime | None = None) -> bool:
    """``True`` si el cliente del contexto tiene membresía y no está activa."""
    row = await live_membership(session)
    return row is not None and not is_active(row, now=now)


async def require_active_membership(session: AsyncSession) -> None:
    """402 si la membresía del cliente no está activa (requisito 9.1)."""
    if await blocks_sending(session):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"{MEMBERSHIP_INACTIVE}: this client's monthly membership is not active; "
                "nothing was queued"
            ),
        )
