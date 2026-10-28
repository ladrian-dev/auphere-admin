"""El ciclo de vida de una conversación en la Bandeja — spec 030 (D11 a D13).

Estados, derivados sin columna nueva de estado (D12):

* *responde el agente* — ``agent_active = true``;
* *espera a una persona* — ``status = ESCALATED`` (el agente pidió ayuda);
* *responde una persona* — ``agent_active = false`` y ``assigned_user_id``;
* *resuelta* — ``status = CLOSED``; si el contacto vuelve a escribir, se
  reabre y responde el agente.

**El escalado, en un solo sitio y en dos pasos.** La herramienta
``escalate.escalate_to_human`` —la única que escribe ``ESCALATED``— llama a:

1. ``mark_waiting``, **dentro** de su transacción: estado, evento con el
   motivo y el resumen que dio el agente y, **solo si el cliente tiene
   Bandeja**, el agente callado. Sin Bandeja el agente sigue respondiendo
   como hasta hoy: nadie atendería la conversación (clarificación del owner,
   2026-10-08).
2. ``announce_waiting``, **después** del commit: campana y correo a las
   personas del cliente (una vez por escalado) y el evento de tiempo real.
   Avisar antes del commit dejaba un aviso de un escalado que podía no haber
   ocurrido, y una consola que volvía a pedir la conversación y la veía igual.

Quitar la Bandeja o apagar el acceso devuelve al agente las conversaciones que
se quedaron calladas por un escalado (``release_escalated_for_tenant``): sin
Bandeja, nadie las atendería nunca.

**Spec 047 — el motivo (requisitos 2.3 y 1.5).** Toda conversación que espera
dice por qué, en ``conversations.waiting_reason`` (``contracts/events.md`` §2).
El escalado del agente es ``escalated``. Las puertas del turno (sin saldo,
pausa, canal con problemas, agente sin publicar, sin modelo, el modelo falló…)
pasan por ``mark_waiting_reason``: el mensaje ya está guardado, la conversación
espera a una persona con su motivo y el agente **no** se calla en ella —la
puerta ya lo calla—; cuando la puerta se abre y el agente vuelve a contestar,
``release_reason`` la devuelve sola. Fuera de la audiencia guarda el motivo sin
ir a la Bandeja, y «la lleva una persona» lo guarda sin pisar una espera.

Ninguna función hace commit en la sesión que recibe.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    ClientAccess,
    ClientModule,
    Conversation,
    ConversationEvent,
    ConversationEventKind,
    ConversationStatus,
    Customer,
    NotificationAudience,
    NotificationKind,
    NotificationSeverity,
    PartnerTenant,
)
from nexus_api.db.models.conversation import WAITING_REASONS
from nexus_api.services import conversation_control
from nexus_api.services.inbox_stream import publish_inbox_event

log = structlog.get_logger(__name__)

#: El actor de lo que hace el agente en el hilo.
AGENT = "agent"
SYSTEM = "system"
CONTACT = "contact"

#: Spec 047: los motivos que escribe una puerta del turno. Mientras la puerta
#: está cerrada la conversación espera a una persona; al abrirse, el agente la
#: recupera en su siguiente respuesta.
GATE_REASONS: frozenset[str] = frozenset(
    {
        "no_balance",
        "agent_cap",
        "paused_agent",
        "paused_channel",
        "paused_client",
        "archived_client",
        "channel_problem",
        "agent_unpublished",
        "no_model",
        "provider_failure",
        "turn_limit",
    }
)
#: Motivos que se guardan sin convertir la conversación en una espera: fuera de
#: la audiencia no espera a nadie, y la que lleva una persona ya la atiende.
NOT_WAITING: frozenset[str] = frozenset({"out_of_audience", "human_takeover"})
#: Lo que el agente, al volver a contestar, deja de tener por cierto.
_STALE_WHEN_ANSWERED: frozenset[str] = GATE_REASONS | NOT_WAITING


def _now() -> datetime:
    return datetime.now(UTC)


async def tenant_has_inbox(session: AsyncSession, tenant_id: uuid.UUID) -> bool:
    """El cliente tiene la consola encendida y la Bandeja entre sus módulos."""
    access = await session.get(ClientAccess, tenant_id)
    return bool(access and access.enabled and ClientModule.INBOX.value in (access.modules or []))


async def record_event(
    session: AsyncSession,
    conversation: Conversation,
    kind: ConversationEventKind,
    actor: str,
    payload: dict[str, Any] | None = None,
) -> ConversationEvent:
    event = ConversationEvent(
        id=uuid.uuid4(),
        tenant_id=conversation.tenant_id,
        conversation_id=conversation.id,
        kind=kind.value,
        actor=actor,
        payload=dict(payload or {}),
    )
    session.add(event)
    return event


async def _contact_name(session: AsyncSession, conversation: Conversation) -> str | None:
    customer = await session.get(Customer, conversation.customer_id)
    if customer is None:
        return None
    return customer.name or customer.identifier


@dataclass(frozen=True)
class WaitingMark:
    """Lo que ``announce_waiting`` necesita después del commit."""

    tenant_id: uuid.UUID
    conversation_id: uuid.UUID
    event_id: uuid.UUID
    inbox: bool
    contact: str | None
    #: Spec 047: el código de ``contracts/events.md`` §2.
    reason: str | None = None


async def mark_waiting(
    session: AsyncSession,
    conversation: Conversation,
    *,
    reason: str | None,
    summary: str | None,
) -> WaitingMark:
    """El agente pidió ayuda: estado, evento y, si el cliente tiene Bandeja,
    el agente callado. No avisa: eso es ``announce_waiting``, tras el commit."""
    conversation.status = ConversationStatus.ESCALATED
    conversation.waiting_reason = "escalated"
    event = await record_event(
        session,
        conversation,
        ConversationEventKind.ESCALATED,
        AGENT,
        {"reason": (reason or "")[:500], "customer_summary": (summary or "")[:2000] or None},
    )
    inbox = await tenant_has_inbox(session, conversation.tenant_id)
    if inbox and conversation.agent_active:
        conversation_control.pause(
            conversation, reason="escalated", notes=reason, operator_label=AGENT
        )
        conversation.assigned_user_id = None
    if inbox:
        # Spec 031 (R8.2, R8.5): el aviso al teléfono nace aquí, en la
        # transacción del escalado. Si el escalado no se confirma, no avisa.
        from nexus_api.services import push_events

        await push_events.enqueue(
            session,
            tenant_id=conversation.tenant_id,
            kind="inbox.waiting",
            conversation_id=conversation.id,
            dedupe_key=f"inbox.waiting:{event.id}",
        )
    await session.flush()
    return WaitingMark(
        tenant_id=conversation.tenant_id,
        conversation_id=conversation.id,
        event_id=event.id,
        inbox=inbox,
        contact=await _contact_name(session, conversation) if inbox else None,
        reason="escalated",
    )


async def mark_waiting_reason(
    session: AsyncSession,
    conversation: Conversation,
    *,
    reason: str,
    inbox: bool | None = None,
) -> WaitingMark | None:
    """Spec 047: una puerta del turno no dejó contestar. El mensaje ya está
    guardado; aquí la conversación guarda el motivo y, salvo los de
    ``NOT_WAITING``, pasa a «Espera a una persona».

    Devuelve la marca **solo cuando empieza una espera** (o cambia su motivo):
    es lo que ``announce_waiting`` avisa tras el commit. Diez mensajes sin saldo
    son una espera y un aviso, no diez. A diferencia del escalado, el agente no
    se calla en la conversación: lo calla la puerta mientras está cerrada.
    """
    if reason not in WAITING_REASONS:  # pragma: no cover - error de programación
        raise ValueError(f"unknown waiting reason: {reason!r}")
    previous = conversation.waiting_reason
    if reason == "human_takeover" and conversation.status == ConversationStatus.ESCALATED:
        # Ya espera a una persona (un escalado, una puerta): que la lleve una
        # persona lo dirá quien la tome, no el siguiente mensaje del contacto.
        return None
    conversation.waiting_reason = reason
    if reason in NOT_WAITING:
        await session.flush()
        return None
    if conversation.status == ConversationStatus.ESCALATED and previous == reason:
        await session.flush()
        return None
    conversation.status = ConversationStatus.ESCALATED
    event = await record_event(
        session, conversation, ConversationEventKind.ESCALATED, SYSTEM, {"reason": reason}
    )
    has_inbox = await tenant_has_inbox(session, conversation.tenant_id) if inbox is None else inbox
    if has_inbox:
        from nexus_api.services import push_events

        await push_events.enqueue(
            session,
            tenant_id=conversation.tenant_id,
            kind="inbox.waiting",
            conversation_id=conversation.id,
            dedupe_key=f"inbox.waiting:{event.id}",
        )
    await session.flush()
    return WaitingMark(
        tenant_id=conversation.tenant_id,
        conversation_id=conversation.id,
        event_id=event.id,
        inbox=has_inbox,
        contact=await _contact_name(session, conversation) if has_inbox else None,
        reason=reason,
    )


async def release_reason(session: AsyncSession, conversation: Conversation) -> bool:
    """Spec 047: el agente vuelve a contestar. Un motivo de puerta deja de ser
    cierto, y la espera que abrió vuelve al agente. El escalado no: ese lo
    resuelve una persona."""
    reason = conversation.waiting_reason
    if reason not in _STALE_WHEN_ANSWERED:
        return False
    conversation.waiting_reason = None
    if reason in GATE_REASONS and conversation.status == ConversationStatus.ESCALATED:
        conversation.status = ConversationStatus.OPEN
        await record_event(
            session,
            conversation,
            ConversationEventKind.RELEASED,
            SYSTEM,
            {"why": "gate_open", "reason": reason},
        )
    await session.flush()
    return True


async def announce_waiting(mark: WaitingMark, *, redis: Redis | None = None) -> None:
    """Campana, correo y tiempo real de un escalado ya confirmado. Sin Bandeja
    no hay a quién avisar. Nunca lanza: el aviso no puede tumbar el escalado."""
    if not mark.inbox:
        return
    await _notify_waiting(mark)
    await publish_inbox_event(
        redis,
        tenant_id=mark.tenant_id,
        event="conversation.updated",
        conversation_id=mark.conversation_id,
    )


async def _notify_waiting(mark: WaitingMark) -> None:
    """En su propia sesión de plataforma: ``console_notifications`` no es una
    tabla del cliente. La campana deduplica por escalado (``event_id``)."""
    from nexus_api.services.console_notifications import emit

    try:
        async with get_sessionmaker()() as session, session.begin():
            access = await session.get(ClientAccess, mark.tenant_id)
            if access is None:
                return
            ref = await session.scalar(
                sa.select(PartnerTenant.external_client_ref).where(
                    PartnerTenant.partner_id == access.partner_id,
                    PartnerTenant.tenant_id == mark.tenant_id,
                )
            )
            if ref is None:
                return
            await emit(
                session,
                partner_id=access.partner_id,
                kind=NotificationKind.INBOX_WAITING,
                severity=NotificationSeverity.WARNING,
                external_client_ref=ref,
                data={
                    "conversation_id": str(mark.conversation_id),
                    "contact": mark.contact,
                    # Spec 047: por qué espera; nunca el texto del mensaje.
                    "reason": mark.reason,
                },
                dedupe_key=f"inbox.waiting:{mark.event_id}",
                audience=NotificationAudience.CLIENT,
            )
    except Exception as exc:  # pragma: no cover - el aviso no puede tumbar el escalado
        log.warning("inbox_lifecycle.notify_failed", error=str(exc))


async def resolve(session: AsyncSession, conversation: Conversation, *, actor: str) -> bool:
    """Resuelta: sale de la lista por defecto. Si el contacto vuelve a escribir
    responde el agente, así que el agente queda listo (idempotente)."""
    if conversation.status == ConversationStatus.CLOSED:
        return False
    conversation.status = ConversationStatus.CLOSED
    conversation.closed_at = _now()
    conversation.assigned_user_id = None
    conversation.waiting_reason = None
    # Spec 047 (requisito 53): la derivación de Recepción dura lo que la
    # conversación; la siguiente empieza otra vez en Recepción y sin saltos.
    conversation.handled_by_agent_id = None
    conversation.reception_hops = 0
    if not conversation.agent_active:
        conversation_control.resume(conversation)
    await record_event(session, conversation, ConversationEventKind.RESOLVED, actor)
    await session.flush()
    return True


async def reopen(session: AsyncSession, conversation: Conversation, *, actor: str) -> bool:
    """Vuelve a la lista y responde el agente. Idempotente."""
    if conversation.status != ConversationStatus.CLOSED:
        return False
    conversation.status = ConversationStatus.OPEN
    conversation.closed_at = None
    conversation.assigned_user_id = None
    conversation.waiting_reason = None
    if not conversation.agent_active:
        conversation_control.resume(conversation)
    await record_event(session, conversation, ConversationEventKind.REOPENED, actor)
    await session.flush()
    return True


async def release_escalated_for_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, *, actor: str
) -> int:
    """Sin Bandeja, las conversaciones calladas por un escalado vuelven al
    agente. Las que una persona tomó a mano se respetan: esa persona sigue
    con su WhatsApp y el admin puede devolverlas."""
    rows = (
        (
            await session.execute(
                sa.select(Conversation).where(
                    Conversation.tenant_id == tenant_id,
                    Conversation.status == ConversationStatus.ESCALATED,
                    Conversation.agent_active.is_(False),
                    Conversation.assigned_user_id.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    for conversation in rows:
        conversation_control.resume(conversation)
        conversation.waiting_reason = None
        await record_event(
            session,
            conversation,
            ConversationEventKind.RELEASED,
            actor,
            {"why": "inbox_removed"},
        )
    if rows:
        await session.flush()
    return len(rows)


async def tell_escalation_recipients(
    session: AsyncSession, conversation: Conversation, *, reason: str
) -> None:
    """Spec 047 (requisito 2.5): sin Bandeja, los destinatarios de escalado del
    canal se enteran por la vía de hoy —la fila ``conversation.escalated`` que el
    alertador convierte en la plantilla al dueño— hasta que la ola 4 traiga los
    destinatarios por canal. Sin texto del mensaje: solo el motivo."""
    from nexus_api.repositories import AuditRepository

    await AuditRepository(session).record(
        actor="system:turn",
        action="conversation.escalated",
        target=str(conversation.id),
        before=None,
        after={"status": conversation.status.value, "reason": reason},
    )


__all__ = [
    "AGENT",
    "CONTACT",
    "GATE_REASONS",
    "NOT_WAITING",
    "SYSTEM",
    "WaitingMark",
    "announce_waiting",
    "mark_waiting",
    "mark_waiting_reason",
    "record_event",
    "release_escalated_for_tenant",
    "release_reason",
    "reopen",
    "resolve",
    "tell_escalation_recipients",
    "tenant_has_inbox",
]
