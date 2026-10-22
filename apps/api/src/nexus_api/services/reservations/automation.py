"""Reservas — lo que pasa solo (spec 043, Requisito 7).

Lo llaman los crons del worker (``reservations-cron``, ``reservation-offers-cron``
y ``reservation-outbox-cron``; ``contracts/worker-y-avisos.md``), siempre dentro
de la sesión **acotada al cliente** y con el ``now`` que les pasa el bucle: las
pruebas fijan el reloj. Aquí viven las reglas; en el worker, el bucle y el envío.

- **Pedir confirmación y recordar** a su hora, una sola vez por reserva y tipo
  (``ask:{id}:auto``, ``reminder:{id}``). Servicios, 24 h antes; Aforo, según
  ``confirm_when``. Solo a quien tiene a quién escribirle y solo si la reserva
  ya existía cuando tocaba preguntar: quien reservó dentro de esa ventana acaba
  de hablar con el negocio.
- **Liberar** (Aforo): la que sigue sin confirmar 1 h antes **y a la que se le
  preguntó de verdad** (su petición salió). «Sin respuesta» exige una pregunta.
- **Terminar**: Servicios, ``pending``/``confirmed`` tras su fin; Aforo,
  ``arrived`` tras su estancia. La confirmada que nunca llegó no se toca.
- **Avisos al cliente final**: el texto y la plantilla de cada ``kind`` con sus
  variables (``nombre``, ``negocio``, ``cuando``, ``detalle``, ``minutos``) y la
  contabilidad de la fila del outbox: ``sent``, ``skipped`` con su razón (y
  ``notify_failed`` en el historial), reintentos con espera y tope de 3.

Cada transición automática **comprueba el estado dentro del candado**
(``FOR UPDATE SKIP LOCKED``): lo que otra transacción tiene cogido se deja para
la próxima pasada.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import StatementError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import (
    Conversation,
    Customer,
    Reservation,
    ReservationOffer,
    ReservationOfferCandidate,
    ReservationOutbox,
    ReservationService,
    ReservationStaff,
    ReservationWaitlist,
)
from nexus_api.services.reservations import waitlist
from nexus_api.services.reservations.core import (
    SYSTEM,
    Ctx,
    add_event,
    cancel_booking,
    phone_digits,
)

#: Servicios (y Aforo con ``confirm_when = 24h``): 24 h antes.
DAY_BEFORE = timedelta(hours=24)
#: Aforo ``3h``, y el suelo de ``same_day_12`` para lo que empieza temprano.
THREE_HOURS = timedelta(hours=3)
NOON = time(12, 0)
#: Aforo: «sin respuesta 1 h antes, se cancela».
RELEASE_BEFORE = timedelta(hours=1)
#: Reservas que una pasada mira como mucho por regla (las siguientes, en la
#: próxima pasada: cada minuto).
BATCH = 200

#: La ventana de atención de WhatsApp: el cliente escribió en las últimas 24 h.
SERVICE_WINDOW = timedelta(hours=24)
OUTBOX_BATCH = 50
#: Espera antes del reintento n (1, 5, 15 min) y tope de intentos (data-model).
OUTBOX_BACKOFF: tuple[timedelta, ...] = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=15),
)
OUTBOX_MAX_ATTEMPTS = 3
TEMPLATE_LANGUAGE = "es"

#: Razones de ``skipped``. ``stale``: lo que se iba a decir ya no aplica (la
#: reserva se confirmó o se canceló antes de que saliera la pregunta); no es un
#: fallo de aviso y no deja ``notify_failed``.
SKIP_NO_PHONE = "no_phone"
SKIP_NO_TEMPLATE = "no_template"
SKIP_OPTED_OUT = "opted_out"
SKIP_NO_CHANNEL = "no_channel"
SKIP_STALE = "stale"


# ── pedir confirmación y recordar ───────────────────────────────────────────


def ask_at(ctx: Ctx, res: Reservation) -> datetime:
    """Cuándo toca la pregunta (o el recordatorio) de esta reserva."""
    if res.mode == "services":
        return res.starts_at - DAY_BEFORE
    when = ctx.settings.confirm_when
    if when == "3h":
        return res.starts_at - THREE_HOURS
    if when == "same_day_12":
        noon = ctx.at(ctx.local(res.starts_at).date(), NOON)
        # Lo que empieza antes de las 15:00 no se pregunta a mediodía (no
        # quedaría tiempo para responder antes de liberar): 3 h antes.
        return min(noon, res.starts_at - THREE_HOURS)
    return res.starts_at - DAY_BEFORE


def automatic_kind(ctx: Ctx, res: Reservation) -> str | None:
    """``ask_confirmation``, ``reminder`` o nada. Si se pide confirmación, ese
    mensaje ya recuerda: no van los dos."""
    s = ctx.settings
    if s.confirm_enabled and res.status == "pending":
        return "ask_confirmation"
    if res.mode == "services" and s.reminder_enabled and res.status in ("pending", "confirmed"):
        return "reminder"
    return None


def automatic_key(kind: str, reservation_id: uuid.UUID) -> str:
    if kind == "ask_confirmation":
        return f"ask:{reservation_id}:auto"
    return f"reminder:{reservation_id}"


async def enqueue_once(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    kind: str,
    dedupe_key: str,
    reservation_id: uuid.UUID | None = None,
    offer_id: uuid.UUID | None = None,
    waitlist_id: uuid.UUID | None = None,
) -> bool:
    """Como ``core.enqueue_message``, pero dice si la fila es nueva: el evento
    del historial va solo con la primera."""
    inserted = await session.scalar(
        insert(ReservationOutbox)
        .values(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            reservation_id=reservation_id,
            offer_id=offer_id,
            waitlist_id=waitlist_id,
            kind=kind,
            dedupe_key=dedupe_key[:160],
        )
        .on_conflict_do_nothing(constraint="uq_reservation_outbox_dedupe")
        .returning(ReservationOutbox.id)
    )
    return inserted is not None


async def _lock(
    session: AsyncSession, reservation_id: uuid.UUID, statuses: tuple[str, ...]
) -> Reservation | None:
    """La reserva bajo candado, si sigue en uno de ``statuses``. Si otra
    transacción la tiene, ``None``: la próxima pasada la vuelve a mirar."""
    locked: Reservation | None = await session.scalar(
        sa.select(Reservation)
        .where(Reservation.id == reservation_id, Reservation.status.in_(statuses))
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )
    return locked


def _automatic_key_sql(kind: str) -> sa.ColumnElement[str]:
    """``automatic_key`` en SQL, para buscarla por el índice único del outbox."""
    rid = sa.cast(Reservation.id, sa.String)
    if kind == "ask_confirmation":
        return sa.literal("ask:", sa.String) + rid + sa.literal(":auto", sa.String)
    return sa.literal("reminder:", sa.String) + rid


async def request_confirmations(session: AsyncSession, ctx: Ctx, now: datetime) -> int:
    """(1) Encola la petición de confirmación o el recordatorio que ya toca.

    Mira las de las próximas 24 h que aún no tienen ninguno de los dos, sin
    tope: con tope, las que nunca se preguntan (reservadas dentro de la
    ventana) podrían tapar para siempre a las que sí tocan."""
    already = (
        sa.select(ReservationOutbox.id)
        .where(
            sa.or_(
                ReservationOutbox.dedupe_key == _automatic_key_sql("ask_confirmation"),
                ReservationOutbox.dedupe_key == _automatic_key_sql("reminder"),
            )
        )
        .exists()
    )
    rows = await session.execute(
        sa.select(Reservation)
        .where(
            Reservation.status.in_(("pending", "confirmed")),
            Reservation.starts_at > now,
            Reservation.starts_at <= now + DAY_BEFORE,
            sa.or_(Reservation.contact_phone.is_not(None), Reservation.customer_id.is_not(None)),
            ~already,
        )
        .order_by(Reservation.starts_at)
        .execution_options(populate_existing=True)
    )
    queued = 0
    for res in rows.scalars().all():
        due = ask_at(ctx, res)
        if now < due or res.created_at > due:
            continue
        if res.confirmation_requested_at is not None and res.confirmation_requested_at >= due:
            continue  # ya se le preguntó a mano en la ventana
        locked = await _lock(session, res.id, ("pending", "confirmed"))
        if locked is None:
            continue
        kind = automatic_kind(ctx, locked)
        if kind is None:
            continue
        fresh = await enqueue_once(
            session,
            tenant_id=ctx.tenant_id,
            kind=kind,
            dedupe_key=automatic_key(kind, locked.id),
            reservation_id=locked.id,
        )
        if not fresh:
            continue
        if kind == "ask_confirmation":
            locked.confirmation_requested_at = now
            add_event(session, locked, "confirmation_requested", SYSTEM)
        queued += 1
    return queued


# ── liberar (Aforo) ─────────────────────────────────────────────────────────


async def release_unconfirmed(session: AsyncSession, ctx: Ctx, now: datetime) -> int:
    """(2) Aforo: cancela (fuente ``system``) la que sigue sin confirmar 1 h
    antes, si «liberar» está encendido y la pregunta le llegó a salir."""
    if ctx.mode != "capacity" or not ctx.settings.release_unconfirmed:
        return 0
    asked = (
        sa.select(ReservationOutbox.id)
        .where(
            ReservationOutbox.reservation_id == Reservation.id,
            ReservationOutbox.kind == "ask_confirmation",
            ReservationOutbox.status == "sent",
        )
        .exists()
    )
    rows = await session.execute(
        sa.select(Reservation)
        .where(
            Reservation.mode == "capacity",
            Reservation.status == "pending",
            Reservation.starts_at > now,
            Reservation.starts_at <= now + RELEASE_BEFORE,
            asked,
        )
        .order_by(Reservation.starts_at)
        .limit(BATCH)
        .with_for_update(skip_locked=True, of=Reservation)
        .execution_options(populate_existing=True)
    )
    released = 0
    for res in rows.scalars():
        await cancel_booking(
            session,
            ctx,
            res,
            by="system",
            actor=SYSTEM,
            now=now,
            notify=True,
            cause="release_unconfirmed",
            check_allowed=False,
        )
        add_event(session, res, "released", SYSTEM)
        released += 1
    return released


# ── terminar ────────────────────────────────────────────────────────────────


async def mark_done(session: AsyncSession, now: datetime) -> int:
    """(3) Servicios: ``pending``/``confirmed`` tras su fin. Aforo: ``arrived``
    tras su estancia. Cada una con su versión nueva y su evento."""
    rows = await session.execute(
        sa.select(Reservation)
        .where(
            Reservation.starts_at < now,
            Reservation.ends_at <= now,
            sa.or_(
                sa.and_(
                    Reservation.mode == "services",
                    Reservation.status.in_(("pending", "confirmed")),
                ),
                sa.and_(Reservation.mode == "capacity", Reservation.status == "arrived"),
            ),
        )
        .order_by(Reservation.ends_at)
        .limit(BATCH)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )
    done = 0
    for res in rows.scalars():
        res.status = "done"
        res.version = (res.version or 1) + 1
        add_event(session, res, "done", SYSTEM)
        done += 1
    return done


# ── ofertas de Aforo ────────────────────────────────────────────────────────


async def open_capacity_offers(session: AsyncSession, ctx: Ctx, now: datetime) -> int:
    """(5) Aforo: hoy y mañana, una oferta en cada franja donde alguien de la
    lista ya cabe (``waitlist.open_capacity`` decide; aquí solo se evita mirar
    días sin nadie esperando)."""
    if ctx.mode != "capacity" or not ctx.settings.waitlist_enabled:
        return 0
    today = ctx.today(now)
    opened = 0
    for day in (today, today + timedelta(days=1)):
        someone = await session.scalar(
            sa.select(ReservationWaitlist.id)
            .where(
                ReservationWaitlist.mode == "capacity",
                ReservationWaitlist.status == "waiting",
                ReservationWaitlist.desired_day == day,
            )
            .limit(1)
        )
        if someone is None:
            continue
        opened += len(await waitlist.open_capacity(session, ctx, day=day, now=now))
    return opened


@dataclass
class Tick:
    """Lo que hizo una pasada de ``reservations-cron`` en un cliente."""

    asked: int = 0
    released: int = 0
    done: int = 0
    expired: int = 0
    offers: int = 0

    def as_log(self) -> dict[str, int]:
        return {
            "asked": self.asked,
            "released": self.released,
            "done": self.done,
            "expired": self.expired,
            "offers": self.offers,
        }


async def tick(session: AsyncSession, ctx: Ctx, now: datetime, *, offers: bool = True) -> Tick:
    """Una pasada de ``reservations-cron`` en un cliente. ``offers`` = el
    cliente tiene el módulo: sin él, Reservas deja de ofrecer huecos (spec,
    «Desactivar el módulo»), pero lo comprometido sigue (recordatorios,
    liberar, terminar, caducar)."""
    out = Tick()
    out.released = await release_unconfirmed(session, ctx, now)
    out.asked = await request_confirmations(session, ctx, now)
    out.done = await mark_done(session, now)
    out.expired = await waitlist.expire(session, ctx, now)
    if offers:
        # Incluye el sitio que acaba de liberar (2): siempre es de hoy o de
        # mañana.
        out.offers = await open_capacity_offers(session, ctx, now)
    await session.flush()
    return out


# ── avisos al cliente final ─────────────────────────────────────────────────

#: La plantilla de cada aviso fuera de la ventana de 24 h. ``offer_lost`` no
#: tiene: va en la ventana (la persona acaba de escribir).
TEMPLATES: dict[str, str | None] = {
    "confirmation": "reserva_confirmada",
    "ask_confirmation": "reserva_pide_confirmacion",
    "reminder": "reserva_recordatorio",
    "moved": "reserva_cambiada",
    "cancelled": "reserva_cancelada",
    "offer": "reserva_hueco_libre",
    "offer_won": "reserva_confirmada",
    "offer_lost": None,
}
#: Las variables (BODY, con nombre) de cada plantilla, en el orden del contrato.
TEMPLATE_VARIABLES: dict[str, tuple[str, ...]] = {
    "reserva_confirmada": ("nombre", "negocio", "cuando", "detalle"),
    "reserva_pide_confirmacion": ("nombre", "negocio", "cuando", "detalle"),
    "reserva_recordatorio": ("nombre", "negocio", "cuando", "detalle"),
    "reserva_cambiada": ("nombre", "negocio", "cuando", "detalle"),
    "reserva_cancelada": ("nombre", "negocio", "cuando"),
    "reserva_hueco_libre": ("nombre", "negocio", "cuando", "detalle", "minutos"),
}
#: El mismo mensaje como texto, para dentro de la ventana: el texto de partida
#: de cada plantilla (``contracts/worker-y-avisos.md``).
TEXTS: dict[str, str] = {
    "confirmation": (
        "Hola, {nombre}. Tu reserva en {negocio} quedó para {cuando} ({detalle}). "
        "Si necesitas cambiarla, escríbenos por aquí."
    ),
    "ask_confirmation": (
        "Hola, {nombre}. Te esperamos en {negocio} {cuando} ({detalle}). "
        "¿Nos confirmas que vienes? Responde SÍ o NO."
    ),
    "reminder": "Hola, {nombre}. Te recordamos tu reserva en {negocio} {cuando} ({detalle}).",
    "moved": "Hola, {nombre}. Tu reserva en {negocio} cambió: ahora es {cuando} ({detalle}).",
    "cancelled": (
        "Hola, {nombre}. Tu reserva en {negocio} para {cuando} quedó cancelada. "
        "Si quieres otra hora, escríbenos por aquí."
    ),
    "offer": (
        "Mensaje automático de {negocio}: se liberó un hueco {cuando} ({detalle}). "
        "¿Lo quieres? Responde SÍ en los próximos {minutos} minutos y te lo reservamos."
    ),
    "offer_won": (
        "Hola, {nombre}. Tu reserva en {negocio} quedó para {cuando} ({detalle}). "
        "Si necesitas cambiarla, escríbenos por aquí."
    ),
    "offer_lost": (
        "Hola, {nombre}. El hueco de {cuando} ya lo tomó otra persona. Sigues en la "
        "lista de espera de {negocio}: si se libera otro, te avisamos."
    ),
}

WEEKDAYS_ES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
#: «4 personas» con la palabra de cada tipo de negocio (singular, plural).
PARTY_WORDS: dict[str, tuple[str, str]] = {
    "restaurant": ("comensal", "comensales"),
    "bar": ("persona", "personas"),
    "classes": ("plaza", "plazas"),
    "tours": ("plaza", "plazas"),
    "rooms": ("persona", "personas"),
    "spa": ("plaza", "plazas"),
}


def when_text(ctx: Ctx, at: datetime) -> str:
    """«el jueves 23 a las 20:30», en la hora del negocio."""
    loc = ctx.local(at)
    return f"el {WEEKDAYS_ES[loc.weekday()]} {loc.day} a las {loc.strftime('%H:%M')}"


def party_text(ctx: Ctx, n: int) -> str:
    one, many = PARTY_WORDS.get(ctx.settings.capacity_kind or "", ("persona", "personas"))
    return f"{n} {one if n == 1 else many}"


def render_text(kind: str, variables: dict[str, str]) -> str:
    text = TEXTS[kind].format(**variables)
    # «de el jueves» → «del jueves» (solo en texto libre: «El hueco de {cuando}»).
    return text.replace(" de el ", " del ")


def window_open(conversation: Conversation | None, now: datetime) -> bool:
    """La ventana de atención de WhatsApp: el cliente escribió hace < 24 h."""
    if conversation is None or conversation.last_inbound_at is None:
        return False
    return now - conversation.last_inbound_at < SERVICE_WINDOW


@dataclass
class Notice:
    """Un aviso listo para salir (o la razón por la que no sale)."""

    kind: str
    template: str | None
    variables: dict[str, str]
    text: str
    reservation: Reservation | None
    #: Teléfono del destinatario en dígitos (el ``from`` de Meta), o ``None``.
    phone: str | None
    customer_id: uuid.UUID | None
    conversation_id: uuid.UUID | None
    stale: bool = False
    data: dict[str, Any] = field(default_factory=dict)

    def template_body(self) -> dict[str, str]:
        if self.template is None:
            return {}
        return {k: self.variables[k] for k in TEMPLATE_VARIABLES[self.template]}


async def _detail(
    session: AsyncSession,
    ctx: Ctx,
    *,
    mode: str,
    service_name: str | None,
    service_id: uuid.UUID | None,
    staff_id: uuid.UUID | None,
    party: int,
) -> str:
    if mode != "services":
        return party_text(ctx, party)
    if service_name is None and service_id is not None:
        svc = await session.get(ReservationService, service_id)
        service_name = svc.name if svc is not None else None
    staff = await session.get(ReservationStaff, staff_id) if staff_id is not None else None
    if service_name and staff is not None:
        return f"{service_name} con {staff.name}"
    return service_name or (staff.name if staff is not None else "tu cita")


def _still_applies(
    row: ReservationOutbox,
    res: Reservation | None,
    offer: ReservationOffer | None,
    candidate: ReservationOfferCandidate | None,
    now: datetime,
) -> bool:
    """Lo encolado sigue siendo verdad: no se pregunta a quien ya confirmó ni se
    recuerda una reserva cancelada, ni se ofrece un hueco que ya no se ofrece."""
    if row.kind in ("offer_lost",):
        return True
    if row.kind == "offer":
        return (
            offer is not None
            and offer.status == "running"
            and candidate is not None
            and candidate.status == "waiting"
        )
    if res is None:
        return False
    if row.kind == "cancelled":
        return res.status == "cancelled"
    if row.kind == "ask_confirmation":
        return res.status == "pending" and res.starts_at > now
    if row.kind == "offer_won":
        return res.status in ("pending", "confirmed")
    return res.status in ("pending", "confirmed") and res.starts_at > now


async def compose(session: AsyncSession, ctx: Ctx, row: ReservationOutbox, now: datetime) -> Notice:
    """El aviso de una fila del outbox: a quién, qué y con qué plantilla."""
    res = (
        await session.get(Reservation, row.reservation_id)
        if row.reservation_id is not None
        else None
    )
    entry = (
        await session.get(ReservationWaitlist, row.waitlist_id)
        if row.waitlist_id is not None
        else None
    )
    offer = await session.get(ReservationOffer, row.offer_id) if row.offer_id is not None else None
    candidate = (
        await session.get(ReservationOfferCandidate, (row.offer_id, row.waitlist_id))
        if row.offer_id is not None and row.waitlist_id is not None
        else None
    )
    template = TEMPLATES.get(row.kind)
    stale = not _still_applies(row, res, offer, candidate, now)

    name: str | None
    if res is not None:
        name, phone, customer_id = res.contact_name, res.contact_phone, res.customer_id
        at: datetime | None = res.starts_at
        detail = await _detail(
            session,
            ctx,
            mode=res.mode,
            service_name=res.service_name,
            service_id=res.service_id,
            staff_id=res.staff_id,
            party=res.party_size,
        )
    elif entry is not None:
        name, phone, customer_id = entry.contact_name, entry.contact_phone, entry.customer_id
        at = offer.starts_at if offer is not None else None
        detail = await _detail(
            session,
            ctx,
            mode=entry.mode,
            service_name=None,
            # Lo que la persona pidió, en el hueco (y con quien) que se libera.
            service_id=entry.service_id or (offer.service_id if offer else None),
            staff_id=offer.staff_id if offer is not None else entry.staff_id,
            party=entry.party_size,
        )
    else:
        name = phone = None
        customer_id = None
        at = None
        detail = ""
        stale = True
    variables = {
        "nombre": (name or "").strip() or "cliente",
        "negocio": ctx.business_name,
        "cuando": when_text(ctx, at) if at is not None else "",
        "detalle": detail,
        "minutos": str(offer.window_minutes) if offer is not None else "",
    }
    digits = phone_digits(phone)
    if digits is None and customer_id is not None:
        customer = await session.get(Customer, customer_id)
        digits = phone_digits(customer.identifier) if customer is not None else None
    return Notice(
        kind=row.kind,
        template=template,
        variables=variables,
        text=render_text(row.kind, variables) if not stale else "",
        reservation=res,
        phone=digits,
        customer_id=customer_id,
        conversation_id=res.conversation_id if res is not None else None,
        stale=stale,
    )


async def due_outbox(
    session: AsyncSession, now: datetime, *, limit: int = OUTBOX_BATCH
) -> list[ReservationOutbox]:
    """Lo pendiente que ya toca, bajo candado (``SKIP LOCKED``: dos réplicas no
    mandan la misma fila)."""
    rows = await session.execute(
        sa.select(ReservationOutbox)
        .where(ReservationOutbox.status == "pending", ReservationOutbox.next_attempt_at <= now)
        .order_by(ReservationOutbox.next_attempt_at, ReservationOutbox.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )
    return list(rows.scalars())


def mark_sent(
    session: AsyncSession,
    row: ReservationOutbox,
    notice: Notice,
    *,
    message_id: uuid.UUID,
    via: str,
) -> None:
    row.status = "sent"
    row.message_id = message_id
    row.attempts = (row.attempts or 0) + 1
    row.last_error = None
    if notice.reservation is not None:
        kind = "reminder_sent" if row.kind == "reminder" else "notified"
        add_event(session, notice.reservation, kind, SYSTEM, {"kind": row.kind, "via": via})


def mark_skipped(
    session: AsyncSession,
    row: ReservationOutbox,
    reason: str,
    reservation: Reservation | None,
) -> None:
    """No sale, y la reserva lo dice en su historial: nunca se da por avisado a
    quien no lo fue. ``stale`` no es un fallo y no deja evento."""
    row.status = "skipped"
    row.skip_reason = reason
    if reason != SKIP_STALE and reservation is not None:
        add_event(session, reservation, "notify_failed", SYSTEM, {"kind": row.kind, "why": reason})


def error_text(exc: BaseException, limit: int = 300) -> str:
    """El error para el log y la fila, sin datos de nadie. El de SQLAlchemy lleva
    la sentencia y sus parámetros (teléfonos, nombres): de ese, solo los tipos."""
    if isinstance(exc, StatementError):
        orig = type(exc.orig).__name__ if exc.orig is not None else "-"
        return f"{type(exc).__name__}: {orig}"[:limit]
    return f"{type(exc).__name__}: {exc}"[:limit]


async def mark_error(
    session: AsyncSession, row: ReservationOutbox, error: BaseException, now: datetime
) -> None:
    """Un error al preparar el envío: reintento con espera; al tercero, ``failed``
    y ``notify_failed`` en el historial. Nunca se reintenta para siempre."""
    row.attempts = (row.attempts or 0) + 1
    row.last_error = error_text(error)
    if row.attempts >= OUTBOX_MAX_ATTEMPTS:
        row.status = "failed"
        if row.reservation_id is not None:
            res = await session.get(Reservation, row.reservation_id)
            if res is not None:
                add_event(
                    session, res, "notify_failed", SYSTEM, {"kind": row.kind, "why": "send_failed"}
                )
        return
    row.next_attempt_at = now + OUTBOX_BACKOFF[min(row.attempts, len(OUTBOX_BACKOFF)) - 1]


__all__ = [
    "OUTBOX_BACKOFF",
    "OUTBOX_MAX_ATTEMPTS",
    "SKIP_NO_CHANNEL",
    "SKIP_NO_PHONE",
    "SKIP_NO_TEMPLATE",
    "SKIP_OPTED_OUT",
    "SKIP_STALE",
    "TEMPLATES",
    "TEMPLATE_LANGUAGE",
    "TEMPLATE_VARIABLES",
    "TEXTS",
    "Notice",
    "Tick",
    "ask_at",
    "automatic_key",
    "automatic_kind",
    "compose",
    "due_outbox",
    "enqueue_once",
    "error_text",
    "mark_done",
    "mark_error",
    "mark_sent",
    "mark_skipped",
    "open_capacity_offers",
    "party_text",
    "release_unconfirmed",
    "render_text",
    "request_confirmations",
    "tick",
    "when_text",
    "window_open",
]
