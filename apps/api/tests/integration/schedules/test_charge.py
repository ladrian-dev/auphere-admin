"""Lo que cuesta una rutina, cobrado a la bolsa — spec 082, T019 (requisitos
9.1, 9.2 y 9.4).

Tres cosas, y las tres se notan en una factura si fallan:

1. el asiento es ``debit_schedule``, no ``debit_turn``, que es lo que permite
   decirle al cliente cuánto se le fue en rutinas y cuánto atendiendo;
2. la misma ejecución no se cobra dos veces, aunque el reparto se reintente;
3. no suma al tope del agente, porque ese tope habla de atender.
"""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.db.models import ClientWalletEntry
from nexus_api.services.wallet.schedules import ENTRY_KIND, charge_schedule

from ..wallet._wallet_world import UNIT, MoneyWorld, as_client, money, money_world

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _assign(client: Any, world: MoneyWorld, ref: str, amount: int, currency: str) -> Any:
    return await client.post(
        f"/console/clients/{ref}/bag/assign",
        json={"amount": money(amount, currency)},
        headers=world.headers(),
    )


async def _entries(db_session: Any, world: MoneyWorld, tenant_id: Any) -> list[tuple[str, int]]:
    # El libro de la bolsa es del cliente: se lee con su contexto puesto
    # (garantía 1), igual que la bolsa.
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        await as_client(db_session, tenant_id)
        rows = (
            await db_session.execute(
                sa.select(ClientWalletEntry.kind, ClientWalletEntry.amount_micros)
                .where(ClientWalletEntry.tenant_id == tenant_id)
                .order_by(ClientWalletEntry.id)
            )
        ).all()
    return [(r[0], int(r[1])) for r in rows]


async def test_a_run_lands_on_its_own_entry(client: Any, db_session: Any) -> None:
    world = await money_world(db_session)
    await _assign(client, world, world.us.ref, UNIT, "USD")

    await charge_schedule(
        partner_id=world.partner_id,
        tenant_id=world.us.tenant_id,
        agent_id=None,
        amount_usd=2_000,
        usage_ref="schedule:run-1",
    )

    kinds = [k for k, _ in await _entries(db_session, world, world.us.tenant_id)]
    assert ENTRY_KIND in kinds
    assert "debit_turn" not in kinds


async def test_the_same_run_is_never_charged_twice(client: Any, db_session: Any) -> None:
    """El reparto se reintenta cuando una entrada no se acusa: el cobro tiene
    que ser idempotente por su referencia o la bolsa se vacía sola."""
    world = await money_world(db_session)
    await _assign(client, world, world.us.ref, UNIT, "USD")

    first = await charge_schedule(
        partner_id=world.partner_id,
        tenant_id=world.us.tenant_id,
        agent_id=None,
        amount_usd=2_000,
        usage_ref="schedule:run-1",
    )
    again = await charge_schedule(
        partner_id=world.partner_id,
        tenant_id=world.us.tenant_id,
        agent_id=None,
        amount_usd=2_000,
        usage_ref="schedule:run-1",
    )

    assert first.duplicate is False
    assert again.duplicate is True
    charged = [
        a for k, a in await _entries(db_session, world, world.us.tenant_id) if k == ENTRY_KIND
    ]
    assert len(charged) == 1


async def test_it_does_not_count_against_the_agents_cap(client: Any, db_session: Any) -> None:
    """El tope del agente habla de lo que gasta atendiendo. Si una rutina cara
    contara ahí, dejaría al agente sin responder a sus clientes."""
    from nexus_api.db.models import AgentMonthlySpend

    world = await money_world(db_session)
    await _assign(client, world, world.us.ref, UNIT, "USD")
    await charge_schedule(
        partner_id=world.partner_id,
        tenant_id=world.us.tenant_id,
        agent_id=None,
        amount_usd=2_000,
        usage_ref="schedule:run-1",
    )

    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        spend = (
            await db_session.execute(sa.select(sa.func.count()).select_from(AgentMonthlySpend))
        ).scalar_one()
    assert spend == 0
