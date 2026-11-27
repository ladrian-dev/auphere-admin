"""El rendimiento de un agente y sus conversaciones, solo con metadatos — spec 047,
T174 (requisitos 51.1 y 51.2), con las reglas de la spec 083.

- :func:`period_cycles`: las **conversaciones** de un periodo contadas como ciclos
  (spec 083, requisitos 2 a 4). Lo usan el informe del cliente
  (``services/client_report.py``) y :func:`agent_performance`: las dos páginas
  dicen lo mismo (D14).
- :func:`agent_performance`: los últimos ``days`` días, en total y por día **de la
  zona del cliente**: conversaciones, cuántas pasaron a una persona, cuántas se
  resolvieron sin persona y el gasto.
- :func:`agent_conversations`: la lista, de la más reciente a la más antigua,
  con fecha, canal, duración, número de mensajes, resultado, motivo del traspaso
  y gasto.

**Un ciclo** (``research.md`` R1): una fila de ``conversations`` es un contacto en
un número y se reabre. El ciclo empieza al crearse la fila o cuando el contacto o
un aviso la reabren, y acaba en la siguiente resolución (a mano o por
inactividad). Si la reabre una persona, deshace la resolución: el mismo ciclo
(spec 064, 4.4). Cuenta como conversación solo si el contacto escribió en él, y
es del día de su primer mensaje del contacto.

**Con persona, por historial** (R3): un escalado (del agente o de una puerta), un
takeover (Bandeja, panel de operador o una persona que escribe) o un freno de
reservas dentro del ciclo. No el estado de hoy: lo que se tomó y se devolvió
también pasó por una persona.

**Nada sale de un texto.** Las consultas cuentan filas, leen horas y suman
importes; ninguna proyecta ``messages.content``, el motivo libre de un escalado
ni un dato del cliente final (C1 y C8).

**El gasto es a precio, nunca a coste (C9)**: lo medido en la partida
Conversaciones (``usage_records.source = channel``) por 2,2, en cien milésimas de
US$, como el precio real de la pantalla Calidad.

Todo dentro de la transacción del cliente (RLS).
"""

from __future__ import annotations

import base64
import uuid
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import (
    AuditLog,
    Channel,
    Conversation,
    ConversationEvent,
    ConversationStatus,
    Message,
    MessageDirection,
    MessageStatus,
    Tenant,
    UsageRecord,
)
from nexus_api.db.models.conversation import WAITING_REASONS
from nexus_api.services.agents import principal_agent_id
from nexus_api.services.console_traffic import customer_facing_channel
from nexus_api.services.wallet.usage_lines import PRICE_MULTIPLIER, UNITS

DEFAULT_DAYS: Final = 30
MAX_DAYS: Final = 90
#: La medición de las conversaciones (la partida que paga la bolsa del cliente).
CHANNEL_SOURCE: Final = "channel"

#: Spec 083 (R3): lo que deja una persona en el historial de una conversación.
HANDOFF_EVENTS: Final = ("escalated", "takeover")
#: La Bandeja (que además deja el evento ``takeover``) y el panel de operador.
TAKEOVER_AUDITS: Final = ("inbox.takeover", "conversation.takeover")
#: El freno de reservas (spec 056, ``runtime/booking_brake.AUDIT_ACTION``).
BRAKE_AUDIT: Final = "agent.booking_brake"
HANDOFF_AUDITS: Final = (*TAKEOVER_AUDITS, BRAKE_AUDIT)
#: Quién escribe como persona del negocio (R2): la Bandeja, el panel, el dueño…
PERSON_ACTORS: Final = ("member", "operator", "owner")
#: …y lo que la plataforma marca como suyo, el eco de la app incluido.
PERSON_ORIGINS: Final = ("business_person", "business_app_echo")
#: Un envío es lo que el proveedor aceptó.
SENT_STATUSES: Final = (MessageStatus.SENT, MessageStatus.DELIVERED, MessageStatus.READ)
#: El ``target`` de una auditoría de conversación.
TARGET_PREFIX: Final = "conversation:"
CYCLE_EVENTS: Final = ("resolved", "reopened")
#: Spec 083 (D15): el eco de la app del negocio guarda la hora de Meta, y la fila
#: o la reapertura que provoca, la de la plataforma, unos segundos después. Una
#: señal de persona en este margen antes de que empiece un ciclo (y fuera del
#: anterior) es de ese ciclo.
SIGNAL_SLACK: Final = timedelta(minutes=10)

