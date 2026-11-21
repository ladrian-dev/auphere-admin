"""El mundo de «Lo que te necesita» (spec 071): el del dinero de la consola nueva y
las piezas para poner al partner en cada condición y leer sus avisos.

No es un test (empieza por ``_``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.db.models import ConsoleNotification, PartnerSubscription, PartnerWallet
from nexus_api.services.wallet import build_budget
from tests.integration.wallet._wallet_world import UNIT, MoneyWorld, money, money_world

__all__ = [
    "UNIT",
    "MoneyWorld",
    "Notice",
    "assign",
    "billing_state",
    "build_spent",
    "money",
    "money_world",
    "notice",
    "notice_state",
    "notices_of",
    "set_purchased",
]


async def assign(client: Any, world: MoneyWorld, ref: str, amount: int) -> None:
    resp = await client.post(
        f"/console/clients/{ref}/bag/assign",
        json={"amount": money(amount, "EUR" if ref.endswith("-es") else "USD")},
        headers=world.headers(),
    )
    assert resp.status_code == 200, resp.text


async def build_spent(db_session: AsyncSession, world: MoneyWorld, amount: int) -> list[str]:
    """Suma a la partida del mes (el tope por defecto es 50 unidades)."""
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        return await build_budget.record(db_session, world.partner_id, amount)


async def set_purchased(db_session: AsyncSession, world: MoneyWorld, amount: int) -> None:
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        await db_session.execute(
            sa.update(PartnerWallet)
            .where(PartnerWallet.partner_id == world.partner_id)
            .values(purchased_remaining=amount)
        )


async def billing_state(db_session: AsyncSession, partner_id: uuid.UUID, state: str) -> None:
    async with db_session.begin():
        await db_session.execute(
            sa.update(PartnerSubscription)
            .where(PartnerSubscription.partner_id == partner_id)
            .values(state=state)
        )


async def notice(
    db_session: AsyncSession,
    partner_id: uuid.UUID,
    kind: str,
    *,
    ref: str | None = None,
    severity: str = "warning",
    dedupe: bool = True,
    audience: str = "partner",
) -> uuid.UUID:
    """Un aviso pendiente, como lo deja su emisor."""
    row = ConsoleNotification(
        id=uuid.uuid4(),
        partner_id=partner_id,
        kind=kind,
        severity=severity,
        external_client_ref=ref,
        payload={},
        dedupe_key=f"{kind}:{ref}:{uuid.uuid4().hex}" if dedupe else None,
        audience=audience,
    )
    async with db_session.begin():
        db_session.add(row)
    return row.id


@dataclass(frozen=True)
class Notice:
    kind: str
    ref: str | None
    handled_at: datetime | None
    dedupe_key: str | None

    @property
    def resolved(self) -> bool:
        return self.handled_at is not None


async def notice_state(db_session: AsyncSession, notice_id: uuid.UUID) -> Notice:
    async with db_session.begin():
        row = (
            await db_session.execute(
                sa.select(
                    ConsoleNotification.kind,
                    ConsoleNotification.external_client_ref,
                    ConsoleNotification.handled_at,
                    ConsoleNotification.dedupe_key,
                ).where(ConsoleNotification.id == notice_id)
            )
        ).one()
    return Notice(*row)


async def notices_of(
    db_session: AsyncSession, partner_id: uuid.UUID, kind: str | None = None
) -> list[Notice]:
    stmt = sa.select(
        ConsoleNotification.kind,
        ConsoleNotification.external_client_ref,
        ConsoleNotification.handled_at,
        ConsoleNotification.dedupe_key,
    ).where(
        ConsoleNotification.partner_id == partner_id,
        ConsoleNotification.audience == "partner",
    )
    if kind is not None:
        stmt = stmt.where(ConsoleNotification.kind == kind)
    async with db_session.begin():
        rows = (await db_session.execute(stmt.order_by(ConsoleNotification.created_at))).all()
    return [Notice(*r) for r in rows]


def now() -> datetime:
    return datetime.now(UTC)
