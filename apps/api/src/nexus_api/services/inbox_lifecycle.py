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

**Spec 056 — el aviso se cierra solo (requisito 8, D8).** Cuando la
conversación deja de esperar —alguien la toma, la devuelve al agente, la resuelve
o la elimina, la puerta se abre (``release_reason``) o el cliente se queda sin
Bandeja (``release_escalated_for_tenant``)—, su aviso ``inbox.waiting`` pasa a
atendido con ``mark_waiting_handled``: ``handled_at`` (migración 0227). Deja de
contar en la campana y sigue en la lista. Se llama tras el commit, en su propia
sesión de plataforma como ``_notify_waiting``, o dentro de la transacción de quien
ya tiene una de plataforma (``client_access.set_access``).

**Spec 058 — la audiencia antes que la pausa.** Un contacto fuera de la
audiencia de su número no espera a nadie, aunque haya una pausa. Si su
conversación esperaba por una puerta y nadie se la asignó, ``leave_gate_wait``
la saca de «Espera a una persona» con el motivo ``out_of_audience``. Quien llama cierra su
aviso con ``mark_waiting_handled``. La espera que pidió una persona, o la que
una persona tomó, conserva su motivo (la guarda de ``mark_waiting_reason``).

Ninguna función hace commit en la sesión que recibe.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.errors import IsolationViolation
from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Channel,
    ClientAccess,
    ClientModule,
    ConsoleNotification,
    Conversation,
    ConversationEvent,
    ConversationEventKind,
    ConversationStatus,
    Customer,
    Message,
    MessageDirection,
    NotificationAudience,
    NotificationKind,
    NotificationSeverity,
    PartnerTenant,
    Reservation,
    ReservationOffer,
    ReservationOutbox,
)
from nexus_api.db.models.conversation import WAITING_REASONS
from nexus_api.services import conversation_control
from nexus_api.services.inbox_stream import publish_inbox_event
from nexus_api.services.inbox_view import PLAYGROUND_PROVIDER, display_handle

log = structlog.get_logger(__name__)

#: El actor de lo que hace el agente en el hilo.
AGENT = "agent"
SYSTEM = "system"
CONTACT = "contact"

#: Spec 064 (requisito 5.1): los plazos del cierre por inactividad. ``NULL`` en
#: ``client_access.inbox_autoclose_hours`` es «nunca».
AUTOCLOSE_HOURS: tuple[int, ...] = (24, 72, 168, 720)
#: Conversaciones que una pasada cierra como mucho por cliente.
AUTOCLOSE_BATCH = 200
#: El motivo que lleva el evento ``resolved`` de un cierre por inactividad.
INACTIVITY = "inactivity"

#: Spec 064 (requisito 4.6): cuánto sigue vigente, sin respuesta, un envío por
#: plantilla que no viene de Reservas (la cobranza, un envío directo).
NOTICE_VALID_FOR = timedelta(days=7)

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
    """Sin nombre, el contacto se llama por su número como en la Bandeja: en
    WhatsApp, con «+» (spec 056, 13.3)."""
    customer = await session.get(Customer, conversation.customer_id)
    if customer is None:
        return None
    if customer.name:
        return customer.name
    channel = await session.get(Channel, conversation.channel_id)
    kind = channel.type.value if channel is not None else None
    return display_handle(customer.identifier, kind) or None


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
    if reason == "out_of_audience" and conversation.status == ConversationStatus.ESCALATED:
        # Spec 058 (requisito 2.2): sigue esperando —la pidió una persona, o
        # una persona se la asignó— y su motivo es el que la Bandeja pinta. Una
        # espera de puerta sin asignar ya la sacó ``leave_gate_wait``.
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