#: Los códigos de una puerta que el motivo de una incidencia dice tal cual (R4):
#: los de ``WAITING_REASONS`` salvo los que no son una espera.
GATE_CAUSES: Final = frozenset(WAITING_REASONS) - {"escalated", "human_takeover", "out_of_audience"}


class CursorInvalid(ValueError):
    """El cursor de la lista no es uno que diera esta API."""


# ── la zona del cliente ────────────────────────────────────────────────────


def zone_of(name: str | None) -> ZoneInfo:
    """La zona de un nombre; uno que no vale es UTC, como la agenda."""
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


async def client_zone(session: AsyncSession) -> ZoneInfo:
    """La zona del cliente del contexto (``tenants.timezone``)."""
    tenant = await session.get(Tenant, require_current_tenant())
    return zone_of(tenant.timezone if tenant is not None else None)


def local_day(at: datetime, zone: ZoneInfo) -> date:
    return at.astimezone(zone).date()


def local_midnight(day: date, zone: ZoneInfo) -> datetime:
    """El principio de ``day`` en la zona, en UTC."""
    return datetime.combine(day, time.min, zone).astimezone(UTC)


def _local_day_sql(column: Any, zone: ZoneInfo) -> sa.ColumnElement[date]:
    # ``zone.key`` sale de ``zone_of``: un nombre que ``ZoneInfo`` ya aceptó.
    return sa.cast(sa.func.timezone(zone.key, column), sa.Date)


# ── qué mensaje es de quién (R2) ───────────────────────────────────────────


def contact_wrote() -> sa.ColumnElement[bool]:
    """Un mensaje del contacto; lo importado del historial no es del periodo."""
    return sa.and_(
        Message.direction == MessageDirection.INBOUND,
        sa.or_(Message.origin.is_(None), Message.origin == "customer"),
    )


def agent_sent() -> sa.ColumnElement[bool]:
    """Un mensaje del agente que el proveedor aceptó; no las plantillas del sistema."""
    return sa.and_(
        Message.direction == MessageDirection.OUTBOUND,
        Message.actor_kind == "agent",
        Message.status.in_(SENT_STATUSES),
    )


def person_wrote() -> sa.ColumnElement[bool]:
    """Una persona del negocio escribió (Bandeja, panel o la app en coexistencia)."""
    return sa.and_(
        Message.direction == MessageDirection.OUTBOUND,
        sa.or_(Message.actor_kind.in_(PERSON_ACTORS), Message.origin.in_(PERSON_ORIGINS)),
    )


def _conversation_target() -> sa.ColumnElement[str]:
    return sa.func.concat(TARGET_PREFIX, sa.cast(Conversation.id, sa.Text))


def handed_to_person() -> sa.ColumnElement[bool]:
    """«Pasada a una persona» **por historial** (spec 083, requisito 3): en algún
    momento de la vida de la fila hubo un escalado, un takeover o un freno. Una
    expresión sobre ``Conversation``, para la lista y las sugerencias."""
    return sa.or_(
        sa.exists().where(
            ConversationEvent.conversation_id == Conversation.id,
            ConversationEvent.kind.in_(HANDOFF_EVENTS),
        ),
        sa.exists().where(
            AuditLog.action.in_(HANDOFF_AUDITS),
            AuditLog.target == _conversation_target(),
        ),
        sa.exists().where(Message.conversation_id == Conversation.id, person_wrote()),
    )


def conversation_owner() -> sa.ColumnElement[Any]:
    """El agente de la conversación: al que la derivó Recepción o el de su número."""
    return sa.func.coalesce(Conversation.handled_by_agent_id, Channel.agent_id)


async def _is_principal(session: AsyncSession, agent_id: uuid.UUID) -> bool:
    return await principal_agent_id(session) == agent_id


