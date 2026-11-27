"""El informe de un cliente para unas fechas — spec 083.

Lo que un partner enseña a su cliente al cerrar un piloto, con las reglas de la
spec (``specs/083-informe-del-piloto``, D1 a D14):

- **conversaciones** y **primera respuesta**: los ciclos de
  ``improvement.performance.period_cycles``, los mismos de la página Rendimiento;
- **incidencias**: cada escalado del periodo (su motivo, un código) y cada freno
  de reservas que no pasó la conversación; resueltas si su ciclo se resolvió;
- **freno de reservas**: cuántas veces paró una respuesta y cómo acabó;
- **agenda** y **recordatorios**, solo si el cliente tiene Reservas;
- **gasto**: la fila del cliente en Consumo (``usage_lines.spend``), en su propia
  sesión: si no se puede leer, el resto sale igual (estado parcial).

Los días son los del calendario del cliente (``tenants.timezone``). Todo lo que
no es el gasto se lee en la transacción del cliente (RLS, garantía 1). Ninguna
consulta proyecta un cuerpo de mensaje, el texto libre de un escalado ni un dato
del cliente final (C8).
"""

from __future__ import annotations

import math
import statistics
import uuid
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Final
from zoneinfo import ZoneInfo

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AuditLog,
    Channel,
    ClientAccess,
    ClientModule,
    Conversation,
    ConversationEvent,
    ReservationEvent,
    ReservationOutbox,
    ReservationSettings,
    Tenant,
)
from nexus_api.services.console_traffic import customer_facing_channel
from nexus_api.services.improvement import performance as perf
from nexus_api.services.reservations.automation import SKIP_STALE
from nexus_api.services.wallet import usage_lines

log = structlog.get_logger(__name__)

#: D13: un trimestre cubre cualquier piloto.
MAX_DAYS: Final = 92
#: Los objetivos del piloto (spec, Supuestos).
WITHOUT_PERSON_TARGET_PCT: Final = 70
FIRST_RESPONSE_TARGET_PCT: Final = 95
FIRST_RESPONSE_TARGET_SECONDS: Final = 60
#: Las incidencias que la lista enseña; el recuento las cuenta todas.
INCIDENT_LIST_LIMIT: Final = 100
#: Las partidas de la bolsa del cliente: la fila del cliente en Consumo.
BAG_LINES: Final = ("conversations", "client_tests")

#: Quién hizo una operación de agenda.
WHO: Final = ("agent", "person", "customer")
AGENDA_KINDS: Final = ("created", "moved", "cancelled")
#: Aceptar una oferta de la lista de espera con una reserva viva la mueve
#: (``move_booking(event="waitlist_accepted")``, sin ``moved``): es una movida. Sin
#: reserva, la crea y deja ``created`` y ``waitlist_accepted`` en la misma
#: transacción, con la misma hora: es un alta, ya contada.
WAITLIST_ACCEPTED: Final = "waitlist_accepted"
#: El «no» a la confirmación va en la misma transacción que su cancelación (D11).
REPLIED_NO_WINDOW: Final = timedelta(seconds=60)
REMINDER_KINDS: Final = ("reminder", "ask_confirmation")
FINAL_OUTBOX: Final = ("sent", "failed", "skipped")


