"""«Construcción y pruebas» — spec 047, T158 (requisito 46.5; research D29).

Una partida mensual por partner, en dinero (nunca en tokens): el constructor, el
playground, las pruebas, las simulaciones y su juez, la lectura de webs, la
indexación, las sugerencias y las certificaciones que lanza el partner. La paga
Auphere hasta el tope (50 en la moneda de la cuenta por defecto,
``partners.build_budget_default_micros``), que Auphere ajusta por partner.

- Al 80 %, un aviso (``build.budget.warning``).
- Al 100 %, se paran el constructor, las pruebas y el playground (``402
  build_budget_exhausted``); la edición a mano sigue y la suite empezada termina.
- «Pedir ampliación»: una al día (``429 request_already_sent_today``).

Sustituye al tope de 2 M de tokens del playground (``qa_monthly_token_cap``) para
los partners con la consola nueva.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import BuildBudgetRequest, Partner, PartnerBuildBudget
from nexus_api.services.wallet.bags import WalletError, month_of

WARN_SHARE: Final = 0.80


@dataclass(frozen=True)
class BudgetState:
    cap_micros: int
    spent_micros: int
    state: str  # ok · warning · exhausted

    @property
    def remaining_micros(self) -> int:
        return max(0, self.cap_micros - self.spent_micros)


async def _row(session: AsyncSession, partner_id: uuid.UUID) -> PartnerBuildBudget:
    month = month_of()
    row = await session.get(PartnerBuildBudget, (partner_id, month))
    if row is None:
        cap = await session.scalar(
            sa.select(Partner.build_budget_default_micros).where(Partner.id == partner_id)
        )
        await session.execute(
            insert(PartnerBuildBudget)
            .values(partner_id=partner_id, month=month, cap_micros=int(cap or 5_000_000))
            .on_conflict_do_nothing()
        )
        row = await session.get(PartnerBuildBudget, (partner_id, month))
    assert row is not None
    return row


def _state(row: PartnerBuildBudget) -> BudgetState:
    if row.spent_micros >= row.cap_micros:
        state = "exhausted"
    elif row.spent_micros >= WARN_SHARE * row.cap_micros:
        state = "warning"
    else:
        state = "ok"
    return BudgetState(cap_micros=row.cap_micros, spent_micros=row.spent_micros, state=state)


async def read(session: AsyncSession, partner_id: uuid.UUID) -> BudgetState:
    """Dentro de una sesión con el ``app.partner_id`` del partner."""
    return _state(await _row(session, partner_id))


async def require_room(session: AsyncSession, partner_id: uuid.UUID) -> None:
    """Antes de construir, probar o abrir el playground: con la partida agotada,
    ``402 build_budget_exhausted``."""
    if (await read(session, partner_id)).state == "exhausted":
        raise WalletError("build_budget_exhausted", 402)


async def require_room_for_partner(partner_id: uuid.UUID) -> None:
    """El freno de la partida para los partners con la consola nueva (los de hoy
    siguen con el tope de tokens del playground). En su propia sesión: la partida
    tiene RLS por partner."""
    from nexus_api.core.partner_context import apply_partner_to_session
    from nexus_api.db.base import get_sessionmaker

    async with get_sessionmaker()() as session, session.begin():
        v2 = await session.scalar(
            sa.select(Partner.console_v2_enabled_at).where(Partner.id == partner_id)
        )
        if v2 is None:
            return
        await apply_partner_to_session(session, partner_id)
        await require_room(session, partner_id)


async def record(session: AsyncSession, partner_id: uuid.UUID, amount: int) -> list[str]:
    """Suma ``amount`` a la partida del mes. Devuelve los avisos que tocan."""
    if amount <= 0:
        return []
    current = await _row(session, partner_id)
    row = await session.get(PartnerBuildBudget, (partner_id, current.month), with_for_update=True)
    assert row is not None
    row.spent_micros += amount
    now = datetime.now(UTC)
    out: list[str] = []
    if row.spent_micros >= row.cap_micros and row.exhausted_at is None:
        row.exhausted_at = now
        out.append("build.budget.exhausted")
    elif row.spent_micros >= WARN_SHARE * row.cap_micros and row.warned_at is None:
        row.warned_at = now
        out.append("build.budget.warning")
    await session.flush()
    return out


async def request_more(session: AsyncSession, partner_id: uuid.UUID, actor: str) -> None:
    """«Pedir ampliación»: una al día por partner."""
    try:
        async with session.begin_nested():
            session.add(BuildBudgetRequest(partner_id=partner_id, requested_by=actor))
            await session.flush()
    except IntegrityError:
        raise WalletError("request_already_sent_today", 429) from None


__all__ = [
    "BudgetState",
    "read",
    "record",
    "request_more",
    "require_room",
    "require_room_for_partner",
]