async def leave_gate_wait(session: AsyncSession, conversation: Conversation) -> bool:
    """Spec 058 (requisito 2.1): el contacto escribe ya fuera de la audiencia
    de su número. Una espera que abrió una puerta (una pausa, el saldo…) deja
    de ser cierta: su número no le respondería ni con todo activo, así que no
    espera a nadie. Deja de esperar, con el motivo ``out_of_audience``.

    Solo si la espera es de puerta y nadie se la asignó: lo que pidió una
    persona, o lo que una persona tomó a mano, se respeta (requisito 2.2; la
    misma regla que ``release_escalated_for_tenant``). No avisa ni escribe al
    contacto (2.3); su aviso pendiente lo cierra quien llama, tras el commit,
    con ``mark_waiting_handled``. Devuelve si la sacó."""
    previous = conversation.waiting_reason
    if (
        conversation.status != ConversationStatus.ESCALATED
        or previous not in GATE_REASONS
        or conversation.assigned_user_id is not None
    ):
        return False
    conversation.status = ConversationStatus.OPEN
    conversation.waiting_reason = "out_of_audience"
    await record_event(
        session,
        conversation,
        ConversationEventKind.RELEASED,
        SYSTEM,
        {"why": "out_of_audience", "reason": previous},
    )
    await session.flush()
    return True


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


async def mark_waiting_handled(
    tenant_id: uuid.UUID,
    conversation_ids: Iterable[uuid.UUID],
    *,
    session: AsyncSession | None = None,
) -> int:
    """Spec 056 (8.1): los avisos «espera a una persona» pendientes de esas
    conversaciones pasan a atendidos. Devuelve cuántos.

    ``console_notifications`` es del partner, no del cliente: el ``UPDATE``
    filtra por el partner y por el cliente (``external_client_ref``), así que el
    aviso de otro cliente del mismo partner no se toca aunque nombre el mismo id.

    Sin ``session`` abre la suya de plataforma y confirma: es lo que se llama tras
    el commit de una ruta lite (``scope.after_commit``) o del despachador, y nunca
    lanza, porque cerrar el aviso no puede tumbar lo que ya pasó. Con ``session``
    (una de plataforma, como la de ``client_access.set_access``) va en esa
    transacción."""
    ids = sorted({str(c) for c in conversation_ids})
    if not ids:
        return 0
    if session is not None:
        return await _handle_waiting(session, tenant_id, ids)
    try:
        async with get_sessionmaker()() as own, own.begin():
            return await _handle_waiting(own, tenant_id, ids)
    except Exception as exc:  # pragma: no cover - el aviso no puede tumbar la transición
        log.warning("inbox_lifecycle.handle_failed", error=str(exc))
        return 0


async def _handle_waiting(session: AsyncSession, tenant_id: uuid.UUID, ids: list[str]) -> int:
    access = await session.get(ClientAccess, tenant_id)
    if access is None:
        return 0
    ref = await session.scalar(
        sa.select(PartnerTenant.external_client_ref).where(
            PartnerTenant.partner_id == access.partner_id,
            PartnerTenant.tenant_id == tenant_id,
        )
    )
    if ref is None:
        return 0
    result = await session.execute(
        sa.update(ConsoleNotification)
        .where(
            ConsoleNotification.partner_id == access.partner_id,
            ConsoleNotification.external_client_ref == ref,
            ConsoleNotification.kind == NotificationKind.INBOX_WAITING.value,
            ConsoleNotification.handled_at.is_(None),
            ConsoleNotification.payload["conversation_id"].astext.in_(ids),
        )
        .values(handled_at=_now())
        .execution_options(synchronize_session=False)
    )
    return int(getattr(result, "rowcount", 0) or 0)


async def resolve(
    session: AsyncSession,
    conversation: Conversation,
    *,
    actor: str,
    payload: dict[str, Any] | None = None,
) -> bool:
    """Resuelta: sale de la lista por defecto. Si el contacto vuelve a escribir
    responde el agente, así que el agente queda listo (idempotente). ``payload``
    va al evento del hilo: el cierre por inactividad dice ahí su motivo."""
    if conversation.status == ConversationStatus.CLOSED:
        return False
    conversation.status = ConversationStatus.CLOSED
    conversation.closed_at = _now()
    conversation.assigned_user_id = None
    conversation.waiting_reason = None
    # Spec 064 (requisito 4): un asunto cerrado. Si el contacto vuelve a escribir,
    # o sale un aviso, el agente empieza desde aquí (``reopen``).
    conversation.cut_on_reopen = True
    # Spec 047 (requisito 53): la derivación de Recepción dura lo que la
    # conversación; la siguiente empieza otra vez en Recepción y sin saltos.
    conversation.handled_by_agent_id = None
    conversation.reception_hops = 0
    if not conversation.agent_active:
        conversation_control.resume(conversation)
    await record_event(session, conversation, ConversationEventKind.RESOLVED, actor, payload)
    await session.flush()
    return True


