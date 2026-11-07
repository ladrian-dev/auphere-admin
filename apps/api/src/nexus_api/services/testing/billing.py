"""Quién paga una pasada de pruebas — spec 047, requisito 68 (Luis, 2026-11-05).

- La primera pasada de **todas** las pruebas de un agente la paga Auphere, en
  «Construcción y pruebas». Es la única que corre sola, al guardar.
- Otra pasada entera se pide a propósito y la paga la bolsa del cliente, sabiéndolo antes.
- Repetir una prueba o las que no pasan sigue en la partida: así se arregla un agente, y
  cuesta céntimos. La partida tiene su tope.
- Un cliente con consumo ilimitado, o un partner que no cobra de las bolsas, no tiene de
  dónde cobrarla: sigue en la partida.

El dinero va en cien milésimas de la moneda (``{amount_micros, currency}``), como todo
el de la consola. La estimación (``estimate_for_agent``) sale en millonésimas de dólar:
aquí se convierte, y la consola nunca compara unidades.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Final, Literal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import Agent, Partner
from nexus_api.db.models.agent_spec import AgentTestResult, AgentTestRun
from nexus_api.services.wallet import fx

Payer = Literal["auphere", "client_bag"]
#: El valor de ``agent_test_runs.paid_by`` de cada uno. «partner» es, desde antes de esto,
#: lo que entra en la partida del partner, y el nombre se queda.
PAID_BY: Final[dict[Payer, str]] = {"auphere": "partner", "client_bag": "client_bag"}
#: Lo que tiene que quedar en la bolsa para empezar: la estimación es una estimación.
BAG_MARGIN: Final = Decimal("1.5")
#: Por debajo de lo que cuestan estas pruebas, las que faltan no empiezan (68.6).
BAG_KEEPS_TESTS: Final = 2
MICRO_USD_PER_UNIT: Final = 10


@dataclass(frozen=True)
class Money:
    amount_micros: int
    currency: str

    def out(self) -> dict[str, int | str]:
        return {"amount_micros": self.amount_micros, "currency": self.currency}


@dataclass(frozen=True)
class RunPrice:
    payer: Payer
    #: Lo estimado, en la moneda de quien paga. ``None`` si falta el precio de un modelo.
    charge: Money | None
    #: Lo que queda en la bolsa o en la partida. ``None`` si el partner no tiene partida.
    left: Money | None
    fits: bool

    def out(self) -> dict[str, object]:
        return {
            "payer": self.payer,
            "charge": self.charge.out() if self.charge is not None else None,
            "left": self.left.out() if self.left is not None else None,
            "fits": self.fits,
        }


async def first_pass_spent(session: AsyncSession, agent_id: uuid.UUID) -> bool:
    """¿Terminó ya una pasada de todas las pruebas de este agente, con algo que diga algo
    del agente? Una que se paró, o en la que ningún modelo respondió, queda ``failed``; y una
    solo de «No sé» no ha dicho nada (68.1). El tope de la partida limita lo que se repita.
    Las de antes de un cambio que hizo Auphere por su cuenta ya no cuentan (68.14)."""
    return bool(
        await session.scalar(
            sa.select(
                sa.exists().where(
                    AgentTestRun.tenant_id == require_current_tenant(),
                    AgentTestRun.agent_id == agent_id,
                    AgentTestRun.scope == "all",
                    AgentTestRun.status == "done",
                    # Una comprobación de calidad corre con otra política de modelo.
                    AgentTestRun.reason != "certification",
                    AgentTestResult.tenant_id == AgentTestRun.tenant_id,
                    AgentTestResult.run_id == AgentTestRun.id,
                    AgentTestResult.passed.is_not(None),
                    Agent.tenant_id == AgentTestRun.tenant_id,
                    Agent.id == AgentTestRun.agent_id,
                    sa.or_(
                        Agent.tests_pass_returned_at.is_(None),
                        AgentTestRun.created_at > Agent.tests_pass_returned_at,
                    ),
                )
            )
        )
    )


async def return_the_pass(session: AsyncSession, agent_id: uuid.UUID) -> None:
    """Auphere cambió este agente por su cuenta: sus pruebas dejan de valer por algo que el
    cliente no pidió, así que volver a pasarlas no se le cobra (68.14)."""
    await session.execute(
        sa.update(Agent)
        .where(Agent.tenant_id == require_current_tenant(), Agent.id == agent_id)
        .values(tests_pass_returned_at=sa.func.now())
    )


async def _on_console_v2(session: AsyncSession, partner_id: uuid.UUID | None) -> bool:
    if partner_id is None:
        return False
    enabled = await session.scalar(
        sa.select(Partner.console_v2_enabled_at).where(Partner.id == partner_id)
    )
    return enabled is not None


async def saves_without_testing(
    session: AsyncSession, agent_id: uuid.UUID, partner_id: uuid.UUID | None
) -> bool:
    """«Guardar» ya no pasa las pruebas: el agente gastó su pasada. Los partners de antes
    de la consola nueva, sin esta partida, siguen como estaban (historia 13, D38)."""
    return await _on_console_v2(session, partner_id) and await first_pass_spent(session, agent_id)


async def _bag_applies(partner_id: uuid.UUID, tenant_id: uuid.UUID) -> bool:
    from nexus_api.metering.wallet import is_unlimited
    from nexus_api.services.wallet.turns import bags_on

    return await bags_on(partner_id) and not await is_unlimited(tenant_id)


async def next_full_pass(
    session: AsyncSession, *, agent_id: uuid.UUID, partner_id: uuid.UUID, tenant_id: uuid.UUID
) -> Payer:
    """Quién pagaría una pasada entera si se pidiera ahora."""
    if not await first_pass_spent(session, agent_id):
        return "auphere"
    return "client_bag" if await _bag_applies(partner_id, tenant_id) else "auphere"


def _convert(micro_usd: int, rate: Decimal) -> int:
    return fx.convert(micro_usd // MICRO_USD_PER_UNIT, rate)


async def _rate(session: AsyncSession, currency: str) -> Decimal:
    try:
        rate, _date = await fx.rate_on(session, datetime.now(UTC).date(), "USD", currency)
    except fx.FxUnavailable:
        # Sin cambio publicado no se inventa uno: se lee 1:1, como en Consumo.
        return Decimal(1)
    return rate


async def price_run(
    session: AsyncSession,
    *,
    payer: Payer,
    partner_id: uuid.UUID,
    tenant_id: uuid.UUID,
    agent_id: uuid.UUID,
    tests: int,
) -> RunPrice:
    """Cuánto costaría y cuánto queda, en la moneda de quien paga."""
    from nexus_api.services.testing.estimate import estimate_for_agent
    from nexus_api.services.wallet import bags, build_budget
    from nexus_api.services.wallet.usage_lines import account_currency

    estimate = (await estimate_for_agent(session, agent_id, tests=tests)).amount_micros
    if payer == "client_bag":
        balance = await bags.balance_left(partner_id, tenant_id)
        currency = balance[1] if balance else await bags.currency_of(partner_id, tenant_id)
        left = balance[0] if balance else 0
        charge = (
            _convert(estimate, await _rate(session, currency)) if estimate is not None else None
        )
        # Sin precio no se cobra a ciegas (68.5).
        fits = charge is not None and left >= charge * BAG_MARGIN
        return RunPrice(
            payer=payer,
            charge=Money(charge, currency) if charge is not None else None,
            left=Money(left, currency),
            fits=fits,
        )
    currency = await account_currency(partner_id)
    charge = _convert(estimate, await _rate(session, currency)) if estimate is not None else None
    room = await build_budget.read_for_partner(partner_id)
    return RunPrice(
        payer=payer,
        charge=Money(charge, currency) if charge is not None else None,
        left=Money(room.remaining_micros, currency) if room is not None else None,
        # Si no se puede estimar, o no hay partida, arranca y es ella quien dice qué pasa.
        fits=room is None or charge is None or charge <= room.remaining_micros,
    )


async def bag_keeps_room(
    session: AsyncSession, *, partner_id: uuid.UUID, tenant_id: uuid.UUID, agent_id: uuid.UUID
) -> bool:
    """¿Puede empezar otra prueba a cargo de la bolsa? Con lo que cuestan
    :data:`BAG_KEEPS_TESTS`, una prueba no deja sin saldo a un agente que atiende (68.6)."""
    from nexus_api.services.testing.estimate import estimate_for_agent
    from nexus_api.services.wallet import bags

    balance = await bags.balance_left(partner_id, tenant_id)
    if balance is None:
        return False
    estimate = (await estimate_for_agent(session, agent_id, tests=BAG_KEEPS_TESTS)).amount_micros
    if estimate is None:
        return True
    left, currency = balance
    return left > _convert(estimate, await _rate(session, currency))


__all__ = [
    "BAG_KEEPS_TESTS",
    "BAG_MARGIN",
    "PAID_BY",
    "Money",
    "Payer",
    "RunPrice",
    "bag_keeps_room",
    "first_pass_spent",
    "next_full_pass",
    "price_run",
    "saves_without_testing",
]