def _mine(agent_id: uuid.UUID, *, principal: bool) -> sa.ColumnElement[bool]:
    owner = conversation_owner()
    return sa.or_(owner == agent_id, owner.is_(None)) if principal else owner == agent_id


def _spend_of(agent_id: uuid.UUID, *, principal: bool) -> sa.ColumnElement[bool]:
    mine = UsageRecord.agent_id == agent_id
    return sa.or_(mine, UsageRecord.agent_id.is_(None)) if principal else mine


def price_micros(cost_usd: Any) -> int:
    """Coste del modelo (US$) → precio en cien milésimas de US$."""
    return int((Decimal(str(cost_usd or 0)) * PRICE_MULTIPLIER * UNITS).to_integral_value())


# ── los ciclos, puros (R1) ─────────────────────────────────────────────────


@dataclass(frozen=True)
class Span:
    """Un tramo de una fila: de su apertura a su resolución (``None``: abierto)."""

    start: datetime
    end: datetime | None

    def holds(self, at: datetime) -> bool:
        return self.start <= at and (self.end is None or at < self.end)


def owns_signal(spans: Sequence[Span], index: int, at: datetime) -> bool:
    """La señal de persona ``at`` es del ciclo ``spans[index]``: cae dentro o, como
    mucho :data:`SIGNAL_SLACK` antes de que empiece, fuera del ciclo anterior (D15)."""
    span = spans[index]
    if span.holds(at):
        return True
    if not span.start - SIGNAL_SLACK <= at < span.start:
        return False
    previous = spans[index - 1] if index else None
    return previous is None or not previous.holds(at)


def _by_person(actor: str) -> bool:
    """Como ``inbox_lifecycle._is_person``: una persona lleva su cuenta en el actor."""
    return ":" in actor


def build_spans(created_at: datetime, events: Iterable[tuple[datetime, str, str]]) -> list[Span]:
    """Los ciclos de una fila con sus ``resolved`` y ``reopened`` (``(hora, tipo,
    actor)``, en cualquier orden). Reabrir el contacto o un aviso empieza un ciclo;
    reabrir una persona deshace la resolución (D3)."""
    spans: list[list[datetime | None]] = [[created_at, None]]
    for at, kind, actor in sorted(events, key=lambda e: e[0]):
        last = spans[-1]
        if kind == "resolved":
            if last[1] is None:
                last[1] = at
        elif kind == "reopened":
            if _by_person(actor):
                last[1] = None
            else:
                if last[1] is None:
                    last[1] = at
                spans.append([at, None])
    return [Span(start, end) for start, end in spans if start is not None]


@dataclass(frozen=True)
class Send:
    """Un envío del agente: cuándo se creó y cuánto tardó el proveedor en aceptarlo."""

    created_at: datetime
    delivery: timedelta

    @property
    def accepted_at(self) -> datetime:
        return self.created_at + self.delivery


@dataclass(frozen=True)
class Cycle:
    """Una conversación del periodo (spec 083, requisito 2)."""

    conversation_id: uuid.UUID
    start: datetime
    end: datetime | None
    first_contact_at: datetime
    day: date
    with_person: bool
    #: Del primer mensaje del contacto al primer envío del agente; ``None`` sin envío.
    first_reply_seconds: float | None


def assemble_cycles(
    *,
    spans: Mapping[uuid.UUID, Sequence[Span]],
    contact_times: Mapping[uuid.UUID, Sequence[datetime]],
    contact_before: Mapping[uuid.UUID, datetime],
    agent_sends: Mapping[uuid.UUID, Sequence[Send]],
    person_signals: Mapping[uuid.UUID, Sequence[datetime]],
    zone: ZoneInfo,
) -> list[Cycle]:
    """Los ciclos del periodo: los que tienen un mensaje del contacto en él
    (``contact_times``) y ninguno antes (``contact_before``: el último anterior al
    periodo), en orden de su primer mensaje."""
    out: list[Cycle] = []
    for conv, conv_spans in spans.items():
        times = sorted(contact_times.get(conv, ()))
        before = contact_before.get(conv)
        sends = sorted(agent_sends.get(conv, ()), key=lambda s: s.created_at)
        signals = person_signals.get(conv, ())
        for index, span in enumerate(conv_spans):
            inside = [t for t in times if span.holds(t)]
            if not inside or (before is not None and span.holds(before)):
                continue
            first = inside[0]
            reply = next(
                (s for s in sends if s.created_at >= first and span.holds(s.created_at)), None
            )
            out.append(
                Cycle(
                    conversation_id=conv,
                    start=span.start,
                    end=span.end,
                    first_contact_at=first,
                    day=local_day(first, zone),
                    with_person=any(owns_signal(conv_spans, index, t) for t in signals),
                    first_reply_seconds=(reply.accepted_at - first).total_seconds()
                    if reply is not None
                    else None,
                )
            )
    out.sort(key=lambda c: (c.first_contact_at, c.conversation_id))
    return out


