"""Corte por presupuesto sin dejar al agente mudo (WP-20).

El corte duro es la parte del presupuesto que puede salir muy mal. La
tentación es "no responder": es lo más barato y lo más fácil de
implementar. También es el peor fallo posible de este producto — el
cliente final no sabe que existe un presupuesto, solo ve que el negocio
al que escribió no le contesta, y en el canal de partners ese negocio no
es ni siquiera cliente nuestro.

Así que cortar significa exactamente tres cosas, en este orden:

1. **No se abre el turno.** No hay LLM, no hay herramientas, no hay
   gasto. Eso es lo que el presupuesto venía a conseguir.
2. **Se responde igual**, una sola vez por conversación, con un traspaso
   a una persona. Una sola vez porque repetir el mismo aviso en cada
   mensaje convierte el corte en spam.
3. **Se avisa al dueño** por el camino de escalado que ya existe (fila
   en ``audit_log`` → alerter → plantilla de WhatsApp). Si nadie se
   entera, el corte solo consigue que el negocio pierda clientes en
   silencio.

Spec 047 (requisito 44.8): el mensaje del contacto ya está guardado cuando se
llega aquí, y la conversación pasa a la Bandeja como «Espera a una persona»
con el motivo ``turn_limit``.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Conversation
from nexus_api.services import inbox_lifecycle

from nexus_worker.metering.budget import BudgetVerdict

log = structlog.get_logger(__name__)

ACTOR = "budget_gate"
#: Spec 047 (``contracts/events.md`` §2): el corte del presupuesto de Auphere
#: es un límite de gasto, no la bolsa del cliente —no se arregla asignando
#: saldo—, así que su motivo es «Límite del turno» y no «Sin saldo».
CUTOFF_REASON = "turn_limit"
# Acción del audit_log que el alerter traduce a plantilla de WhatsApp.
ESCALATION_ACTION = "budget.hard_limit_reached"

# El texto que lee el cliente final. Deliberadamente NO menciona
# presupuesto, coste ni ningún detalle interno: para quien escribe, lo
# único cierto y accionable es que le va a contestar una persona.
HANDOFF_MESSAGE = (
    "Gracias por tu mensaje. En este momento no puedo atenderte por aquí, "
    "pero ya avisé al equipo y una persona te responde en breve."
)

# Ventana en la que no se repite el aviso a la misma conversación.
_REPEAT_WINDOW = "6 hours"


_ALREADY_WARNED_SQL = sa.text(
    """
    SELECT 1 FROM messages
     WHERE conversation_id = :c
       AND direction = 'outbound'
       AND content = :body
       AND created_at > now() - interval '"""
    + _REPEAT_WINDOW
    + """'
     LIMIT 1
    """
)


async def apply_hard_cutoff(
    *,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    verdict: BudgetVerdict,
) -> bool:
    """Responde el traspaso y escala al dueño. Devuelve si escribió aviso.

    No lanza: un fallo aquí no puede convertirse en un turno atascado en
    el stream. Lo peor que pasa es que el aviso no salga, y eso ya está
    en el log.
    """
    sm = get_sessionmaker()
    mark: inbox_lifecycle.WaitingMark | None = None
    try:
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            # Spec 047 (requisito 44.8): el corte cumple el requisito 2. El
            # mensaje ya está guardado (el despachador guarda antes de las
            # puertas); aquí la conversación espera a una persona con su motivo.
            conversation = await session.get(Conversation, conversation_id)
            if conversation is not None:
                mark = await inbox_lifecycle.mark_waiting_reason(
                    session, conversation, reason=CUTOFF_REASON
                )
            already = await session.scalar(
                _ALREADY_WARNED_SQL, {"c": str(conversation_id), "body": HANDOFF_MESSAGE}
            )
            if already:
                # Ya se avisó hace poco en esta conversación. Se sigue sin
                # abrir turno, pero no se repite el mensaje: el corte no
                # puede convertirse en spam hacia el cliente final.
                await session.commit()
                await _announce(mark)
                return False

            await session.execute(
                sa.text(
                    "INSERT INTO messages "
                    "(tenant_id, conversation_id, direction, status, content, actor_kind) "
                    "VALUES (:t, :c, 'outbound', 'pending', :body, 'system')"
                ),
                {"t": str(tenant_id), "c": str(conversation_id), "body": HANDOFF_MESSAGE},
            )
            # Escalado por el camino que ya existe: el alerter lee
            # ``audit_log`` y dispara la plantilla al dueño. Reutilizarlo
            # evita una segunda ruta de notificación que mantener.
            await session.execute(
                sa.text(
                    "INSERT INTO audit_log "
                    "(tenant_id, actor, action, target, after_json) "
                    "VALUES (:t, :a, :act, :target, CAST(:payload AS jsonb))"
                ),
                {
                    "t": str(tenant_id),
                    "a": ACTOR,
                    "act": ESCALATION_ACTION,
                    "target": f"conversation:{conversation_id}",
                    "payload": _payload(verdict),
                },
            )
            await session.commit()
        await _announce(mark)
        log.warning(
            "budget.hard_cutoff",
            tenant_id=str(tenant_id),
            conversation_id=str(conversation_id),
            scope=verdict.scope,
            period=verdict.period,
            spent=str(verdict.spent),
            limit=str(verdict.limit),
        )
        return True
    except Exception as exc:
        log.error("budget.cutoff_failed", tenant_id=str(tenant_id), error=str(exc))
        return False


async def _announce(mark: inbox_lifecycle.WaitingMark | None) -> None:
    """Con Bandeja, su gente se entera de la espera (uno por espera). Sin
    Bandeja el aviso al dueño ya es la fila de ``ESCALATION_ACTION``."""
    if mark is not None:
        await inbox_lifecycle.announce_waiting(mark)


def _payload(verdict: BudgetVerdict) -> str:
    import json

    return json.dumps(
        {
            "scope": verdict.scope,
            "period": verdict.period,
            "spent_usd": str(verdict.spent),
            "limit_usd": str(verdict.limit),
        }
    )