class PeriodInvalid(ValueError):
    """El periodo no se puede pedir: ``code`` es el de la API."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def period_window(
    day_from: date, day_to: date, zone: ZoneInfo, now: datetime
) -> tuple[datetime, datetime]:
    """``[since, until)`` en UTC: de la medianoche local de ``day_from`` a la del
    día siguiente a ``day_to`` o, si ``day_to`` es hoy, hasta ahora."""
    if day_to < day_from:
        raise PeriodInvalid("range_reversed")
    if (day_to - day_from).days + 1 > MAX_DAYS:
        raise PeriodInvalid("range_too_long")
    if day_to > perf.local_day(now, zone):
        raise PeriodInvalid("range_in_future")
    since = perf.local_midnight(day_from, zone)
    until = min(perf.local_midnight(day_to + timedelta(days=1), zone), now)
    return since, until


# ── la agenda, pura (D10, D11) ─────────────────────────────────────────────


@dataclass(frozen=True)
class AgendaEvent:
    reservation_id: uuid.UUID
    kind: str
    actor_kind: str
    actor_name: str | None
    at: datetime


@dataclass
class AgendaCounts:
    created: dict[str, int]
    moved: dict[str, int]
    cancelled: dict[str, int]
    #: Las reservas sin confirmar que se liberaron solas.
    released: int


def _blank() -> dict[str, int]:
    return {**dict.fromkeys(WHO, 0), "total": 0}


def agenda_counts(
    events: Iterable[AgendaEvent], *, replied_no: Mapping[uuid.UUID, Sequence[datetime]]
) -> AgendaCounts:
    """Quién creó, movió y canceló. Las cancelaciones del sistema son liberaciones;
    sus altas, la importación «Paso a Reservas», que no cuenta. Una cancelación de
    «cliente» sin su «contestó que no» la hizo el agente (``reservas.cancel`` la
    graba como del cliente hasta la spec 080). Aceptar una oferta de la lista de
    espera con una reserva viva es una movida (``WAITLIST_ACCEPTED``)."""
    counts = {kind: _blank() for kind in AGENDA_KINDS}
    released = 0
    events = list(events)
    made = {(e.reservation_id, e.at) for e in events if e.kind == "created"}
    for event in events:
        who = event.actor_kind
        kind = event.kind
        if kind == WAITLIST_ACCEPTED:
            if (event.reservation_id, event.at) in made:
                continue
            kind = "moved"
        if kind == "cancelled":
            if who == "system":
                released += 1
                continue
            if who == "customer" and not any(
                event.at - REPLIED_NO_WINDOW <= t <= event.at
                for t in replied_no.get(event.reservation_id, ())
            ):
                who = "agent"
        if kind not in counts or who not in WHO:
            continue
        counts[kind][who] += 1
        counts[kind]["total"] += 1
    return AgendaCounts(
        created=counts["created"],
        moved=counts["moved"],
        cancelled=counts["cancelled"],
        released=released,
    )


# ── el informe ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DayRow:
    day: date
    without_person: int
    with_person: int


@dataclass(frozen=True)
class HourRow:
    #: La hora local del primer mensaje del contacto, de 0 a 23.
    hour: int
    without_person: int
    with_person: int


@dataclass(frozen=True)
class WeekdayRow:
    #: ISO: 1 es lunes y 7, domingo.
    weekday: int
    without_person: int
    with_person: int


@dataclass(frozen=True)
class Conversations:
    total: int
    without_person: int
    with_person: int
    without_person_pct: float | None
    series: list[DayRow]
    #: Enmienda 2026-11-27 (13.1): cuándo escriben, para cubrir esas horas.
    by_hour: list[HourRow]
    by_weekday: list[WeekdayRow]


@dataclass(frozen=True)
class FirstResponse:
    answered: int
    within_target: int
    within_target_pct: float | None
    median_seconds: int | None
    p90_seconds: int | None
    unanswered: int


@dataclass(frozen=True)
class CauseRow:
    cause: str
    total: int
    resolved: int


@dataclass(frozen=True)
class IncidentRow:
    at: datetime
    cause: str
    resolved_at: datetime | None


@dataclass(frozen=True)
class Incidents:
    total: int
    resolved: int
    open: int
    by_cause: list[CauseRow]
    items: list[IncidentRow]
    truncated: bool


@dataclass(frozen=True)
class BookingBrake:
    stopped: int
    corrected: int
    handed_over: int


@dataclass(frozen=True)
class ReminderRow:
    kind: str
    sent: int
    failed: int
    skipped: int


@dataclass(frozen=True)
class Agenda:
    created: dict[str, int]
    moved: dict[str, int]
    cancelled: dict[str, int]
    released: int
    reminders: list[ReminderRow]


@dataclass(frozen=True)
class Money:
    amount_micros: int
    currency: str


@dataclass(frozen=True)
class Spend:
    currency: str
    total: Money
    conversations: Money
    client_tests: Money
    meta: Money
    approx: bool
    per_conversation: Money | None


@dataclass(frozen=True)
class Targets:
    without_person_pct: int = WITHOUT_PERSON_TARGET_PCT
    first_response_pct: int = FIRST_RESPONSE_TARGET_PCT
    first_response_seconds: int = FIRST_RESPONSE_TARGET_SECONDS


@dataclass(frozen=True)
class ClientReport:
    day_from: date
    day_to: date
    timezone: str
    since: datetime
    until: datetime
    generated_at: datetime
    autoclose: bool
    conversations: Conversations
    first_response: FirstResponse
    incidents: Incidents
    booking_brake: BookingBrake
    agenda: Agenda | None
    spend: Spend | None
    targets: Targets = field(default_factory=Targets)


def _pct(part: int, whole: int) -> float | None:
    return round(part / whole * 100, 1) if whole else None


def _conversations(
    cycles: Sequence[perf.Cycle], day_from: date, day_to: date, zone: ZoneInfo
) -> Conversations:
    by_day: dict[date, list[int]] = {
        day_from + timedelta(days=i): [0, 0] for i in range((day_to - day_from).days + 1)
    }
    by_hour = [[0, 0] for _ in range(24)]
    by_weekday = [[0, 0] for _ in range(7)]
    for cycle in cycles:
        if cycle.day in by_day:
            column = 1 if cycle.with_person else 0
            by_day[cycle.day][column] += 1
            local = cycle.first_contact_at.astimezone(zone)
            by_hour[local.hour][column] += 1
            by_weekday[local.isoweekday() - 1][column] += 1
    without = sum(v[0] for v in by_day.values())
    with_person = sum(v[1] for v in by_day.values())
    total = without + with_person
    return Conversations(
        total=total,
        without_person=without,
        with_person=with_person,
        without_person_pct=_pct(without, total),
        series=[DayRow(d, v[0], v[1]) for d, v in sorted(by_day.items())],
        by_hour=[HourRow(hour, v[0], v[1]) for hour, v in enumerate(by_hour)],
        by_weekday=[WeekdayRow(i + 1, v[0], v[1]) for i, v in enumerate(by_weekday)],
    )


def _first_response(cycles: Sequence[perf.Cycle]) -> FirstResponse:
    seconds = sorted(c.first_reply_seconds for c in cycles if c.first_reply_seconds is not None)
    within = sum(1 for s in seconds if s <= FIRST_RESPONSE_TARGET_SECONDS)
    p90 = seconds[max(0, math.ceil(0.9 * len(seconds)) - 1)] if seconds else None
    return FirstResponse(
        answered=len(seconds),
        within_target=within,
        within_target_pct=_pct(within, len(seconds)),
        median_seconds=round(statistics.median(seconds)) if seconds else None,
        p90_seconds=round(p90) if p90 is not None else None,
        unanswered=len(cycles) - len(seconds),
    )


async def _incidents(
    session: AsyncSession, since: datetime, until: datetime
) -> tuple[Incidents, BookingBrake]:
    escalations = (
        await session.execute(
            sa.select(
                ConversationEvent.conversation_id,
                ConversationEvent.created_at,
                ConversationEvent.actor,
                ConversationEvent.payload["reason"].astext,
            )
            .join(Conversation, Conversation.id == ConversationEvent.conversation_id)
            .join(Channel, Channel.id == Conversation.channel_id)
            .where(
                customer_facing_channel(),
                ConversationEvent.kind == "escalated",
                ConversationEvent.created_at >= since,
                ConversationEvent.created_at < until,
            )
        )
    ).tuples()
    escalation_rows = list(escalations)
    brake_rows: list[tuple[uuid.UUID, datetime, str | None]] = []
    for target, at, outcome in (
        await session.execute(
            sa.select(
                AuditLog.target, AuditLog.created_at, AuditLog.after_json["outcome"].astext
            ).where(
                AuditLog.action == perf.BRAKE_AUDIT,
                AuditLog.target.startswith(perf.TARGET_PREFIX),
                AuditLog.created_at >= since,
                AuditLog.created_at < until,
            )
        )
    ).tuples():
        cid = perf.target_id(target)
        if cid is not None:
            brake_rows.append((cid, at, outcome))
    ids = list({row[0] for row in escalation_rows} | {row[0] for row in brake_rows})
    spans = await perf.load_spans(session, ids)
    found = perf.assemble_incidents(escalations=escalation_rows, brakes=brake_rows, spans=spans)

    totals: Counter[str] = Counter(i.cause for i in found)
    resolved: Counter[str] = Counter(i.cause for i in found if i.resolved_at is not None)
    done = sum(resolved.values())
    handed = sum(1 for row in brake_rows if row[2] == "handed_off")
    return (
        Incidents(
            total=len(found),
            resolved=done,
            open=len(found) - done,
            by_cause=[
                CauseRow(cause, n, resolved[cause])
                for cause, n in sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))
            ],
            items=[IncidentRow(i.at, i.cause, i.resolved_at) for i in found[:INCIDENT_LIST_LIMIT]],
            truncated=len(found) > INCIDENT_LIST_LIMIT,
        ),
        BookingBrake(
            stopped=len(brake_rows), corrected=len(brake_rows) - handed, handed_over=handed
        ),
    )


async def _agenda(
    session: AsyncSession, tenant_id: uuid.UUID, since: datetime, until: datetime
) -> Agenda | None:
    if await session.get(ReservationSettings, tenant_id) is None:
        return None
    events = [
        AgendaEvent(rid, kind, actor_kind, actor_name, at)
        for rid, kind, actor_kind, actor_name, at in (
            await session.execute(
                sa.select(
                    ReservationEvent.reservation_id,
                    ReservationEvent.kind,
                    ReservationEvent.actor_kind,
                    ReservationEvent.actor_name,
                    ReservationEvent.created_at,
                ).where(
                    ReservationEvent.kind.in_((*AGENDA_KINDS, WAITLIST_ACCEPTED)),
                    ReservationEvent.created_at >= since,
                    ReservationEvent.created_at < until,
                )
            )
        ).tuples()
    ]
    asked = [
        e.reservation_id for e in events if e.kind == "cancelled" and e.actor_kind == "customer"
    ]
    replied_no: dict[uuid.UUID, list[datetime]] = defaultdict(list)
    if asked:
        for rid, at in (
            await session.execute(
                sa.select(ReservationEvent.reservation_id, ReservationEvent.created_at).where(
                    ReservationEvent.reservation_id.in_(asked),
                    ReservationEvent.kind == "replied_no",
                    ReservationEvent.created_at >= since - REPLIED_NO_WINDOW,
                    ReservationEvent.created_at < until,
                )
            )
        ).tuples():
            replied_no[rid].append(at)
    counts = agenda_counts(events, replied_no=replied_no)

    reminders: dict[str, Counter[str]] = {kind: Counter() for kind in REMINDER_KINDS}
    for kind, state, n in (
        await session.execute(
            sa.select(ReservationOutbox.kind, ReservationOutbox.status, sa.func.count())
            .where(
                ReservationOutbox.kind.in_(REMINDER_KINDS),
                ReservationOutbox.status.in_(FINAL_OUTBOX),
                ReservationOutbox.updated_at >= since,
                ReservationOutbox.updated_at < until,
                # Un aviso que dejó de aplicar no es un fallo (``automation.mark_skipped``).
                sa.or_(
                    ReservationOutbox.status != "skipped",
                    ReservationOutbox.skip_reason.is_distinct_from(SKIP_STALE),
                ),
            )
            .group_by(ReservationOutbox.kind, ReservationOutbox.status)
        )
    ).tuples():
        reminders[kind][state] += int(n)
    return Agenda(
        created=counts.created,
        moved=counts.moved,
        cancelled=counts.cancelled,
        released=counts.released,
        reminders=[
            ReminderRow(kind, c["sent"], c["failed"], c["skipped"]) for kind, c in reminders.items()
        ],
    )


async def _autoclose(session: AsyncSession, tenant_id: uuid.UUID) -> bool:
    """El cliente cierra solas las conversaciones inactivas (spec 064)."""
    access = await session.get(ClientAccess, tenant_id)
    return bool(
        access is not None
        and access.inbox_autoclose_hours is not None
        and access.enabled
        and ClientModule.INBOX.value in (access.modules or [])
    )


async def _spend(
    *,
    partner_id: uuid.UUID,
    tenant_id: uuid.UUID,
    since: datetime,
    until: datetime,
    conversations: int,
) -> Spend | None:
    """La fila del cliente en Consumo para el periodo. En su sesión: ``spend`` abre
    sus transacciones, y la del cliente ya está abierta. Si falla, ``None``."""
    try:
        async with get_sessionmaker()() as reporting:
            found = await usage_lines.spend(
                reporting,
                partner_id=partner_id,
                tenant_ids=[tenant_id],
                since=since,
                until=until,
                with_outside=False,
                lines=(*BAG_LINES, "meta"),
            )
    except Exception as exc:
        log.warning("client_report.spend_unavailable", error=type(exc).__name__)
        return None
    currency = found.currency

    def money(lines: tuple[str, ...]) -> Money:
        return Money(found.total(lines=lines, tenant=tenant_id), currency)

    total = money(BAG_LINES)
    return Spend(
        currency=currency,
        total=total,
        conversations=money(("conversations",)),
        client_tests=money(("client_tests",)),
        meta=money(("meta",)),
        approx=bool(found.approx_lines & set(BAG_LINES)),
        per_conversation=Money(round(total.amount_micros / conversations), currency)
        if conversations
        else None,
    )


async def build_report(
    session: AsyncSession,
    *,
    tenant: Tenant,
    partner_id: uuid.UUID,
    day_from: date,
    day_to: date,
    now: datetime | None = None,
) -> ClientReport:
    """El informe del cliente del contexto. ``PeriodInvalid`` si las fechas no valen."""
    now = now or datetime.now(UTC)
    zone = perf.zone_of(tenant.timezone)
    since, until = period_window(day_from, day_to, zone, now)
    cycles = await perf.period_cycles(session, since=since, until=until, zone=zone)
    conversations = _conversations(cycles, day_from, day_to, zone)
    incidents, brake = await _incidents(session, since, until)
    agenda = await _agenda(session, tenant.id, since, until)
    autoclose = await _autoclose(session, tenant.id)
    spend = await _spend(
        partner_id=partner_id,
        tenant_id=tenant.id,
        since=since,
        until=until,
        conversations=conversations.total,
    )
    return ClientReport(
        day_from=day_from,
        day_to=day_to,
        timezone=zone.key,
        since=since,
        until=until,
        generated_at=now,
        autoclose=autoclose,
        conversations=conversations,
        first_response=_first_response(cycles),
        incidents=incidents,
        booking_brake=brake,
        agenda=agenda,
        spend=spend,
    )


__all__ = [
    "MAX_DAYS",
    "AgendaCounts",
    "AgendaEvent",
    "ClientReport",
    "PeriodInvalid",
    "agenda_counts",
    "build_report",
    "period_window",
]