# ── las incidencias, puras (R4) ────────────────────────────────────────────


def escalation_cause(actor: str, reason: str | None) -> str:
    """El motivo de un escalado como código (D7). El del agente es texto libre del
    modelo y nunca sale: es «el agente pidió una persona» (``escalated``)."""
    if actor == "agent" or reason == "escalated":
        return "escalated"
    if reason is not None and reason in GATE_CAUSES:
        return reason
    return "other"


@dataclass(frozen=True)
class Incident:
    conversation_id: uuid.UUID
    at: datetime
    cause: str
    #: Cuándo se resolvió la conversación en ese ciclo; ``None``: sigue abierta.
    resolved_at: datetime | None


def assemble_incidents(
    *,
    escalations: Iterable[tuple[uuid.UUID, datetime, str, str | None]],
    brakes: Iterable[tuple[uuid.UUID, datetime, str | None]],
    spans: Mapping[uuid.UUID, Sequence[Span]],
) -> list[Incident]:
    """Cada escalado (``(conversación, hora, actor, motivo)``) y cada freno que no
    pasó la conversación (``(conversación, hora, resultado)``): el que la pasó ya
    es su escalado ``booking_unbacked`` (D6). De la más reciente a la más antigua."""
    found = [(conv, at, escalation_cause(actor, reason)) for conv, at, actor, reason in escalations]
    found += [
        (conv, at, "booking_brake") for conv, at, outcome in brakes if outcome != "handed_off"
    ]
    out: list[Incident] = []
    for conv, at, cause in found:
        span = next((s for s in spans.get(conv, ()) if s.holds(at)), None)
        out.append(Incident(conv, at, cause, span.end if span is not None else None))
    out.sort(key=lambda i: (i.at, i.conversation_id), reverse=True)
    return out


# ── los ciclos, de la base ─────────────────────────────────────────────────