async def close_inactive(
    session: AsyncSession, *, hours: int, now: datetime, limit: int = AUTOCLOSE_BATCH
) -> list[uuid.UUID]:
    """Resuelve las conversaciones que llevan ``hours`` sin mensajes en ningún
    sentido (spec 064, requisito 5). Solo las que responde el agente: nunca una
    que espera a una persona, que lleva una persona, o que no está en la
    Bandeja. Las firma el sistema y dicen su motivo en el hilo. No avisa a
    nadie. Devuelve sus ids, para el aviso de tiempo real tras el commit.

    Corre en la sesión acotada al cliente: la RLS decide qué conversaciones ve."""
    rows = await session.execute(
        sa.select(Conversation)
        .join(Channel, Channel.id == Conversation.channel_id)
        .where(
            # Not only the RLS: a platform session would see every client (/cso 2026-11-19).
            Conversation.tenant_id == require_current_tenant(),
            Conversation.status == ConversationStatus.OPEN,
            Conversation.agent_active.is_(True),
            Conversation.assigned_user_id.is_(None),
            Conversation.waiting_reason.is_(None),
            Conversation.awaiting_owner_response.is_(False),
            sa.or_(Conversation.takeover_until.is_(None), Conversation.takeover_until <= now),
            Conversation.attended_at.is_not(None),
            Conversation.last_message_at <= now - timedelta(hours=hours),
            Channel.provider != PLAYGROUND_PROVIDER,
        )
        .order_by(Conversation.last_message_at)
        .limit(limit)
        # Lo que un turno tiene cogido se deja para la próxima pasada.
        .with_for_update(skip_locked=True, of=Conversation)
    )
    closed: list[uuid.UUID] = []
    for conversation in rows.scalars().all():
        if await resolve(session, conversation, actor=SYSTEM, payload={"reason": INACTIVITY}):
            closed.append(conversation.id)
    return closed


async def autoclose_tick(
    session: AsyncSession, tenant_id: uuid.UUID, now: datetime
) -> list[uuid.UUID]:
    """Una pasada del cierre por inactividad en un cliente, dentro de su sesión
    acotada. Sin plazo (``NULL`` = nunca, el valor de partida) o sin Bandeja, no
    hace nada."""
    if tenant_id != require_current_tenant():
        raise IsolationViolation("autoclose_tick: the tenant is not the session's")
    access = await session.get(ClientAccess, tenant_id)
    if access is None or access.inbox_autoclose_hours is None:
        return []
    if not (access.enabled and ClientModule.INBOX.value in (access.modules or [])):
        return []
    return await close_inactive(session, hours=access.inbox_autoclose_hours, now=now)


async def clear(session: AsyncSession, conversation: Conversation) -> None:
    """«Vaciar el chat» (owner, 2026-11-01). Nothing is erased (constitution §IV:
    borrar no existe): the Inbox and the agent read from ``attended_at`` on, so
    moving it to now leaves the chat empty for both. The rows stay for the
    retention rules. The Meta window (``last_inbound_at``, ``last_dm_at``) is
    the channel's, not the chat's, and does not move."""
    conversation.attended_at = _now()
    conversation.last_attended_inbound_at = None
    conversation.last_message_at = None
    await session.flush()


async def archive(session: AsyncSession, conversation: Conversation, *, actor: str) -> None:
    """«Eliminar el chat» (owner, 2026-11-01): out of the Inbox, archived rather
    than erased (constitution §IV). ``attended_at = NULL`` is exactly a
    conversation that does not exist for the Inbox (spec 045, R1); if the contact
    writes again it reopens with the agent and only the new messages show."""
    await resolve(session, conversation, actor=actor)
    conversation.attended_at = None
    conversation.last_attended_inbound_at = None
    await session.flush()


def _is_person(actor: str) -> bool:
    """Los actores de persona llevan su cuenta (``client:ana@…``); el contacto,
    el sistema, el eco del WhatsApp del negocio y la importación del historial,
    una sola palabra."""
    return ":" in actor


