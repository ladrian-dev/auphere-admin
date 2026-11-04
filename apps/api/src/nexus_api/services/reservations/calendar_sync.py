"""Reservas P3 — sincronizar el Google Calendar del equipo (spec 043, Historia 7).

Lo hace **el sistema**, no el agente. Aquí se usa la conexión que el cliente ya
hizo en el proveedor de consentimientos, con el mismo ``user_id = tenant_<slug>``
que el resto del runtime.

Dos sentidos, y en los dos lo mínimo:

- **entra** el «ocupado» de cada calendario asociado a una persona: solo inicio
  y fin (``reservation_busy``); ni título ni asistentes;
- **sale** cada reserva viva de esa persona como un evento **«Ocupado»**, sin
  nombre del cliente ni servicio; se mueve o se borra con la reserva.

**Una pasada, tres partes que no dependen unas de otras**: quitar lo que sobra,
escribir lo que falta y leer el ocupado. Si una falla, las otras siguen.

**Lo que se escribe en Google se apunta de inmediato**, en su propia transacción
y reserva por reserva. Google no se deshace con un ``ROLLBACK``: si un fallo se
llevara los ids, cada pasada repetiría sus «Ocupado».

**Con datos viejos no se bloquea.** Sin conexión sana, o con un permiso rechazado,
el ocupado se quita en la pasada siguiente; con lecturas fallidas por cualquier
otra causa, a los ``BUSY_STALE_AFTER``. Un hueco ofrecido de más se ve como un
choque en la agenda; uno bloqueado de más es un cliente que nadie atiende. La
pantalla lo dice con ``last_error``.

Todo lo que sabe del proveedor vive en :class:`ComposioGoogleCalendar`: los
nombres de las acciones y de sus argumentos son los del catálogo público de
Composio (``docs.composio.dev/toolkits/googlecalendar``). Las pruebas usan un
doble de la puerta.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from typing import Any, Final, Literal, Protocol

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import get_current_tenant, tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Connector,
    Reservation,
    Tenant,
    TenantConnector,
    TenantConnectorStatus,
)
from nexus_api.services.connectors.composio_client import (
    ComposioAuthExpired,
    ComposioNotFound,
)
from nexus_api.services.reservations.core import EVENT_MOVED, Ctx

log = structlog.get_logger(__name__)

#: Marca de nuestros propios eventos «Ocupado», para quien mire el calendario.
#: Lo nuestro se reconoce por el id del evento que guarda la reserva
#: (``external_event_id``), no por este texto: cualquiera puede escribirlo en la
#: descripción de una invitación y liberar así ese hueco (/cso, apéndice).
MARK = "auphere:reserva:"
SYNC_AHEAD = timedelta(days=60)
TOOLKIT = "googlecalendar"

#: Cuánto se sigue creyendo el ocupado de un calendario que no se puede leer. Da
#: margen a un corte del proveedor sin liberar huecos, y no bloquea con datos viejos
#: un día entero.
BUSY_STALE_AFTER: Final = timedelta(minutes=30)
#: Cuánto se insiste en borrar el evento de una reserva ya terminada. Sin tope, un
#: calendario perdido significa una llamada cada dos minutos, para siempre.
REMOVAL_WINDOW: Final = timedelta(days=7)
PAGE_SIZE: Final = 250
MAX_PAGES: Final = 50

#: Lo que ``last_error`` guarda y la API enseña: códigos nuestros, que la pantalla
#: traduce. El texto del proveedor no pasa de aquí: puede traer un token o el título
#: de la cita de otra persona.
ERROR_CONNECTION: Final = "connection"
ERROR_AUTH: Final = "auth"
ERROR_CALENDAR_GONE: Final = "calendar_gone"
ERROR_READ: Final = "read"
ERROR_WRITE: Final = "write"

#: Lo que no se arregla solo: seguir creyendo ese ocupado solo bloquea huecos.
_NEEDS_A_PERSON: Final = frozenset({ERROR_AUTH, ERROR_CALENDAR_GONE})

#: El evento se creó en Google y su respuesta no trae el id. Se guarda para no volver
#: a crearlo cada dos minutos; no se podrá mover, y la pantalla dice ``write``.
UNKNOWN_EVENT: Final = "?"

_LIVE: Final = ("pending", "confirmed")
_GONE: Final = ("cancelled", "noshow")
_MAX_REF: Final = 255 - len(EVENT_MOVED)

#: Google responde 403 también al pasarse de cuota, y eso se arregla solo: se mira
#: antes que el permiso.
_RATE_LIMIT = re.compile(r"\b429\b|rate.?limit|quota|usage.?limit", re.IGNORECASE)
_NOT_FOUND = re.compile(r"\b(404|410)\b|not.?found|been deleted", re.IGNORECASE)
_REFUSED = re.compile(
    r"\b(401|403)\b|invalid_grant|unauthori[sz]ed|forbidden|insufficient|expired",
    re.IGNORECASE,
)


class GoogleCalendarError(RuntimeError):
    """Lo que dijo el proveedor. ``kind``: ``auth``, ``not_found`` u ``other``."""

    def __init__(self, message: str, *, kind: str = "other") -> None:
        super().__init__(message)
        self.kind = kind


def _kind_of_text(text: str) -> str:
    if _RATE_LIMIT.search(text):
        return "other"
    if _NOT_FOUND.search(text):
        return "not_found"
    if _REFUSED.search(text):
        return "auth"
    return "other"


ConnectionState = Literal["none", "connected", "needs_reauth"]


@dataclass(frozen=True)
class Connection:
    user_id: str
    connection_id: str


@dataclass(frozen=True)
class Busy:
    starts_at: datetime
    ends_at: datetime
    event_id: str | None = None


class GoogleCalendarGateway(Protocol):
    async def list_calendars(self, conn: Connection) -> list[dict[str, str]]: ...

    async def busy(
        self, conn: Connection, calendar_id: str, start: datetime, end: datetime, *, tz: tzinfo
    ) -> list[Busy]: ...

    async def create_busy(
        self, conn: Connection, calendar_id: str, start: datetime, end: datetime, marker: str
    ) -> str: ...

    async def delete_busy(self, conn: Connection, calendar_id: str, event_id: str) -> None: ...


def _rfc3339(at: datetime) -> str:
    """En UTC y con ``Z``: sin un «+» que pueda perderse en una URL."""
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _body_of(data: dict[str, Any]) -> dict[str, Any]:
    """El proveedor devuelve lo de Google suelto o dentro de ``response_data``."""
    inner = data.get("response_data")
    return inner if isinstance(inner, dict) else data


def _listing(data: dict[str, Any], *keys: str) -> tuple[list[Any], str | None]:
    """Los elementos de un listado y el token de la página siguiente.

    Una respuesta que no es un listado es un fallo, no un calendario vacío: leerla
    como vacío borraría el ocupado de verdad sin que nadie lo supiera."""
    body = _body_of(data)
    token = body.get("nextPageToken") or body.get("next_page_token")
    next_token = str(token) if token else None
    for key in keys:
        found = body.get(key)
        if isinstance(found, list):
            return found, next_token
    # Google puede omitir ``items`` si no hay nada; el sobre dice que es un listado.
    if "kind" in body or "timeZone" in body or "etag" in body:
        return [], next_token
    raise GoogleCalendarError("the provider did not answer with a listing")


def _span(ev: dict[str, Any], tz: tzinfo) -> tuple[datetime, datetime] | None:
    """Inicio y fin de un evento. Uno de todo el día ocupa el día en la zona del
    negocio, porque es ahí donde se ofrecen los huecos, y su fin ya es exclusivo."""
    start, end = ev.get("start") or {}, ev.get("end") or {}
    if not isinstance(start, dict) or not isinstance(end, dict):
        return None
    try:
        if start.get("dateTime") and end.get("dateTime"):
            a = datetime.fromisoformat(start["dateTime"])
            b = datetime.fromisoformat(end["dateTime"])
            return (
                a if a.tzinfo else a.replace(tzinfo=tz),
                b if b.tzinfo else b.replace(tzinfo=tz),
            )
        if start.get("date") and end.get("date"):
            return (
                datetime.combine(date.fromisoformat(start["date"]), time.min, tzinfo=tz),
                datetime.combine(date.fromisoformat(end["date"]), time.min, tzinfo=tz),
            )
    except (TypeError, ValueError):
        return None  # un evento raro no tumba la lectura del calendario entero
    return None


class ComposioGoogleCalendar:
    """La puerta real, sobre el cliente del proveedor de consentimientos."""

    def __init__(self, client: Any) -> None:
        self._client = client

    async def _run(self, conn: Connection, slug: str, args: dict[str, Any]) -> dict[str, Any]:
        try:
            result = await self._client.execute_tool(
                tool_slug=slug,
                user_id=conn.user_id,
                connection_id=conn.connection_id,
                arguments=args,
            )
        except ComposioAuthExpired as exc:
            raise GoogleCalendarError(f"{slug}: refused", kind="auth") from exc
        except ComposioNotFound as exc:
            # No es «el evento no existe»: Composio no conoce la conexión o el toolkit. Darlo
            # por borrado perdería el id y dejaría el evento en Google para siempre.
            raise GoogleCalendarError(f"{slug}: connection unknown", kind="auth") from exc
        if result.error:
            raise GoogleCalendarError(f"{slug}: {result.error}", kind=_kind_of_text(result.error))
        return dict(result.data or {})

    async def _pages(
        self,
        conn: Connection,
        slug: str,
        args: dict[str, Any],
        *keys: str,
        token_arg: str,
    ) -> list[Any]:
        items: list[Any] = []
        token: str | None = None
        for _ in range(MAX_PAGES):
            page = await self._run(conn, slug, {**args, token_arg: token} if token else args)
            found, token = _listing(page, *keys)
            items.extend(found)
            if token is None:
                return items
        raise GoogleCalendarError(f"{slug}: more than {MAX_PAGES} pages")

    async def list_calendars(self, conn: Connection) -> list[dict[str, str]]:
        """Los calendarios de la cuenta **en los que se puede escribir**: uno de solo
        lectura, como el de festivos, rechazaría cada «Ocupado» para siempre."""
        items = await self._pages(
            conn, "GOOGLECALENDAR_LIST_CALENDARS", {}, "items", "calendars", token_arg="page_token"
        )
        return [
            {"id": str(c.get("id")), "name": str(c.get("summary") or c.get("id"))}
            for c in items
            if isinstance(c, dict)
            and c.get("id")
            and c.get("accessRole") not in ("reader", "freeBusyReader")
        ]

    async def busy(
        self, conn: Connection, calendar_id: str, start: datetime, end: datetime, *, tz: tzinfo
    ) -> list[Busy]:
        items = await self._pages(
            conn,
            "GOOGLECALENDAR_EVENTS_LIST",
            {
                "calendarId": calendar_id,
                "timeMin": _rfc3339(start),
                "timeMax": _rfc3339(end),
                "singleEvents": True,
                "maxResults": PAGE_SIZE,
            },
            "items",
            "events",
            token_arg="pageToken",
        )
        out: list[Busy] = []
        for ev in items:
            if not isinstance(ev, dict) or ev.get("transparency") == "transparent":
                continue
            span = _span(ev, tz)
            if span is not None:
                ev_id = ev.get("id")
                out.append(Busy(span[0], span[1], str(ev_id) if ev_id else None))
        return out

    async def create_busy(
        self, conn: Connection, calendar_id: str, start: datetime, end: datetime, marker: str
    ) -> str:
        minutes = int((end - start).total_seconds() // 60)
        data = await self._run(
            conn,
            "GOOGLECALENDAR_CREATE_EVENT",
            {
                "calendar_id": calendar_id,
                "summary": "Ocupado",
                "description": marker,
                # Sin desfase y con la zona aparte, como pide la acción.
                "start_datetime": start.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
                "timezone": "UTC",
                "event_duration_hour": minutes // 60,
                "event_duration_minutes": minutes % 60,
                "transparency": "opaque",
                "send_updates": "none",
            },
        )
        event_id = _body_of(data).get("id")
        if event_id:
            return str(event_id)
        if not data:  # sin error y sin nada: no consta que exista
            raise GoogleCalendarError("GOOGLECALENDAR_CREATE_EVENT: empty answer")
        return UNKNOWN_EVENT

    async def delete_busy(self, conn: Connection, calendar_id: str, event_id: str) -> None:
        try:
            await self._run(
                conn,
                "GOOGLECALENDAR_DELETE_EVENT",
                {"calendar_id": calendar_id, "event_id": event_id},
            )
        except GoogleCalendarError as exc:
            # Quien lo borró a mano ya hizo el trabajo.
            if exc.kind != "not_found":
                raise


# ── dónde vive el evento de cada reserva ────────────────────────────────────
#
# ``external_event_id`` guarda ``<calendario> <evento>``: una reserva puede cambiar de
# persona, y una persona de calendario, y el evento sigue donde se escribió. Ni los ids
# de calendario ni los de evento de Google llevan espacios. Con ``EVENT_MOVED`` delante
# está pendiente de borrar: lo pone ``move_booking``, en la transacción de la reserva.


@dataclass(frozen=True)
class _EventRef:
    calendar_id: str | None
    event_id: str


def _event_ref(calendar_id: str, event_id: str) -> str:
    joined = f"{calendar_id} {event_id}"
    return joined if len(joined) <= _MAX_REF else event_id[:_MAX_REF]


def _parse_ref(stored: str) -> _EventRef:
    bare = stored.removeprefix(EVENT_MOVED)
    calendar_id, _, event_id = bare.rpartition(" ")
    return _EventRef(calendar_id or None, event_id)


# ── la conexión ─────────────────────────────────────────────────────────────


async def connection_state(session: AsyncSession) -> ConnectionState:
    """``none``, ``connected`` o ``needs_reauth``: la de la cuenta de Google Calendar del
    cliente de esta transacción. No recibe el cliente: lo pone la RLS."""
    rows = await session.execute(
        sa.select(TenantConnector.status, TenantConnector.credentials_ref)
        .join(Connector, Connector.id == TenantConnector.connector_id)
        .where(Connector.mcp_server_ref == f"composio:{TOOLKIT}")
    )
    state: ConnectionState = "none"
    for status, credentials in rows.all():
        value = getattr(status, "value", status)
        if value in (TenantConnectorStatus.CONNECTED.value, TenantConnectorStatus.PARTIAL.value):
            if (credentials or {}).get("composio_connection_id"):
                return "connected"
        elif value in (
            TenantConnectorStatus.NEEDS_REAUTH.value,
            TenantConnectorStatus.PAUSED.value,
        ):
            state = "needs_reauth"
    return state


async def connection_of(session: AsyncSession, tenant_id: uuid.UUID) -> Connection | None:
    """La conexión de Google Calendar del cliente, si la hizo."""
    slug = await session.scalar(sa.select(Tenant.slug).where(Tenant.id == tenant_id))
    row = (
        await session.execute(
            sa.select(TenantConnector.credentials_ref)
            .join(Connector, Connector.id == TenantConnector.connector_id)
            .where(
                TenantConnector.tenant_id == tenant_id,
                Connector.mcp_server_ref == f"composio:{TOOLKIT}",
                TenantConnector.status.in_(
                    [TenantConnectorStatus.CONNECTED.value, TenantConnectorStatus.PARTIAL.value]
                ),
            )
            .limit(1)
        )
    ).first()
    if not slug or row is None:
        return None
    connection_id = (row[0] or {}).get("composio_connection_id")
    if not isinstance(connection_id, str) or not connection_id:
        return None
    return Connection(user_id=f"tenant_{slug}", connection_id=connection_id)


async def connection_lost(session: AsyncSession, *, now: datetime) -> int:
    """La conexión no está sana y hay calendarios asociados: nadie va a refrescar su
    ocupado hasta que una persona vuelva a conectar, así que deja de bloquear. Lo dice
    una vez, no cada dos minutos. Las reservas sin escribir esperan a la vuelta."""
    told = await session.execute(
        sa.text(
            "UPDATE reservation_staff_calendars SET last_error = :e "
            "WHERE last_error IS DISTINCT FROM :e"
        ),
        {"e": ERROR_CONNECTION},
    )
    dropped = await session.execute(
        sa.text("DELETE FROM reservation_busy WHERE ends_at > :now"), {"now": now}
    )
    changed, gone = _rowcount(told), _rowcount(dropped)
    if changed or gone:
        log.warning(
            "reservation_calendar.connection_unhealthy",
            tenant_id=str(get_current_tenant()),
            calendars=changed,
            dropped=gone,
        )
    return gone


def _rowcount(result: Any) -> int:
    return int(getattr(result, "rowcount", 0) or 0)


async def has_work(session: AsyncSession, *, now: datetime) -> bool:
    """Hay algo que sincronizar: alguien asociado, o eventos que quitar de un calendario
    que ya no es de nadie."""
    mapped = await session.scalar(sa.text("SELECT 1 FROM reservation_staff_calendars LIMIT 1"))
    if mapped is not None:
        return True
    pending = await session.scalar(
        sa.select(Reservation.id)
        .where(
            Reservation.external_event_id.like(f"{EVENT_MOVED}%"),
            Reservation.ends_at > now - REMOVAL_WINDOW,
        )
        .limit(1)
    )
    return pending is not None


# ── la pasada ───────────────────────────────────────────────────────────────


async def _mappings(session: AsyncSession) -> dict[uuid.UUID, str]:
    rows = await session.execute(
        sa.text("SELECT staff_id, calendar_id FROM reservation_staff_calendars")
    )
    return {sid: cal for sid, cal in rows.all()}


def _failure(exc: Exception, otherwise: str) -> str:
    """El código de un fallo. Del proveedor, solo si es de permiso o de un calendario
    que ya no está; lo demás es lo que se estaba intentando."""
    kind = getattr(exc, "kind", None)
    if kind == "auth":
        return ERROR_AUTH
    if kind == "not_found":
        return ERROR_CALENDAR_GONE
    return otherwise


async def _save_removed(ctx: Ctx, reservation_id: uuid.UUID, stored: str) -> None:
    """Quita la referencia, si sigue siendo la del evento borrado: el evento pudo
    marcarse como movido mientras tanto, y la reserva, ganar otro."""
    bare = stored.removeprefix(EVENT_MOVED)
    async with (
        get_sessionmaker()() as session,
        tenant_scoped_session(session, ctx.tenant_id),
    ):
        await session.execute(
            sa.update(Reservation)
            .where(
                Reservation.id == reservation_id,
                Reservation.external_event_id.in_((bare, f"{EVENT_MOVED}{bare}")),
            )
            .values(external_event_id=None)
        )


async def _save_written(
    ctx: Ctx,
    reservation_id: uuid.UUID,
    staff_id: uuid.UUID,
    calendar_id: str,
    event_id: str,
    span: tuple[datetime, datetime],
) -> bool:
    """Apunta el evento recién creado. La reserva pudo cambiar mientras se creaba: si
    es otra, queda como movido y la pasada siguiente lo arregla. ``False`` si otra
    pasada ya le escribió el suyo, y este sobra."""
    ref = _event_ref(calendar_id, event_id)
    async with (
        get_sessionmaker()() as session,
        tenant_scoped_session(session, ctx.tenant_id),
    ):
        row = (
            await session.execute(
                sa.select(
                    Reservation.staff_id,
                    Reservation.starts_at,
                    Reservation.ends_at,
                    Reservation.status,
                    Reservation.external_event_id,
                )
                .where(Reservation.id == reservation_id)
                .with_for_update()
            )
        ).first()
        if row is None or row.external_event_id is not None:
            return False
        same = (
            row.staff_id == staff_id
            and (row.starts_at, row.ends_at) == span
            and row.status in _LIVE
        )
        await session.execute(
            sa.update(Reservation)
            .where(Reservation.id == reservation_id)
            .values(external_event_id=ref if same else f"{EVENT_MOVED}{ref}")
        )
    return True


async def _remove_events(
    session: AsyncSession,
    ctx: Ctx,
    gateway: GoogleCalendarGateway,
    conn: Connection,
    calendars: Mapping[uuid.UUID, str],
    now: datetime,
    errors: dict[uuid.UUID, str],
) -> int:
    """Borra los eventos que sobran: los de reservas que ya no están vivas y los de las
    movidas, cada uno del calendario donde vive."""
    rows = (
        await session.execute(
            sa.select(Reservation.id, Reservation.staff_id, Reservation.external_event_id).where(
                Reservation.external_event_id.is_not(None),
                Reservation.ends_at > now - REMOVAL_WINDOW,
                sa.or_(
                    Reservation.status.in_(_GONE),
                    Reservation.external_event_id.like(f"{EVENT_MOVED}%"),
                ),
            )
        )
    ).all()
    removed = 0
    for reservation_id, staff_id, stored in rows:
        ref = _parse_ref(stored)
        calendar_id = ref.calendar_id or (calendars.get(staff_id) if staff_id else None)
        if calendar_id is None:
            continue
        try:
            await gateway.delete_busy(conn, calendar_id, ref.event_id)
        except Exception as exc:
            _log_write_failure(ctx, staff_id, reservation_id, "delete", exc)
            if staff_id is not None:
                errors.setdefault(staff_id, _failure(exc, ERROR_WRITE))
            continue
        await _save_removed(ctx, reservation_id, stored)
        removed += 1
    return removed


async def _write_events(
    session: AsyncSession,
    ctx: Ctx,
    gateway: GoogleCalendarGateway,
    conn: Connection,
    staff_id: uuid.UUID,
    calendar_id: str,
    now: datetime,
    errors: dict[uuid.UUID, str],
) -> int:
    """Escribe las reservas vivas de una persona que aún no tienen evento."""
    rows = (
        await session.execute(
            sa.select(Reservation.id, Reservation.starts_at, Reservation.ends_at).where(
                Reservation.staff_id == staff_id,
                Reservation.status.in_(_LIVE),
                Reservation.ends_at > now,
                Reservation.external_event_id.is_(None),
            )
        )
    ).all()
    written = 0
    for reservation_id, starts_at, ends_at in rows:
        try:
            event_id = await gateway.create_busy(
                conn, calendar_id, starts_at, ends_at, f"{MARK}{reservation_id}"
            )
        except Exception as exc:
            _log_write_failure(ctx, staff_id, reservation_id, "create", exc)
            code = _failure(exc, ERROR_WRITE)
            errors.setdefault(staff_id, code)
            if code in _NEEDS_A_PERSON:
                break  # las demás de este calendario fallarían igual
            continue
        if event_id == UNKNOWN_EVENT:
            log.error(
                "reservation_calendar.event_without_id",
                tenant_id=str(ctx.tenant_id),
                staff_id=str(staff_id),
                reservation_id=str(reservation_id),
            )
            errors.setdefault(staff_id, ERROR_WRITE)
        kept = await _save_written(
            ctx, reservation_id, staff_id, calendar_id, event_id, (starts_at, ends_at)
        )
        if kept:
            written += 1
        elif event_id != UNKNOWN_EVENT:
            await _drop_spare(ctx, gateway, conn, staff_id, reservation_id, calendar_id, event_id)
    return written


async def _drop_spare(
    ctx: Ctx,
    gateway: GoogleCalendarGateway,
    conn: Connection,
    staff_id: uuid.UUID,
    reservation_id: uuid.UUID,
    calendar_id: str,
    event_id: str,
) -> None:
    try:
        await gateway.delete_busy(conn, calendar_id, event_id)
    except Exception as exc:
        _log_write_failure(ctx, staff_id, reservation_id, "delete", exc)


def _log_write_failure(
    ctx: Ctx,
    staff_id: uuid.UUID | None,
    reservation_id: uuid.UUID,
    operation: str,
    exc: Exception,
) -> None:
    log.warning(
        "reservation_calendar.write_failed",
        tenant_id=str(ctx.tenant_id),
        staff_id=str(staff_id) if staff_id else None,
        reservation_id=str(reservation_id),
        operation=operation,
        error_kind=_failure(exc, ERROR_WRITE),
        error_type=type(exc).__name__,
    )


async def _our_events(session: AsyncSession) -> set[str]:
    """Los eventos que son reservas nuestras, de quien sean ahora: uno movido a otra
    persona sigue en el calendario de la primera hasta que se borre, y no es un ocupado."""
    stored = (
        await session.execute(
            sa.select(Reservation.external_event_id).where(
                Reservation.external_event_id.is_not(None)
            )
        )
    ).scalars()
    return {_parse_ref(s).event_id for s in stored if s}


async def _expire_busy(
    session: AsyncSession, ctx: Ctx, staff_id: uuid.UUID, code: str, now: datetime
) -> None:
    """No se pudo leer. Lo que no se arregla solo se quita ya; lo demás, al caducar."""
    if code in _NEEDS_A_PERSON:
        result = await session.execute(
            sa.text("DELETE FROM reservation_busy WHERE staff_id = :s AND ends_at > :now"),
            {"s": staff_id, "now": now},
        )
    else:
        result = await session.execute(
            sa.text("DELETE FROM reservation_busy WHERE staff_id = :s AND synced_at < :limit"),
            {"s": staff_id, "limit": now - BUSY_STALE_AFTER},
        )
    gone = _rowcount(result)
    if gone:
        log.warning(
            "reservation_calendar.busy_dropped",
            tenant_id=str(ctx.tenant_id),
            staff_id=str(staff_id),
            dropped=gone,
            reason=code,
        )


async def _read_busy(
    session: AsyncSession,
    ctx: Ctx,
    gateway: GoogleCalendarGateway,
    conn: Connection,
    staff_id: uuid.UUID,
    calendar_id: str,
    ours: set[str],
    now: datetime,
    errors: dict[uuid.UUID, str],
) -> int:
    """Cambia el ocupado futuro de una persona por lo que dice ahora su calendario."""
    try:
        intervals = await gateway.busy(conn, calendar_id, now, now + SYNC_AHEAD, tz=ctx.tz)
    except Exception as exc:
        code = _failure(exc, ERROR_READ)
        log.warning(
            "reservation_calendar.read_failed",
            tenant_id=str(ctx.tenant_id),
            staff_id=str(staff_id),
            error_kind=code,
            error_type=type(exc).__name__,
        )
        errors[staff_id] = code
        await _expire_busy(session, ctx, staff_id, code, now)
        return 0
    await session.execute(
        sa.text("DELETE FROM reservation_busy WHERE staff_id = :s AND ends_at > :now"),
        {"s": staff_id, "now": now},
    )
    count = 0
    for b in intervals:
        if b.event_id is not None and b.event_id in ours:
            continue  # nuestro «Ocupado»: ya es una reserva
        if b.ends_at <= b.starts_at:
            continue  # Google los permite; la tabla, no
        await session.execute(
            sa.text(
                "INSERT INTO reservation_busy (tenant_id, staff_id, starts_at, ends_at, synced_at) "
                "VALUES (:t, :s, :a, :b, :now)"
            ),
            {"t": ctx.tenant_id, "s": staff_id, "a": b.starts_at, "b": b.ends_at, "now": now},
        )
        count += 1
    return count


async def _record_outcome(
    session: AsyncSession,
    calendars: Mapping[uuid.UUID, str],
    errors: Mapping[uuid.UUID, str],
    now: datetime,
) -> None:
    """``last_sync_at`` es la última pasada en la que salió todo; ``last_error``, lo que
    falló en esta."""
    for staff_id in calendars:
        code = errors.get(staff_id)
        if code is None:
            await session.execute(
                sa.text(
                    "UPDATE reservation_staff_calendars SET last_sync_at = :now, last_error = NULL "
                    "WHERE staff_id = :s"
                ),
                {"now": now, "s": staff_id},
            )
        else:
            await session.execute(
                sa.text(
                    "UPDATE reservation_staff_calendars SET last_error = :e WHERE staff_id = :s"
                ),
                {"e": code, "s": staff_id},
            )


async def sync_tenant(
    session: AsyncSession,
    ctx: Ctx,
    gateway: GoogleCalendarGateway,
    conn: Connection,
    *,
    now: datetime,
) -> dict[str, int]:
    """Una pasada, bajo la RLS del cliente. Primero se escribe: así lo que se lee ya
    incluye los eventos nuevos y no los borrados, y un fallo al leer no para nada."""
    stats = {"busy": 0, "written": 0, "deleted": 0}
    calendars = await _mappings(session)
    errors: dict[uuid.UUID, str] = {}
    stats["deleted"] = await _remove_events(session, ctx, gateway, conn, calendars, now, errors)
    for staff_id, calendar_id in calendars.items():
        stats["written"] += await _write_events(
            session, ctx, gateway, conn, staff_id, calendar_id, now, errors
        )
    ours = await _our_events(session)
    for staff_id, calendar_id in calendars.items():
        stats["busy"] += await _read_busy(
            session, ctx, gateway, conn, staff_id, calendar_id, ours, now, errors
        )
    await _record_outcome(session, calendars, errors, now)
    await session.flush()
    return stats


async def set_staff_calendar(
    session: AsyncSession,
    ctx: Ctx,
    staff_id: uuid.UUID,
    calendar_id: str | None,
    calendar_name: str | None,
) -> None:
    """Asocia o suelta un calendario. Los eventos de las reservas por venir que viven en
    otro calendario quedan pendientes de borrar: si no, se quedarían allí para siempre,
    bloqueando a alguien y sin moverse con la reserva."""
    stale = (
        "UPDATE reservations SET external_event_id = :moved || external_event_id "
        "WHERE staff_id = :s AND external_event_id IS NOT NULL AND ends_at > now() "
        "AND left(external_event_id, length(:moved)) <> :moved"
    )
    if calendar_id is None:
        await session.execute(sa.text(stale), {"s": staff_id, "moved": EVENT_MOVED})
        await session.execute(
            sa.text("DELETE FROM reservation_staff_calendars WHERE staff_id = :s"), {"s": staff_id}
        )
        await session.execute(
            sa.text("DELETE FROM reservation_busy WHERE staff_id = :s"), {"s": staff_id}
        )
        return
    await session.execute(
        sa.text(f"{stale} AND left(external_event_id, length(:keep)) <> :keep"),
        {"s": staff_id, "moved": EVENT_MOVED, "keep": f"{calendar_id} "},
    )
    await session.execute(
        sa.text(
            "INSERT INTO reservation_staff_calendars (tenant_id, staff_id, calendar_id, calendar_name) "
            "VALUES (:t, :s, :c, :n) ON CONFLICT (tenant_id, staff_id) DO UPDATE SET "
            "calendar_id = EXCLUDED.calendar_id, calendar_name = EXCLUDED.calendar_name, "
            "last_sync_at = NULL, last_error = NULL"
        ),
        {"t": ctx.tenant_id, "s": staff_id, "c": calendar_id, "n": calendar_name},
    )


def default_gateway() -> GoogleCalendarGateway:
    from nexus_api.services.connectors.runtime import get_composio_client

    return ComposioGoogleCalendar(get_composio_client())


__all__ = [
    "BUSY_STALE_AFTER",
    "ERROR_AUTH",
    "ERROR_CALENDAR_GONE",
    "ERROR_CONNECTION",
    "ERROR_READ",
    "ERROR_WRITE",
    "MARK",
    "MAX_PAGES",
    "Busy",
    "ComposioGoogleCalendar",
    "Connection",
    "GoogleCalendarError",
    "GoogleCalendarGateway",
    "connection_lost",
    "connection_of",
    "connection_state",
    "default_gateway",
    "has_work",
    "set_staff_calendar",
    "sync_tenant",
]