def target_id(target: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(target.removeprefix(TARGET_PREFIX))
    except ValueError:
        return None


async def load_spans(
    session: AsyncSession, conversation_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[Span]]:
    """Los ciclos de cada fila, con su ``created_at`` y sus eventos de ciclo."""
    if not conversation_ids:
        return {}
    created = dict(
        (
            await session.execute(
                sa.select(Conversation.id, Conversation.created_at).where(
                    Conversation.id.in_(conversation_ids)
                )
            )
        )
        .tuples()
        .all()
    )
    events: dict[uuid.UUID, list[tuple[datetime, str, str]]] = defaultdict(list)
    for cid, at, kind, actor in (
        await session.execute(
            sa.select(
                ConversationEvent.conversation_id,
                ConversationEvent.created_at,
                ConversationEvent.kind,
                ConversationEvent.actor,
            ).where(
                ConversationEvent.conversation_id.in_(conversation_ids),
                ConversationEvent.kind.in_(CYCLE_EVENTS),
            )
        )
    ).tuples():
        events[cid].append((at, kind, actor))
    return {cid: build_spans(at, events.get(cid, ())) for cid, at in created.items()}


async def person_signals(
    session: AsyncSession, conversation_ids: Sequence[uuid.UUID], *, since: datetime
) -> dict[uuid.UUID, list[datetime]]:
    """Las horas de las señales de persona de cada fila desde ``since`` (R3)."""
    out: dict[uuid.UUID, list[datetime]] = defaultdict(list)
    if not conversation_ids:
        return out
    for cid, at in (
        await session.execute(
            sa.select(ConversationEvent.conversation_id, ConversationEvent.created_at).where(
                ConversationEvent.conversation_id.in_(conversation_ids),
                ConversationEvent.kind.in_(HANDOFF_EVENTS),
                ConversationEvent.created_at >= since,
            )
        )
    ).tuples():
        out[cid].append(at)
    targets = [f"{TARGET_PREFIX}{cid}" for cid in conversation_ids]
    for target, at in (
        await session.execute(
            sa.select(AuditLog.target, AuditLog.created_at).where(
                AuditLog.action.in_(HANDOFF_AUDITS),
                AuditLog.target.in_(targets),
                AuditLog.created_at >= since,
            )
        )
    ).tuples():
        audited = target_id(target)
        if audited is not None:
            out[audited].append(at)
    for cid, at in (
        await session.execute(
            sa.select(Message.conversation_id, Message.created_at).where(
                Message.conversation_id.in_(conversation_ids),
                person_wrote(),
                Message.created_at >= since,
            )
        )
    ).tuples():
        out[cid].append(at)
    return out


async def period_cycles(
    session: AsyncSession,
    *,
    since: datetime,
    until: datetime,
    zone: ZoneInfo,
    agent_id: uuid.UUID | None = None,
) -> list[Cycle]:
    """Las conversaciones de ``[since, until)``: los ciclos cuyo primer mensaje del
    contacto cae en el periodo, de los canales de clientes (el Playground no) y,
    con ``agent_id``, solo las de ese agente (la regla de siempre)."""
    stmt = (
        sa.select(Message.conversation_id, Message.created_at)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .join(Channel, Channel.id == Conversation.channel_id)
        .where(
            customer_facing_channel(),
            contact_wrote(),
            Message.created_at >= since,
            Message.created_at < until,
        )
    )
    if agent_id is not None:
        stmt = stmt.where(_mine(agent_id, principal=await _is_principal(session, agent_id)))
    contact_times: dict[uuid.UUID, list[datetime]] = defaultdict(list)
    for cid, at in (await session.execute(stmt)).tuples():
        contact_times[cid].append(at)
    ids = list(contact_times)
    if not ids:
        return []
    spans = await load_spans(session, ids)
    contact_before = dict(
        (
            await session.execute(
                sa.select(Message.conversation_id, sa.func.max(Message.created_at))
                .where(
                    Message.conversation_id.in_(ids), contact_wrote(), Message.created_at < since
                )
                .group_by(Message.conversation_id)
            )
        )
        .tuples()
        .all()
    )
    first_any = min(min(times) for times in contact_times.values())
    sends: dict[uuid.UUID, list[Send]] = defaultdict(list)
    for cid, at, latency in (
        await session.execute(
            sa.select(Message.conversation_id, Message.created_at, Message.latency_ms).where(
                Message.conversation_id.in_(ids), agent_sent(), Message.created_at >= first_any
            )
        )
    ).tuples():
        sends[cid].append(Send(at, timedelta(milliseconds=max(0, latency or 0))))
    floor = min(
        (
            span.start - SIGNAL_SLACK
            for cid, conv_spans in spans.items()
            for span in conv_spans
            if any(span.holds(t) for t in contact_times[cid])
        ),
        default=since,
    )
    signals = await person_signals(session, ids, since=floor)
    return assemble_cycles(
        spans=spans,
        contact_times=contact_times,
        contact_before=contact_before,
        agent_sends=sends,
        person_signals=signals,
        zone=zone,
    )


# ── el rendimiento ─────────────────────────────────────────────────────────


@dataclass
class DayFigures:
    day: date
    conversations: int = 0
    handed_to_person: int = 0
    spent_micros: int = 0

    @property
    def resolved_without_person(self) -> int:
        return max(0, self.conversations - self.handed_to_person)


@dataclass
class Performance:
    days: int
    since: datetime
    until: datetime
    series: list[DayFigures] = field(default_factory=list)

    @property
    def conversations(self) -> int:
        return sum(d.conversations for d in self.series)

    @property
    def handed_to_person(self) -> int:
        return sum(d.handed_to_person for d in self.series)

    @property
    def resolved_without_person(self) -> int:
        return max(0, self.conversations - self.handed_to_person)

    @property
    def resolved_pct(self) -> float | None:
        total = self.conversations
        return round(self.resolved_without_person / total * 100, 1) if total else None

    @property
    def spent_micros(self) -> int:
        return sum(d.spent_micros for d in self.series)

    @property
    def spend_per_conversation_micros(self) -> int | None:
        total = self.conversations
        return round(self.spent_micros / total) if total else None


async def agent_performance(
    session: AsyncSession,
    agent_id: uuid.UUID,
    *,
    days: int = DEFAULT_DAYS,
    now: datetime | None = None,
) -> Performance:
    """Los últimos ``days`` días del agente, hoy incluido, día a día en la zona del
    cliente, con los ciclos del informe (spec 083, requisito 9)."""
    now = now or datetime.now(UTC)
    days = max(1, min(days, MAX_DAYS))
    zone = await client_zone(session)
    first = local_day(now, zone) - timedelta(days=days - 1)
    since = local_midnight(first, zone)
    out = Performance(days=days, since=since, until=now)
    by_day = {first + timedelta(days=i): DayFigures(first + timedelta(days=i)) for i in range(days)}
    principal = await _is_principal(session, agent_id)

    for cycle in await period_cycles(
        session, since=since, until=now + timedelta(microseconds=1), zone=zone, agent_id=agent_id
    ):
        if cycle.day in by_day:
            by_day[cycle.day].conversations += 1
            by_day[cycle.day].handed_to_person += int(cycle.with_person)

    spent_day = _local_day_sql(UsageRecord.occurred_at, zone)
    for d, cost in (
        await session.execute(
            sa.select(spent_day, sa.func.sum(UsageRecord.cost_usd))
            .where(
                UsageRecord.source == CHANNEL_SOURCE,
                _spend_of(agent_id, principal=principal),
                UsageRecord.occurred_at >= since,
                UsageRecord.occurred_at <= now,
            )
            .group_by(spent_day)
        )
    ).all():
        if d in by_day:
            by_day[d].spent_micros += price_micros(cost)
    out.series = [by_day[d] for d in sorted(by_day)]
    return out


# ── la lista de conversaciones ─────────────────────────────────────────────


@dataclass(frozen=True)
class ConversationFacts:
    """Lo que se sabe de una conversación sin leerla."""

    id: uuid.UUID
    started_at: datetime
    last_activity_at: datetime
    channel_type: str | None
    messages_count: int
    duration_seconds: int | None
    handed_to_person: bool
    in_progress: bool
    handoff_reason: str | None
    spent_micros: int | None


def encode_cursor(at: datetime, conversation_id: uuid.UUID) -> str:
    raw = f"{at.isoformat()}|{conversation_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        at, cid = base64.urlsafe_b64decode(padded.encode()).decode().split("|", 1)
        return datetime.fromisoformat(at), uuid.UUID(cid)
    except Exception as exc:
        raise CursorInvalid(cursor) from exc


def _handoff_reason(handed: bool, last_escalation: tuple[str, str | None] | None) -> str | None:
    """Un código, nunca un texto: la consola pone las palabras. El del último
    escalado de su historial (``escalated`` si lo pidió el agente) o, sin
    escalado, ``taken_by_person``."""
    if not handed:
        return None
    if last_escalation is None:
        return "taken_by_person"
    cause = escalation_cause(*last_escalation)
    return "escalated" if cause == "other" else cause


async def _last_escalations(
    session: AsyncSession, ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, tuple[str, str | None]]:
    if not ids:
        return {}
    ranked = (
        sa.select(
            ConversationEvent.conversation_id,
            ConversationEvent.actor,
            ConversationEvent.payload["reason"].astext.label("reason"),
            sa.func.row_number()
            .over(
                partition_by=ConversationEvent.conversation_id,
                order_by=ConversationEvent.created_at.desc(),
            )
            .label("n"),
        )
        .where(
            ConversationEvent.conversation_id.in_(ids),
            ConversationEvent.kind == "escalated",
        )
        .subquery()
    )
    rows = await session.execute(
        sa.select(ranked.c.conversation_id, ranked.c.actor, ranked.c.reason).where(ranked.c.n == 1)
    )
    return {cid: (actor, reason) for cid, actor, reason in rows.tuples()}


async def agent_conversations(
    session: AsyncSession,
    agent_id: uuid.UUID,
    *,
    limit: int = 50,
    cursor: str | None = None,
) -> tuple[list[ConversationFacts], str | None]:
    """Una página de conversaciones del agente y el cursor de la siguiente."""
    principal = await _is_principal(session, agent_id)
    handed = handed_to_person().label("handed")
    stmt = (
        sa.select(Conversation, Channel.type.label("channel_type"), handed)
        .join(Channel, Channel.id == Conversation.channel_id)
        .where(customer_facing_channel(), _mine(agent_id, principal=principal))
    )
    if cursor:
        at, cid = decode_cursor(cursor)
        stmt = stmt.where(
            sa.tuple_(Conversation.created_at, Conversation.id)
            < sa.tuple_(sa.literal(at, sa.DateTime(timezone=True)), sa.literal(cid, sa.Uuid()))
        )
    rows = (
        await session.execute(
            stmt.order_by(Conversation.created_at.desc(), Conversation.id.desc()).limit(limit + 1)
        )
    ).all()
    more = len(rows) > limit
    rows = rows[:limit]
    ids = [row[0].id for row in rows]

    stats: dict[uuid.UUID, tuple[int, datetime | None, datetime | None]] = {}
    spent: dict[uuid.UUID, int] = defaultdict(int)
    if ids:
        for cid, count, first_at, last_at in (
            await session.execute(
                sa.select(
                    Message.conversation_id,
                    sa.func.count(Message.id),
                    sa.func.min(Message.created_at),
                    sa.func.max(Message.created_at),
                )
                .where(Message.conversation_id.in_(ids))
                .group_by(Message.conversation_id)
            )
        ).all():
            stats[cid] = (int(count), first_at, last_at)
        for cid, cost in (
            await session.execute(
                sa.select(UsageRecord.conversation_id, sa.func.sum(UsageRecord.cost_usd))
                .where(
                    UsageRecord.source == CHANNEL_SOURCE,
                    UsageRecord.conversation_id.in_(ids),
                )
                .group_by(UsageRecord.conversation_id)
            )
        ).all():
            if cid is not None and cost is not None:
                spent[cid] += price_micros(cost)
    escalations = await _last_escalations(session, [row[0].id for row in rows if row.handed])

    items: list[ConversationFacts] = []
    for row in rows:
        conv: Conversation = row[0]
        count, first_at, last_at = stats.get(conv.id, (0, None, None))
        was_handed = bool(row.handed)
        items.append(
            ConversationFacts(
                id=conv.id,
                started_at=conv.created_at,
                last_activity_at=last_at or conv.last_message_at or conv.updated_at,
                channel_type=row.channel_type.value if row.channel_type is not None else None,
                messages_count=count,
                duration_seconds=int((last_at - first_at).total_seconds())
                if first_at and last_at
                else None,
                handed_to_person=was_handed,
                in_progress=conv.status == ConversationStatus.OPEN,
                handoff_reason=_handoff_reason(was_handed, escalations.get(conv.id)),
                spent_micros=spent.get(conv.id),
            )
        )
    next_cursor = encode_cursor(rows[-1][0].created_at, rows[-1][0].id) if more and rows else None
    return items, next_cursor


__all__ = [
    "BRAKE_AUDIT",
    "DEFAULT_DAYS",
    "MAX_DAYS",
    "SIGNAL_SLACK",
    "ConversationFacts",
    "CursorInvalid",
    "Cycle",
    "DayFigures",
    "Incident",
    "Performance",
    "Send",
    "Span",
    "agent_conversations",
    "agent_performance",
    "agent_sent",
    "assemble_cycles",
    "assemble_incidents",
    "build_spans",
    "client_zone",
    "contact_wrote",
    "conversation_owner",
    "decode_cursor",
    "encode_cursor",
    "escalation_cause",
    "handed_to_person",
    "load_spans",
    "local_day",
    "local_midnight",
    "owns_signal",
    "period_cycles",
    "person_signals",
    "person_wrote",
    "price_micros",
    "target_id",
    "zone_of",
]
