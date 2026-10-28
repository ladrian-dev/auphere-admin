"""El reparto de un aviso a los teléfonos — spec 031, R8.2 a R8.7, R9 (research D6).

El worker (``push-dispatcher``) lo usa en dos pasos por tenant, con el envío a
Apple y a Google entre ellos y **fuera** de cualquier transacción:

1. :func:`claim` — en la transacción del tenant: toma los eventos pendientes con
   ``FOR UPDATE SKIP LOCKED``, les pone un **plazo** (``next_attempt_at``) para
   que otra réplica no los repita mientras se envían, calcula los destinatarios
   **en ese momento** y compone el aviso con los datos de ese momento. Deja una
   ``client_push_deliveries`` por teléfono (``queued`` o ``skipped`` con su
   razón) y devuelve lo que hay que enviar.
2. :func:`settle` — en otra transacción: anota lo que pasó. Lo transitorio se
   reintenta con espera creciente, como mucho ``MAX_ATTEMPTS`` veces.

**Dos sesiones, a propósito.** Los datos del cliente (conversaciones,
contactos, mensajes, eventos y entregas) se leen bajo la RLS del tenant. La
identidad —teléfonos, membresías, acceso, la campana y el partner— se lee como
en ``resolve_client_principal``: con el usuario de conexión y filtrando por el
tenant explícitamente. Es lo que permite la regla de **un destino, un dueño**,
que cruza clientes (data-model §0158).

**Nada se envía si ya no es cierto** (``no_longer_true``): una conversación que
alguien ya tomó no avisa de que espera, y un mensaje en una conversación que ya
no atiende la persona no se le avisa.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import sqlalchemy as sa
import structlog
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexus_api.config import get_settings
from nexus_api.core.client_auth import open_client
from nexus_api.db.models import (
    ClientAccess,
    ClientMembership,
    ClientMemberStatus,
    ClientPhone,
    ClientPushDelivery,
    ClientPushEvent,
    ConsoleNotification,
    Conversation,
    ConversationEvent,
    ConversationStatus,
    Customer,
    Message,
    MessageDirection,
    Partner,
    Reservation,
)
from nexus_api.services import inbox_view, push_texts
from nexus_api.services.business import hours as business_hours
from nexus_api.services.business_hours import load_business_hours
from nexus_api.services.push_payloads import (
    Notice,
    agents_url,
    inbox_url,
    reservas_url,
    usage_url,
)

log = structlog.get_logger(__name__)

#: Mientras se envía, otra réplica no toma el evento.
LEASE = timedelta(minutes=2)
#: Intentos de un evento con entregas transitorias pendientes (contracts/push.md).
MAX_ATTEMPTS = 5
#: Eventos por tenant y vuelta.
BATCH = 20

_INBOX_KINDS = frozenset({"inbox.waiting", "inbox.message_for_you"})
#: Spec 043: los avisos de Reservas, solo a clientes con el módulo.
_RESERVAS_KINDS = frozenset(
    {"reservas.agent_change", "reservas.cancelled_today", "reservas.waitlist_accepted"}
)
#: Spec 045 (R5.4): lo que atraviesa el silencio fuera de horario.
URGENT_KINDS = frozenset({"inbox.waiting"})


@dataclass(frozen=True)
class Outgoing:
    """Un aviso a un teléfono, listo para salir."""

    delivery_id: uuid.UUID
    event_id: uuid.UUID
    phone_id: uuid.UUID
    provider: str
    token: str
    apns_environment: str | None
    notice: Notice


Outcome = Literal["sent", "failed", "retry", "unregistered"]


@dataclass(frozen=True)
class Result:
    delivery_id: uuid.UUID
    event_id: uuid.UUID
    phone_id: uuid.UUID
    outcome: Outcome
    provider_message_id: str | None = None
    error_code: str | None = None


@dataclass
class _Target:
    phone: ClientPhone
    skip: str | None = None


def backoff(attempt: int) -> timedelta:
    """15 s, 30 s, 1 min, 2 min, 4 min."""
    return timedelta(seconds=15 * 2 ** max(attempt - 1, 0))


def _now() -> datetime:
    return datetime.now(UTC)


# ── destinatarios ─────────────────────────────────────────────────────


async def _targets(
    identity: AsyncSession, event: ClientPushEvent, session: AsyncSession
) -> list[_Target]:
    """Los teléfonos activos de las personas del cliente **en este momento**,
    con la razón por la que alguno no recibe nada (R7.2, R9.3, R11.2).

    El cliente tiene que estar abierto con **la misma regla** que cada petición
    del teléfono (``open_client``): si el partner lo archivó, se suspendió o
    apagó su acceso, un aviso pendiente no sale, igual que el teléfono ya no
    puede leer."""
    access = await identity.get(ClientAccess, event.tenant_id)
    outside_hours = event.kind not in URGENT_KINDS and await _outside_hours(
        session, event.tenant_id
    )
    open_for: dict[uuid.UUID, bool] = {}
    rows = (
        await identity.execute(
            sa.select(ClientPhone, ClientMembership.status)
            .join(
                ClientMembership,
                sa.and_(
                    ClientMembership.id == ClientPhone.client_membership_id,
                    ClientMembership.tenant_id == ClientPhone.tenant_id,
                ),
            )
            .where(ClientPhone.tenant_id == event.tenant_id, ClientPhone.revoked_at.is_(None))
        )
    ).all()
    out: list[_Target] = []
    for phone, member_status in rows:
        if (
            event.kind == "inbox.message_for_you"
            and phone.principal_id != event.target_principal_id
        ):
            continue
        target = _Target(phone=phone)
        if phone.partner_id not in open_for:
            open_for[phone.partner_id] = (
                await open_client(identity, partner_id=phone.partner_id, tenant_id=event.tenant_id)
            ) is not None
        if member_status != ClientMemberStatus.ACTIVE.value:
            target.skip = "phone_revoked"
        elif (
            not open_for[phone.partner_id]
            or access is None
            or (event.kind in _INBOX_KINDS and "inbox" not in (access.modules or []))
            or (event.kind in _RESERVAS_KINDS and "reservas" not in (access.modules or []))
        ):
            target.skip = "module_missing"
        elif event.kind not in (phone.notice_kinds or []):
            target.skip = "kind_disabled"
        elif outside_hours and phone.quiet_outside_hours:
            target.skip = "quiet_hours"
        elif not phone.push_token or not phone.push_provider:
            target.skip = "no_push_token"
        elif await _token_owned_elsewhere(identity, phone):
            target.skip = "token_owned_elsewhere"
        out.append(target)
    return out


async def _outside_hours(session: AsyncSession, tenant_id: uuid.UUID) -> bool:
    """¿Es ahora fuera del horario del negocio? Sin horario, nunca (spec 045,
    R5.5): no se puede saber qué es fuera.

    Spec 047: el horario de la ficha, con los turnos nocturnos y las fechas
    especiales (un festivo cerrado es fuera de horario). Se lee con la sesión
    del cliente: las tablas de la ficha tienen la RLS forzada."""
    hours = await load_business_hours(session, tenant_id)
    state = business_hours.open_state(hours, _now())
    return state.known and not state.open


async def _token_owned_elsewhere(identity: AsyncSession, phone: ClientPhone) -> bool:
    """**Un destino, un dueño.** Si otra fila activa —de cualquier cliente— tiene
    el mismo destino registrado después, este teléfono ya no es su dueño: no se
    le envía y se le quita (data-model §0158)."""
    newer = await identity.scalar(
        sa.select(ClientPhone.id).where(
            ClientPhone.push_token == phone.push_token,
            ClientPhone.id != phone.id,
            ClientPhone.revoked_at.is_(None),
            ClientPhone.push_token_updated_at
            > (phone.push_token_updated_at or datetime.min.replace(tzinfo=UTC)),
        )
    )
    if newer is None:
        return False
    await identity.execute(
        sa.update(ClientPhone)
        .where(ClientPhone.id == phone.id)
        .values(push_token=None, push_provider=None, push_token_updated_at=None)
    )
    return True


# ── el texto ──────────────────────────────────────────────────────────


async def _contact(session: AsyncSession, conv: Conversation) -> str | None:
    customer = await session.get(Customer, conv.customer_id)
    # El nombre, nunca el identificador: el identificador es el teléfono (R9.2).
    return customer.name if customer is not None else None


async def _waiting_reason(session: AsyncSession, conv: Conversation) -> str | None:
    event = await session.scalar(
        sa.select(ConversationEvent)
        .where(
            ConversationEvent.conversation_id == conv.id,
            ConversationEvent.kind == "escalated",
        )
        .order_by(ConversationEvent.created_at.desc())
        .limit(1)
    )
    if event is None:
        return None
    reason = (event.payload or {}).get("reason")
    return str(reason) if reason else None


async def _last_inbound(session: AsyncSession, conv: Conversation) -> Message | None:
    msg: Message | None = await session.scalar(
        sa.select(Message)
        .where(
            Message.conversation_id == conv.id,
            Message.direction == MessageDirection.INBOUND,
            Message.skipped_reason.is_(None),
        )
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    return msg


async def _waiting_count(session: AsyncSession) -> int:
    _unread, waiting = await inbox_view.counts(session, me="")
    return waiting


async def _balance_contact(identity: AsyncSession, partner_id: uuid.UUID) -> str:
    partner = await identity.get(Partner, partner_id)
    if partner is None or partner.slug in get_settings().auphere_partner_slug_set:
        return "Auphere"
    return partner.name


async def compose(
    session: AsyncSession, identity: AsyncSession, event: ClientPushEvent, *, locale: str
) -> Notice | None:
    """El aviso en ``locale`` con los datos de ahora, o ``None`` si el hecho ya
    no es cierto. ``session`` va bajo la RLS del tenant."""
    badge = await _waiting_count(session)
    if event.kind in _INBOX_KINDS:
        if event.conversation_id is None:
            return None
        conv = await session.get(Conversation, event.conversation_id)
        # Spec 045 (R2.4): lo que la Bandeja no enseña no avisa.
        if conv is None or conv.attended_at is None:
            return None
        contact = await _contact(session, conv)
        if event.kind == "inbox.waiting":
            if conv.status != ConversationStatus.ESCALATED or conv.assigned_user_id is not None:
                return None
            text = push_texts.waiting(
                contact=contact, reason=await _waiting_reason(session, conv), locale=locale
            )
        else:
            if conv.agent_active or conv.assigned_user_id != event.target_principal_id:
                return None
            last = await _last_inbound(session, conv)
            text = push_texts.message(
                contact=contact,
                content=last.content if last else None,
                media_kind=last.media_kind if last else None,
                locale=locale,
            )
        return Notice(
            kind=event.kind,
            title=text.title,
            body=text.body,
            url=inbox_url(conv.id),
            thread=str(conv.id),
            badge=badge,
        )
    if event.kind in _RESERVAS_KINDS:
        return await _reservas_notice(session, event, locale=locale, badge=badge)
    # client.balance y agents.state — la fila de la campana es de plataforma: se
    # lee como identidad.
    if event.notification_id is None:
        return None
    row = await identity.get(ConsoleNotification, event.notification_id)
    if row is None:
        return None
    if event.kind == "agents.state":
        return await _agents_notice(session, row, event, locale=locale, badge=badge)
    days = (row.payload or {}).get("days_left")
    text = push_texts.balance(
        kind=push_texts.WALLET_AS_BALANCE.get(row.kind, row.kind),
        days_left=int(days) if isinstance(days, (int, float)) else None,
        contact=await _balance_contact(identity, row.partner_id),
        locale=locale,
    )
    return Notice(
        kind=event.kind,
        title=text.title,
        body=text.body,
        url=usage_url(),
        thread="balance",
        badge=badge,
    )


async def _agents_notice(
    session: AsyncSession,
    row: ConsoleNotification,
    event: ClientPushEvent,
    *,
    locale: str,
    badge: int,
) -> Notice | None:
    """Spec 047: el aviso de un agente o de un número. ``session`` va bajo la RLS
    del tenant: un agente que ya no existe no avisa."""
    from nexus_api.db.models import Agent

    payload = row.payload or {}
    raw = payload.get("agent_id")
    try:
        agent_id = uuid.UUID(str(raw))
    except (TypeError, ValueError):
        return None
    agent = await session.get(Agent, agent_id)
    if agent is None:
        return None
    text = push_texts.agents(
        kind=row.kind, agent=agent.name, reason=payload.get("reason"), locale=locale
    )
    return Notice(
        kind=event.kind,
        title=text.title,
        body=text.body,
        url=agents_url(agent.id, payload.get("channel_id")),
        thread=f"agent:{agent.id}",
        badge=badge,
    )


async def _reservas_notice(
    session: AsyncSession, event: ClientPushEvent, *, locale: str, badge: int
) -> Notice | None:
    """Spec 043: el aviso de una reserva, sin nombre del cliente final ni nota.
    ``None`` si ya no es cierto (la cancelaron antes de repartir…)."""
    from nexus_api.services.reservations.core import load_ctx

    if event.reservation_id is None:
        return None
    res = await session.get(Reservation, event.reservation_id)
    ctx = await load_ctx(session, event.tenant_id)
    if res is None or ctx is None:
        return None
    if event.kind == "reservas.agent_change" and res.status not in ("pending", "confirmed"):
        return None
    if event.kind == "reservas.cancelled_today" and res.status != "cancelled":
        return None
    text = push_texts.reservas(
        kind=event.kind,
        at=ctx.local(res.starts_at),
        party=res.party_size if res.mode == "capacity" else None,
        changed=event.dedupe_key.rsplit(":", 1)[-1] not in ("1",)
        if event.kind == "reservas.agent_change"
        else False,
        locale=locale,
    )
    return Notice(
        kind=event.kind,
        title=text.title,
        body=text.body,
        url=reservas_url(res.id),
        thread=f"reserva:{res.id}",
        badge=badge,
    )


# ── los dos pasos ─────────────────────────────────────────────────────


async def claim(
    session: AsyncSession,
    identity_factory: async_sessionmaker[AsyncSession],
    *,
    now: datetime | None = None,
    limit: int = BATCH,
) -> list[Outgoing]:
    """Paso 1. ``session`` está dentro de la transacción del tenant (RLS)."""
    ts = now or _now()
    events = (
        await session.scalars(
            sa.select(ClientPushEvent)
            .where(
                ClientPushEvent.status == "pending",
                sa.or_(
                    ClientPushEvent.next_attempt_at.is_(None),
                    ClientPushEvent.next_attempt_at <= ts,
                ),
            )
            .order_by(ClientPushEvent.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    ).all()
    if not events:
        return []
    outgoing: list[Outgoing] = []
    async with identity_factory() as identity, identity.begin():
        for event in events:
            event.attempts += 1
            event.next_attempt_at = ts + LEASE
            outgoing.extend(await _plan_event(session, identity, event, ts))
    await session.flush()
    return outgoing


async def _plan_event(
    session: AsyncSession, identity: AsyncSession, event: ClientPushEvent, ts: datetime
) -> list[Outgoing]:
    targets = await _targets(identity, event, session)
    for t in targets:
        await session.execute(
            insert(ClientPushDelivery)
            .values(
                id=uuid.uuid4(),
                tenant_id=event.tenant_id,
                event_id=event.id,
                phone_id=t.phone.id,
                status="skipped" if t.skip else "queued",
                skip_reason=t.skip,
            )
            .on_conflict_do_nothing(constraint="uq_client_push_deliveries_event_phone")
        )
    queued = (
        await session.scalars(
            sa.select(ClientPushDelivery).where(
                ClientPushDelivery.event_id == event.id, ClientPushDelivery.status == "queued"
            )
        )
    ).all()
    if not queued:
        _done(event, ts)
        return []
    phones = {t.phone.id: t.phone for t in targets if t.skip is None}
    by_locale: dict[str, Notice | None] = {}
    out: list[Outgoing] = []
    for delivery in queued:
        phone = phones.get(delivery.phone_id)
        if phone is None or not phone.push_token or not phone.push_provider:
            # Entre intentos el teléfono se cerró, apagó el tipo o perdió el destino.
            delivery.status = "skipped"
            delivery.skip_reason = "phone_revoked"
            continue
        if phone.locale not in by_locale:
            by_locale[phone.locale] = await compose(session, identity, event, locale=phone.locale)
        notice = by_locale[phone.locale]
        if notice is None:
            delivery.status = "skipped"
            delivery.skip_reason = "no_longer_true"
            continue
        out.append(
            Outgoing(
                delivery_id=delivery.id,
                event_id=event.id,
                phone_id=phone.id,
                provider=phone.push_provider,
                token=phone.push_token,
                apns_environment=phone.apns_environment,
                notice=notice,
            )
        )
    if not out:
        _done(event, ts)
    return out


def _done(event: ClientPushEvent, ts: datetime) -> None:
    event.status = "fanned_out"
    event.fanned_out_at = ts
    event.next_attempt_at = None


async def settle(
    session: AsyncSession,
    identity_factory: async_sessionmaker[AsyncSession],
    results: Sequence[Result],
    *,
    now: datetime | None = None,
) -> None:
    """Paso 2. ``session`` está dentro de la transacción del tenant (RLS)."""
    if not results:
        return
    ts = now or _now()
    unregistered: list[uuid.UUID] = []
    for r in results:
        values: dict[str, object] = {"error_code": r.error_code}
        if r.outcome == "sent":
            values |= {
                "status": "sent",
                "sent_at": ts,
                "provider_message_id": r.provider_message_id,
            }
        elif r.outcome in ("failed", "unregistered"):
            values |= {"status": "failed"}
            if r.outcome == "unregistered":
                unregistered.append(r.phone_id)
        await session.execute(
            sa.update(ClientPushDelivery)
            .where(ClientPushDelivery.id == r.delivery_id)
            .values(**values)
        )
    if unregistered:
        # El destino ya no existe: se quita, y el teléfono lo registrará de nuevo
        # la próxima vez que se abra la app.
        async with identity_factory() as identity, identity.begin():
            await identity.execute(
                sa.update(ClientPhone)
                .where(ClientPhone.id.in_(unregistered))
                .values(push_token=None, push_provider=None, push_token_updated_at=None)
            )
    for event_id in {r.event_id for r in results}:
        event = await session.get(ClientPushEvent, event_id)
        if event is None:  # pragma: no cover - la FK lo impide
            continue
        pending = await session.scalar(
            sa.select(sa.func.count())
            .select_from(ClientPushDelivery)
            .where(ClientPushDelivery.event_id == event_id, ClientPushDelivery.status == "queued")
        )
        if not pending:
            _done(event, ts)
        elif event.attempts >= MAX_ATTEMPTS:
            await session.execute(
                sa.update(ClientPushDelivery)
                .where(
                    ClientPushDelivery.event_id == event_id, ClientPushDelivery.status == "queued"
                )
                .values(status="failed", error_code="max_attempts")
            )
            event.status = "failed"
            event.next_attempt_at = None
            event.last_error = "max_attempts"
            log.warning("push_fanout.event_failed", event_id=str(event_id))
        else:
            event.next_attempt_at = ts + backoff(event.attempts)
    await session.flush()


async def tenants_with_pending(
    identity: AsyncSession, *, now: datetime | None = None
) -> list[uuid.UUID]:
    """El barrido de seguridad: tenants con eventos pendientes que ya tocan.
    Cubre avisos de ``pg_notify`` perdidos y los reintentos, que el disparador
    de inserción no ve."""
    ts = now or _now()
    rows = await identity.execute(
        sa.select(ClientPushEvent.tenant_id)
        .where(
            ClientPushEvent.status == "pending",
            sa.or_(
                ClientPushEvent.next_attempt_at.is_(None), ClientPushEvent.next_attempt_at <= ts
            ),
        )
        .distinct()
    )
    return [row[0] for row in rows]


__all__ = [
    "BATCH",
    "LEASE",
    "MAX_ATTEMPTS",
    "Outgoing",
    "Result",
    "backoff",
    "claim",
    "compose",
    "settle",
    "tenants_with_pending",
]
