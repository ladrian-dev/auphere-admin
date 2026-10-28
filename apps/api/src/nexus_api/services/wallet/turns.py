"""El turno y la bolsa — spec 047, T157 (requisitos 43.8, 44.1 a 44.3 y 27.4).

- ``charge_turn``: cobra un turno de la bolsa del cliente (con el cambio del día),
  suma el gasto del agente a su mes y aplica su tope; si la bolsa llega a cero,
  los agentes publicados del cliente se pausan «sin saldo».
- ``after_balance_up``: la bolsa volvió a tener saldo: se reanudan **solo** los
  agentes que el sistema pausó por eso (27.4).

Cada parte en su sesión: la bolsa con el ``app.partner_id`` del partner; el gasto
y las pausas, con el ``app.tenant_id`` del cliente.
"""

from __future__ import annotations

import uuid

from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.services.wallet import alerts as wallet_alerts
from nexus_api.services.wallet import bags


async def bags_on(partner_id: uuid.UUID) -> bool:
    async with get_sessionmaker()() as session, session.begin():
        await apply_partner_to_session(session, partner_id)
        return await bags.bags_active(session, partner_id)


async def charge_turn(
    *,
    partner_id: uuid.UUID,
    tenant_id: uuid.UUID,
    agent_id: uuid.UUID | None,
    amount_usd: int,
    usage_ref: str,
) -> bags.Debit:
    from nexus_api.db.models import ClientWallet
    from nexus_api.services import agent_states

    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_partner_to_session(session, partner_id)
        debit = await bags.debit_turn(
            session,
            partner_id=partner_id,
            tenant_id=tenant_id,
            amount_usd=amount_usd,
            usage_ref=usage_ref,
            agent_id=agent_id,
        )
        bag = await session.get(ClientWallet, tenant_id)
        currency = bag.currency if bag is not None else "USD"
    if debit.duplicate:
        return debit
    notices: list[wallet_alerts.Alert] = []
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        if agent_id is not None and debit.spent:
            notices += await wallet_alerts.record_agent_spend(
                session,
                tenant_id=tenant_id,
                agent_id=agent_id,
                spent=debit.spent,
                currency=currency,
            )
        if debit.emptied:
            await agent_states.pause_for_balance(session)
    await wallet_alerts.announce(notices)
    return debit


async def after_balance_up(tenant_id: uuid.UUID) -> list[uuid.UUID]:
    from nexus_api.services import agent_states

    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        return await agent_states.resume_after_balance(session)


__all__ = ["after_balance_up", "bags_on", "charge_turn"]