async def _cut_point(session: AsyncSession, conversation: Conversation, now: datetime) -> datetime:
    """Desde cuándo lee el agente tras una resolución (spec 064, 4.1 y 4.6).

    La resolución misma, adelantada al aviso más antiguo que el contacto aún no
    contestó y que sigue vigente. Sin él, el agente recibiría un «sí, voy» sin
    saber a qué contesta.

    Un aviso es algo que el negocio envió por su cuenta, no una respuesta:

    - lo de Reservas (su fila en ``reservation_outbox`` dice de qué cita o de
      qué oferta habla): vigente mientras la cita no ha pasado, o mientras la
      oferta sigue ``running``;
    - un envío por plantilla (la cobranza, un envío directo): vigente 7 días.

    El texto de espera que sale cuando una puerta no deja contestar también lo
    firma el sistema, pero es una respuesta a lo que el contacto escribió: no
    cuenta, y lo que una persona dijera después tampoco entra por él."""
    closed = conversation.closed_at or now
    last_inbound = await session.scalar(
        sa.select(sa.func.max(Message.created_at)).where(
            Message.conversation_id == conversation.id,
            Message.direction == MessageDirection.INBOUND,
            Message.created_at < closed,
        )
    )
    # ``jsonb_typeof``: un ``None`` explícito se guarda como ``null`` de JSON, que
    # no es ``NULL`` de SQL. Una plantilla de verdad es un objeto.
    is_template = sa.func.coalesce(
        sa.func.jsonb_typeof(Message.template_payload) == "object", sa.false()
    )
    pending = sa.select(Message.id, Message.created_at, is_template.label("template")).where(
        Message.conversation_id == conversation.id,
        Message.direction == MessageDirection.OUTBOUND,
        Message.actor_kind == SYSTEM,
        Message.created_at < closed,
    )
    if last_inbound is not None:
        pending = pending.where(Message.created_at > last_inbound)
    sent = (await session.execute(pending.order_by(Message.created_at))).all()
    if not sent:
        return closed
    about = {
        row.message_id: (row.starts_at, row.offer_status)
        for row in (
            await session.execute(
                sa.select(
                    ReservationOutbox.message_id,
                    Reservation.starts_at,
                    ReservationOffer.status.label("offer_status"),
                )
                .outerjoin(Reservation, Reservation.id == ReservationOutbox.reservation_id)
                .outerjoin(ReservationOffer, ReservationOffer.id == ReservationOutbox.offer_id)
                .where(ReservationOutbox.message_id.in_([m.id for m in sent]))
            )
        ).all()
    }
    for message in sent:
        if message.id in about:
            starts_at, offer_status = about[message.id]
            if offer_status is not None:
                valid = offer_status == "running"
            else:
                valid = starts_at is not None and starts_at > now
        else:
            valid = bool(message.template) and message.created_at >= now - NOTICE_VALID_FOR
        if valid:
            at: datetime = message.created_at
            return min(closed, at)
    return closed


async def reopen(session: AsyncSession, conversation: Conversation, *, actor: str) -> bool:
    """Vuelve a la lista y responde el agente. Idempotente.

    Spec 064 (requisito 4): si la resolvieron (``cut_on_reopen``) y quien la
    reabre es el contacto o un aviso del sistema, el agente empieza desde el
    punto de corte. Una persona que la reabre a mano deshace la resolución: el
    contexto sigue (4.4)."""
    if conversation.status != ConversationStatus.CLOSED:
        return False
    if conversation.cut_on_reopen:
        if not _is_person(actor):
            conversation.context_from = await _cut_point(session, conversation, _now())
        conversation.cut_on_reopen = False
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
) -> list[uuid.UUID]:
    """Sin Bandeja, las conversaciones calladas por un escalado vuelven al
    agente. Las que una persona tomó a mano se respetan: esa persona sigue
    con su WhatsApp y el admin puede devolverlas. Devuelve las que volvieron,
    para cerrar sus avisos (``mark_waiting_handled``, spec 056)."""
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
    return [conversation.id for conversation in rows]


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
    "AUTOCLOSE_HOURS",
    "CONTACT",
    "GATE_REASONS",
    "INACTIVITY",
    "NOT_WAITING",
    "SYSTEM",
    "WaitingMark",
    "announce_waiting",
    "autoclose_tick",
    "close_inactive",
    "leave_gate_wait",
    "mark_waiting",
    "mark_waiting_handled",
    "mark_waiting_reason",
    "record_event",
    "release_escalated_for_tenant",
    "release_reason",
    "reopen",
    "resolve",
    "tell_escalation_recipients",
    "tenant_has_inbox",
]
