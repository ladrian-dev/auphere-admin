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
from nexus_api.services import conversation_control
from nexus_api.services.inbox_stream import publish_inbox_event

log = structlog.get_logger(__name__)

#: El actor de lo que hace el agente en el hilo.
AGENT = "agent"
SYSTEM = "system"
CONTACT = "contact"


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
    await session.flush()
    return WaitingMark(
        tenant_id=conversation.tenant_id,
        conversation_id=conversation.id,
        event_id=event.id,
        inbox=inbox,
        contact=await _contact_name(session, conversation) if inbox else None,
    )


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
                data={"conversation_id": str(mark.conversation_id), "contact": mark.contact},
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


__all__ = [
    "AGENT",
    "CONTACT",
    "SYSTEM",
    "WaitingMark",
    "announce_waiting",
    "mark_waiting",
    "record_event",
    "release_escalated_for_tenant",
    "reopen",
    "resolve",
    "tenant_has_inbox",
]
