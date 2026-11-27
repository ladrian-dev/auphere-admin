"""Lo que cuesta una rutina — spec 082, T018 (requisitos 9.1, 9.2 y 9.4).

Calcado de ``charge_tests``, y por las mismas razones:

- **Lo paga la bolsa del cliente**, como una conversación, porque el agente es
  suyo y el trabajo se hace para él.
- **No suma al tope del agente.** Ese tope habla de lo que el agente gasta
  atendiendo, y una rutina no atiende a nadie. Si contara ahí, poner una rutina
  cara dejaría al agente sin responder a sus clientes, que es exactamente lo que
  nadie quiere que pase de madrugada.
- **Si la bolsa llega a cero, los agentes se pausan igual**: sin dinero no hay
  turno que cobrar, venga de donde venga.
- **La misma ejecución no se cobra dos veces**: la ``usage_ref`` es la del turno
  y el asiento es idempotente por ella.

El asiento se llama ``debit_schedule`` para que el reparto por partidas lo
distinga de un turno de conversación sin tener que adivinar.
"""

from __future__ import annotations

import uuid

from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.services.wallet import bags

#: El asiento de la bolsa de una ejecución de rutina.
ENTRY_KIND = "debit_schedule"
#: El prefijo de la referencia del cobro. Lo escribe el medidor al cobrar y lo
#: lee el hilo para enseñar lo que salió de la bolsa: una sola forma, aquí, o
#: las dos puntas dejan de encontrarse.
REF_PREFIX = "schedule"


def usage_ref_for(run_id: uuid.UUID) -> str:
    """La referencia con la que se cobra —y se encuentra— una ejecución."""
    return f"{REF_PREFIX}:{run_id}"


async def charge_schedule(
    *,
    partner_id: uuid.UUID,
    tenant_id: uuid.UUID,
    agent_id: uuid.UUID | None,
    amount_usd: int,
    usage_ref: str,
) -> bags.Debit:
    """Cobra una ejecución de la bolsa del cliente, en su moneda."""
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
            kind=ENTRY_KIND,
        )
    if debit.emptied and not debit.duplicate:
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            await agent_states.pause_for_balance(session)
    return debit


__all__ = ["ENTRY_KIND", "REF_PREFIX", "charge_schedule", "usage_ref_for"]
