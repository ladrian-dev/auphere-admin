"""Reservas P3 — el Google Calendar de cada profesional (spec 043, requisitos 10, 12 y 13).

Reservas es la fuente de la verdad (Luis, 2026-11-04). Google es un espejo y una fuente
de «ocupado»: lo hace **el sistema**, no el agente, y cada profesional conecta **su
cuenta** desde el panel, con una identidad propia en el proveedor
(``tenant_<slug>_staff_<id>``).

**La conexión de Google del negocio (spec 023) solo se lee** (R12.13). Las citas que un agente
tomó allí no se importan: un evento no dice de qué cliente es. Pero esa hora ya está dada, así
que sigue bloqueando a quien aún no conectó el suyo, hasta que cada uno lo conecte. Nunca se
escribe en ella.

Dos sentidos, y en los dos lo mínimo:

- **entra** el «ocupado» de cada calendario: solo inicio y fin (``reservation_busy``);
  ni título ni asistentes;
- **sale** cada reserva viva de esa persona como un evento **«Ocupado»**, sin
  nombre del cliente ni servicio; se mueve o se borra con la reserva.

**Lo que cambia en Google vuelve bien** (R13). Un evento de la persona bloquea, y si pisa
una reserva sale como choque. Nuestro «Ocupado» borrado o movido a mano se vuelve a
escribir donde dice la reserva: la cita de un cliente no se mueve desde otro calendario.

**Una pasada, tres partes que no dependen unas de otras**: quitar lo que sobra,
escribir lo que falta y leer el ocupado. Si una falla, las otras siguen, y lo que le
pasa a un profesional no toca a los demás.

**Lo que se escribe en Google se apunta de inmediato**, en su propia transacción
y reserva por reserva. Google no se deshace con un ``ROLLBACK``: si un fallo se
llevara los ids, cada pasada repetiría sus «Ocupado». Por eso **la transacción de la pasada
nunca escribe en ``reservations``**: si tuviera una fila sin confirmar, la otra conexión se
quedaría esperándola para siempre, y Postgres no lo ve como un interbloqueo porque una de
las dos espera en Python. Todo lo de esa tabla pasa por :func:`_own_tx`, con ``lock_timeout``.

**Lo nuestro se reconoce por el id que guarda la reserva y, si se perdió, por su marca**: la
descripción ``auphere:reserva:<id>`` de un evento que organiza la propia cuenta y de una
reserva que existe en este cliente. Sin eso, un evento viejo o sin id volvería como ocupado
ajeno y la cita chocaría consigo misma.

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
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from typing import Any, Final, Protocol

import sqlalchemy as sa
import structlog
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AgentConnectorActivation,
    Connector,
    Reservation,
    Tenant,
    TenantConnector,
)
from nexus_api.db.models.connector import TenantConnectorStatus
from nexus_api.services.connectors.composio_client import (
    ComposioAuthExpired,
    ComposioError,
    ComposioNotFound,
)
from nexus_api.services.reservations.core import EVENT_MOVED, Ctx, active_staff

log = structlog.get_logger(__name__)

#: Marca de nuestros propios eventos «Ocupado». Lo nuestro se reconoce antes por el id del
#: evento que guarda la reserva (``external_event_id``). La marca sola no basta: cualquiera
#: puede escribirla en una invitación y liberar así ese hueco (/cso, apéndice). Por eso solo
#: cuenta en lo que organiza la propia cuenta y con el id de una reserva de este cliente.
MARK = "auphere:reserva:"
_MARKED = re.compile(re.escape(MARK) + r"([0-9a-fA-F-]{36})\b")
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
#: Lo más que espera una escritura en ``reservations``: quien tenga la fila la suelta en
#: milisegundos, y un cron secuencial no puede quedarse esperando a nadie.
LOCK_TIMEOUT: str = "5s"
#: Un evento se crea en minutos: una cita importada con segundos no está movida.
_SAME_SPAN: Final = timedelta(seconds=60)
_TEXT_MAX: Final = 255

#: Lo que ``last_error`` guarda y la API enseña: códigos nuestros, que la pantalla
#: traduce. El texto del proveedor no pasa de aquí: puede traer un token o el título
#: de la cita de otra persona.
ERROR_CONNECTION: Final = "connection"
ERROR_AUTH: Final = "auth"
ERROR_CALENDAR_GONE: Final = "calendar_gone"
ERROR_READ: Final = "read"
ERROR_WRITE: Final = "write"
#: La cuenta conectada no da un calendario que usar: elegir uno (``needs_calendar``).
ERROR_CALENDAR_IN_USE: Final = "calendar_in_use"
ERROR_NO_CALENDAR: Final = "no_calendar"

#: Autorizó otra cuenta y Google no le deja leer. Sigue con la anterior, y durante
#: ``PENDING_EXPIRES_AFTER`` la pantalla lo dice: si no, parecería que la nueva entró.
ERROR_NEW_ACCOUNT_REFUSED: Final = "new_account_refused"

#: Cuánto vive un enlace sin terminar, y cuánto se insiste en quitar los eventos de quien
#: se desconectó. Después se da por perdido: nadie debería esperar a un proveedor caído.
PENDING_EXPIRES_AFTER: Final = timedelta(hours=1)
DISCONNECT_GIVES_UP_AFTER: Final = timedelta(hours=1)
#: Cuánto espera una reserva movida a poder borrar su evento viejo antes de escribir el nuevo.
#: Esperar evita un duplicado; esperar siempre la dejaría fuera del calendario de quien la atiende.
REMOVE_WAITS_AT_MOST: Final = timedelta(hours=1)

#: Lo que el proveedor dice de una autorización que ya no va a terminar. ``INITIATED`` e
#: ``INITIALIZING`` siguen esperando (``composio_client.types.connected_account_*``).
_DID_NOT_FINISH: Final = frozenset({"EXPIRED", "FAILED", "INACTIVE", "NOT_FOUND", "REVOKED"})

#: De dónde viene cada fila de ``reservation_busy``.
BUSY_GOOGLE: Final = "google"
BUSY_BUSINESS: Final = "business"

#: ``connection_status``.
PENDING: Final = "pending"
CONNECTED: Final = "connected"
NEEDS_REAUTH: Final = "needs_reauth"
DISCONNECTING: Final = "disconnecting"

#: Lo que no se arregla solo: seguir creyendo ese ocupado solo bloquea huecos.
_NEEDS_A_PERSON: Final = frozenset({ERROR_AUTH, ERROR_CALENDAR_GONE})

#: El evento se creó en Google y su respuesta no trae el id. Se guarda para no volver a
#: crearlo cada dos minutos; la lectura siguiente lo reconoce por su marca y lo adopta.
UNKNOWN_EVENT: Final = "?"

_LIVE: Final = ("pending", "confirmed")
_GONE: Final = ("cancelled", "noshow")
_MAX_REF: Final = 255 - len(EVENT_MOVED)

#: Google responde 403 también al pasarse de cuota, y eso se arregla solo: se mira
#: antes que el permiso.
_RATE_LIMIT = re.compile(r"\b429\b|rate.?limit|quota|usage.?limit", re.IGNORECASE)
_NOT_FOUND = re.compile(r"\b(404|410)\b|not.?found|been deleted", re.IGNORECASE)
_THE_EVENT_IS_GONE = re.compile(r"\b(404|410)\b|been deleted", re.IGNORECASE)
#: «No encontrado» no siempre es el evento. Darlo por borrado soltaría el id con el evento
#: todavía en Google.
_THE_CONNECTION = re.compile(r"connected.?account|connection|auth.?config", re.IGNORECASE)
_THE_TOOL = re.compile(r"\btool(kit)?\b", re.IGNORECASE)
_REFUSED = re.compile(
    r"\b(401|403)\b|invalid_grant|invalid.?credentials|invalid authentication|"
    r"unauthori[sz]ed|forbidden|insufficient|expired",
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
        if _THE_CONNECTION.search(text):
            return "auth"
        if _THE_TOOL.search(text) and not _THE_EVENT_IS_GONE.search(text):
            return "other"
        return "not_found"
    if _REFUSED.search(text):
        return "auth"
    return "other"


class CalendarError(Exception):
    """Lo que la API responde a quien conecta o elige un calendario."""

    def __init__(self, status: int, code: str, **info: Any) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.info = info


@dataclass(frozen=True)
class Connection:
    user_id: str
    connection_id: str


@dataclass(frozen=True)
class StaffCalendar:
    """La fila de una persona: su conexión y el calendario que usa."""

    staff_id: uuid.UUID
    calendar_id: str | None
    connection: Connection | None
    status: str
    since: datetime
    #: La conexión que funcionaba mientras se autoriza otra: se suelta cuando la nueva ya
    #: está, porque es la única que llega a los eventos de la cuenta vieja.
    previous: Connection | None = None

    @property
    def syncs(self) -> bool:
        return self.status == CONNECTED and self.connection is not None and bool(self.calendar_id)


@dataclass(frozen=True)
class Busy:
    starts_at: datetime
    ends_at: datetime
    event_id: str | None = None
    #: El id de reserva de su marca, si la lleva y la organiza la propia cuenta.
    marker: str | None = None


class GoogleCalendarGateway(Protocol):
    async def link(self, user_id: str, callback_url: str) -> tuple[str, str]:
        """``(connection_id, redirect_url)`` de una autorización nueva para ``user_id``."""
        ...

    async def account_state(self, connection_id: str) -> str:
        """``ACTIVE``, ``EXPIRED``, ``FAILED``, ``NOT_FOUND`` o lo que diga el proveedor."""
        ...

    async def revoke(self, connection_id: str) -> None: ...

    async def list_calendars(self, conn: Connection) -> list[dict[str, Any]]: ...

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


#: Lo que Google apunta en el calendario y no es tiempo de nadie.
_NEVER_BLOCKS: Final = frozenset({"birthday", "workingLocation"})


def _blocks(ev: dict[str, Any]) -> bool:
    """¿Ocupa de verdad? No lo cancelado, ni una invitación que la persona rechazó, ni lo que
    Google apunta por su cuenta (cumpleaños, dónde trabaja). Lo de todo el día sí, aunque diga
    que está libre: Google lo crea así y es la forma de cerrar un día. Lo que tiene hora y
    está marcado como disponible, no (R13.4)."""
    if ev.get("status") == "cancelled" or ev.get("eventType") in _NEVER_BLOCKS:
        return False
    attendees = ev.get("attendees")
    if isinstance(attendees, list):
        for person in attendees:
            if (
                isinstance(person, dict)
                and person.get("self")
                and person.get("responseStatus") == "declined"
            ):
                return False
    start = ev.get("start")
    if isinstance(start, dict) and start.get("date") and not start.get("dateTime"):
        return True
    return ev.get("transparency") != "transparent"


def _marker_of(ev: dict[str, Any]) -> str | None:
    """El id de reserva de su marca. Una invitación de fuera no es nuestra, diga lo que diga."""
    organizer = ev.get("organizer")
    if isinstance(organizer, dict) and not organizer.get("self"):
        return None
    description = ev.get("description")
    found = _MARKED.search(description) if isinstance(description, str) else None
    if found is None:
        return None
    try:
        return str(uuid.UUID(found.group(1)))
    except ValueError:
        return None


class ComposioGoogleCalendar:
    """La puerta real, sobre el cliente del proveedor de consentimientos."""

    def __init__(self, client: Any) -> None:
        self._client = client

    async def link(self, user_id: str, callback_url: str) -> tuple[str, str]:
        auth_config_id = await self._client.find_auth_config_id(TOOLKIT)
        request = await self._client.link_account(
            user_id=user_id,
            auth_config_id=auth_config_id,
            callback_url=callback_url,
            # La fila dice qué conexión se usa: una vieja que siga activa en el proveedor
            # no puede impedir volver a conectar a un profesional.
            allow_multiple=True,
        )
        return request.connection_id, request.redirect_url

    async def account_state(self, connection_id: str) -> str:
        try:
            account = await self._client.get_account(connection_id)
        except ComposioNotFound:
            return "NOT_FOUND"
        return str(account.status or "").upper()

    async def revoke(self, connection_id: str) -> None:
        try:
            await self._client.revoke_account(connection_id)
        except ComposioNotFound:
            return  # ya no estaba

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

    async def list_calendars(self, conn: Connection) -> list[dict[str, Any]]:
        """Los calendarios de la cuenta **en los que se puede escribir**: uno de solo
        lectura, como el de festivos, rechazaría cada «Ocupado» para siempre. ``primary``
        marca el principal, cuyo id es la dirección de la cuenta."""
        items = await self._pages(
            conn, "GOOGLECALENDAR_LIST_CALENDARS", {}, "items", "calendars", token_arg="page_token"
        )
        return [
            {
                "id": str(c.get("id")),
                "name": str(c.get("summary") or c.get("id")),
                "primary": bool(c.get("primary")),
            }
            for c in items
            if isinstance(c, dict)
            and c.get("id")
            and len(str(c.get("id"))) <= _TEXT_MAX
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
            if not isinstance(ev, dict) or ev.get("status") == "cancelled":
                continue
            marker = _marker_of(ev)  # lo nuestro se mira aunque no bloquee: quizá haya que quitarlo
            if marker is None and not _blocks(ev):
                continue
            span = _span(ev, tz)
            if span is not None:
                ev_id = ev.get("id")
                out.append(Busy(span[0], span[1], str(ev_id) if ev_id else None, marker))
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
        # Sin error, se creó aunque no diga cuál: la lectura lo reconoce por su marca. Repetirlo
        # sería un evento más cada dos minutos.
        return str(event_id) if event_id else UNKNOWN_EVENT

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
# ``external_event_id`` guarda ``<profesional> <calendario> <evento>``: una reserva puede
# cambiar de persona, y una persona de calendario o de cuenta, y el evento sigue donde se
# escribió, al alcance de la conexión de quien lo escribió. Ni los ids de calendario ni
# los de evento de Google llevan espacios. Con ``EVENT_MOVED`` delante está pendiente de
# borrar: lo pone ``move_booking``, en la transacción de la reserva.


@dataclass(frozen=True)
class _EventRef:
    owner: uuid.UUID | None
    calendar_id: str | None
    event_id: str


def _event_ref(owner: uuid.UUID, calendar_id: str, event_id: str) -> str:
    joined = f"{owner} {calendar_id} {event_id}"
    return joined if len(joined) <= _MAX_REF else event_id[:_MAX_REF]


def _parse_ref(stored: str) -> _EventRef:
    parts = stored.removeprefix(EVENT_MOVED).split(" ")
    if len(parts) == 3:
        try:
            return _EventRef(uuid.UUID(parts[0]), parts[1], parts[2])
        except ValueError:
            return _EventRef(None, parts[1], parts[2])
    if len(parts) == 2:
        return _EventRef(None, parts[0], parts[1])
    return _EventRef(None, None, parts[-1])


# ── la conexión de cada profesional ─────────────────────────────────────────


def staff_user_id(tenant_slug: str, staff_id: uuid.UUID) -> str:
    """Su identidad en el proveedor: nunca la del negocio ni la de otro profesional."""
    return f"tenant_{tenant_slug}_staff_{staff_id}"


async def staff_calendars(session: AsyncSession) -> list[StaffCalendar]:
    """Las filas del cliente de esta transacción, la primera la que antes empezó. No
    recibe el cliente: lo pone la RLS."""
    rows = await session.execute(
        sa.text(
            "SELECT staff_id, calendar_id, connection_id, connection_user_id, "
            "connection_status, status_since, previous_connection_id, previous_user_id "
            "FROM reservation_staff_calendars "
            # Si dos autorizan la misma cuenta, el calendario es del primero que lo pidió.
            "ORDER BY status_since, staff_id"
        )
    )
    return [
        StaffCalendar(
            staff_id=r.staff_id,
            calendar_id=r.calendar_id,
            connection=Connection(r.connection_user_id, r.connection_id)
            if r.connection_id and r.connection_user_id
            else None,
            status=r.connection_status,
            since=r.status_since,
            previous=Connection(r.previous_user_id, r.previous_connection_id)
            if r.previous_connection_id and r.previous_user_id
            else None,
        )
        for r in rows.all()
    ]


async def staff_calendar(session: AsyncSession, staff_id: uuid.UUID) -> StaffCalendar | None:
    for row in await staff_calendars(session):
        if row.staff_id == staff_id:
            return row
    return None


async def start_connection(
    session: AsyncSession,
    ctx: Ctx,
    gateway: GoogleCalendarGateway,
    staff_id: uuid.UUID,
    *,
    callback_url: str,
    now: datetime,
) -> str:
    """Pide la autorización de un profesional y devuelve el enlace: solo a quien la pidió.
    Volver a conectar conserva su calendario y su conexión hasta que la nueva funcione; el
    enlace caduca solo."""
    row = await staff_calendar(session, staff_id)
    if row is not None and row.status == DISCONNECTING:
        raise CalendarError(409, "calendar_disconnecting")
    if row is not None and row.syncs and await _is_healthy(session, staff_id):
        raise CalendarError(409, "calendar_already_connected")
    slug = await session.scalar(sa.select(Tenant.slug).where(Tenant.id == ctx.tenant_id))
    if not slug:
        raise CalendarError(409, "calendar_unavailable")
    user_id = staff_user_id(str(slug), staff_id)
    try:
        connection_id, redirect_url = await gateway.link(user_id, callback_url)
    except (ComposioError, GoogleCalendarError) as exc:
        log.warning(
            "reservation_calendar.link_failed",
            tenant_id=str(ctx.tenant_id),
            staff_id=str(staff_id),
            error_type=type(exc).__name__,
        )
        raise CalendarError(409, "calendar_unavailable") from None
    previous = row.previous if row is not None else None
    if row is not None and row.connection is not None:
        if row.status == CONNECTED:
            if previous is not None:
                await _revoke_quietly(ctx, gateway, staff_id, previous.connection_id)
            previous = row.connection
        else:
            # Un enlace sin terminar o una conexión caída no sirven a nadie; la buena, si la
            # hay, sigue.
            await _revoke_quietly(ctx, gateway, staff_id, row.connection.connection_id)
    # Mientras espera nadie va a refrescar lo que leímos: con datos viejos no se bloquea.
    await _forget_own_busy(session, staff_id)
    await session.execute(
        sa.text(
            "INSERT INTO reservation_staff_calendars (tenant_id, staff_id, connection_id, "
            "connection_user_id, connection_status, status_since, previous_connection_id, "
            "previous_user_id) VALUES (:t, :s, :c, :u, :pending, :now, :pc, :pu) "
            "ON CONFLICT (tenant_id, staff_id) DO UPDATE SET "
            "connection_id = EXCLUDED.connection_id, "
            "connection_user_id = EXCLUDED.connection_user_id, "
            "connection_status = EXCLUDED.connection_status, "
            "status_since = EXCLUDED.status_since, "
            "previous_connection_id = EXCLUDED.previous_connection_id, "
            "previous_user_id = EXCLUDED.previous_user_id, last_error = NULL"
        ),
        {
            "t": ctx.tenant_id,
            "s": staff_id,
            "c": connection_id,
            "u": user_id,
            "pending": PENDING,
            "now": now,
            "pc": previous.connection_id if previous else None,
            "pu": previous.user_id if previous else None,
        },
    )
    return redirect_url


async def _forget_own_busy(session: AsyncSession, staff_id: uuid.UUID) -> None:
    """Lo leído de su calendario. Lo del negocio sigue: ninguna de estas dos cosas lo cambia."""
    await session.execute(
        sa.text("DELETE FROM reservation_busy WHERE staff_id = :s AND source = :own"),
        {"s": staff_id, "own": BUSY_GOOGLE},
    )


async def _is_healthy(session: AsyncSession, staff_id: uuid.UUID) -> bool:
    """Conectar otra vez es la salida de cualquier fallo: solo se niega a quien va bien, para
    que nadie cambie sin querer la cuenta de un profesional."""
    error = await session.scalar(
        sa.text("SELECT last_error FROM reservation_staff_calendars WHERE staff_id = :s"),
        {"s": staff_id},
    )
    return error is None


async def _revoke_quietly(
    ctx: Ctx, gateway: GoogleCalendarGateway, staff_id: uuid.UUID, connection_id: str
) -> None:
    """Soltar una conexión no puede dejar a nadie atascado: si el proveedor falla, ya no
    se usa, y queda en el registro para quitarla a mano."""
    try:
        await gateway.revoke(connection_id)
    except Exception as exc:
        log.warning(
            "reservation_calendar.revoke_failed",
            tenant_id=str(ctx.tenant_id),
            staff_id=str(staff_id),
            error_type=type(exc).__name__,
        )


async def _settle_pending(
    session: AsyncSession,
    ctx: Ctx,
    gateway: GoogleCalendarGateway,
    row: StaffCalendar,
    now: datetime,
) -> None:
    """¿Terminó la autorización? Si sí, queda conectada y con calendario, si se puede. Si
    falló o caducó, la fila vuelve a como estaba."""
    assert row.connection is not None
    try:
        state = await gateway.account_state(row.connection.connection_id)
    except Exception as exc:
        log.warning(
            "reservation_calendar.account_state_failed",
            tenant_id=str(ctx.tenant_id),
            staff_id=str(row.staff_id),
            error_type=type(exc).__name__,
        )
        # Sin respuesta no se decide nada: se mira en la pasada siguiente, pero no para siempre.
        if now - row.since >= PENDING_EXPIRES_AFTER:
            await _give_back(session, ctx, gateway, row, now)
        return
    if state == "ACTIVE":
        await _activated(session, ctx, gateway, row, now)
        return
    if state not in _DID_NOT_FINISH and now - row.since < PENDING_EXPIRES_AFTER:
        return
    await _give_back(session, ctx, gateway, row, now)


async def _give_back(
    session: AsyncSession,
    ctx: Ctx,
    gateway: GoogleCalendarGateway,
    row: StaffCalendar,
    now: datetime,
    *,
    error: str = ERROR_CONNECTION,
) -> None:
    """La autorización no llegó a nada: vuelve a la conexión que tenía, si la tenía. Sin ella,
    conserva su calendario y lo dice; sin calendario tampoco, la fila sobra."""
    assert row.connection is not None
    await _revoke_quietly(ctx, gateway, row.staff_id, row.connection.connection_id)
    if row.previous is not None:
        await session.execute(
            sa.text(
                "UPDATE reservation_staff_calendars SET connection_status = :s, "
                "connection_id = :c, connection_user_id = :u, previous_connection_id = NULL, "
                "previous_user_id = NULL, status_since = :now, last_error = :e "
                "WHERE staff_id = :staff"
            ),
            {
                "s": CONNECTED,
                "c": row.previous.connection_id,
                "u": row.previous.user_id,
                "now": now,
                "e": ERROR_NEW_ACCOUNT_REFUSED if error == ERROR_AUTH else None,
                "staff": row.staff_id,
            },
        )
    elif row.calendar_id or error != ERROR_CONNECTION:
        await session.execute(
            sa.text(
                "UPDATE reservation_staff_calendars SET connection_status = :s, "
                "connection_id = NULL, connection_user_id = NULL, status_since = :now, "
                "last_error = :e WHERE staff_id = :staff"
            ),
            {"s": NEEDS_REAUTH, "now": now, "e": error, "staff": row.staff_id},
        )
    else:
        await session.execute(
            sa.text("DELETE FROM reservation_staff_calendars WHERE staff_id = :s"),
            {"s": row.staff_id},
        )


async def _activated(
    session: AsyncSession,
    ctx: Ctx,
    gateway: GoogleCalendarGateway,
    row: StaffCalendar,
    now: datetime,
) -> None:
    assert row.connection is not None
    try:
        calendars = await gateway.list_calendars(row.connection)
    except Exception as exc:
        code = _failure(exc, ERROR_READ)
        log.warning(
            "reservation_calendar.read_failed",
            tenant_id=str(ctx.tenant_id),
            staff_id=str(row.staff_id),
            error_kind=code,
            error_type=type(exc).__name__,
        )
        # Autorizó y Google no le deja leer: no se arregla esperando. Si es que no contesta, se
        # espera, sin decir que no terminó, pero no para siempre.
        if code == ERROR_AUTH:
            await _give_back(session, ctx, gateway, row, now, error=ERROR_AUTH)
        elif now - row.since >= PENDING_EXPIRES_AFTER:
            await _give_back(session, ctx, gateway, row, now)
        return
    primary = next((c for c in calendars if c.get("primary")), None)
    label = str(primary["id"])[:_TEXT_MAX] if primary is not None else None
    chosen, name, error = await _pick(session, row, calendars, primary)
    update = sa.text(
        "UPDATE reservation_staff_calendars SET connection_status = :s, status_since = :now, "
        "account_label = :label, calendar_id = :c, calendar_name = :n, last_error = :e, "
        "previous_connection_id = NULL, previous_user_id = NULL, last_sync_at = NULL "
        "WHERE staff_id = :staff"
    )
    values = {
        "s": CONNECTED,
        "now": now,
        "label": label,
        "c": chosen,
        "n": name,
        "e": error,
        "staff": row.staff_id,
    }
    try:
        async with session.begin_nested():
            await session.execute(update, values)
    except IntegrityError:
        # Otro se lo quedó en este instante: el índice manda.
        chosen = None
        await session.execute(update, {**values, "c": None, "n": None, "e": ERROR_CALENDAR_IN_USE})
    await _bring_events_along(session, ctx, gateway, row, calendars, chosen, now)
    if row.previous is not None:
        await _revoke_quietly(ctx, gateway, row.staff_id, row.previous.connection_id)


async def _bring_events_along(
    session: AsyncSession,
    ctx: Ctx,
    gateway: GoogleCalendarGateway,
    row: StaffCalendar,
    calendars: list[dict[str, Any]],
    chosen: str | None,
    now: datetime,
) -> None:
    """Sus citas siguen a su cuenta nueva. Lo que está en un calendario al que esta llega se
    queda o se aparta para borrarlo con ella. Lo que no, se borra con la conexión vieja, si la
    hay, y se suelta para escribirlo de nuevo: esperar a que se pudiera borrar lo dejaría
    fuera de su calendario para siempre."""
    reachable = {str(c["id"]) for c in calendars}
    rows = await session.execute(
        sa.select(
            Reservation.id, Reservation.staff_id, Reservation.ends_at, Reservation.external_event_id
        ).where(
            Reservation.external_event_id.is_not(None),
            Reservation.ends_at > now - REMOVAL_WINDOW,
        )
    )
    for reservation_id, current, ends_at, stored in rows.all():
        ref = _parse_ref(stored)
        if (ref.owner or current) != row.staff_id:
            continue
        moved = stored.startswith(EVENT_MOVED)
        if not moved and ends_at <= now:
            continue  # lo pasado se queda en su calendario
        if ref.calendar_id in reachable:
            if not moved and chosen is not None and ref.calendar_id != chosen:
                await _swap_ref(ctx, reservation_id, stored, f"{EVENT_MOVED}{stored}")
            continue
        if row.previous is not None and ref.calendar_id and ref.event_id != UNKNOWN_EVENT:
            await _delete_quietly(
                ctx,
                gateway,
                row.previous,
                row.staff_id,
                reservation_id,
                ref.calendar_id,
                ref.event_id,
            )
        await _swap_ref(ctx, reservation_id, stored, None)


async def _pick(
    session: AsyncSession,
    row: StaffCalendar,
    calendars: list[dict[str, Any]],
    primary: dict[str, Any] | None,
) -> tuple[str | None, str | None, str | None]:
    """El calendario con el que queda: el que ya tenía si sigue en esta cuenta; si no, el
    principal, si nadie más del negocio lo usa. ``(id, nombre, error)``."""
    if row.calendar_id:
        kept = next((c for c in calendars if c["id"] == row.calendar_id), None)
        if kept is not None:
            return str(kept["id"]), str(kept["name"])[:_TEXT_MAX], None
    if primary is None:
        # Sin calendarios no hay nada que elegir; con ellos y sin principal, sí.
        return None, None, None if calendars else ERROR_NO_CALENDAR
    used_by = await _using(session, str(primary["id"]), row.staff_id)
    if used_by is not None:
        return None, None, ERROR_CALENDAR_IN_USE
    return str(primary["id"]), str(primary["name"])[:_TEXT_MAX], None


async def _using(session: AsyncSession, calendar_id: str, staff_id: uuid.UUID) -> str | None:
    """Quién del negocio usa ya ese calendario."""
    found = await session.scalar(
        sa.text(
            "SELECT s.name FROM reservation_staff_calendars c "
            "JOIN reservation_staff s ON s.tenant_id = c.tenant_id AND s.id = c.staff_id "
            "WHERE c.calendar_id = :c AND c.staff_id <> :s AND c.connection_status <> :gone"
        ),
        {"c": calendar_id, "s": staff_id, "gone": DISCONNECTING},
    )
    return str(found) if found is not None else None


async def settle_pending(
    session: AsyncSession, ctx: Ctx, gateway: GoogleCalendarGateway, *, now: datetime
) -> None:
    for row in await staff_calendars(session):
        if row.status == PENDING and row.connection is not None:
            await _settle_pending(session, ctx, gateway, row, now)


async def calendars_of(
    session: AsyncSession, gateway: GoogleCalendarGateway, staff_id: uuid.UUID
) -> list[dict[str, Any]]:
    """Los calendarios de la cuenta de ese profesional, con quién más los usa."""
    row = await staff_calendar(session, staff_id)
    if row is None or row.connection is None or row.status not in (CONNECTED, NEEDS_REAUTH):
        raise CalendarError(409, "calendar_not_connected")
    try:
        calendars = await gateway.list_calendars(row.connection)
    except Exception:
        raise CalendarError(409, "calendar_unavailable") from None
    return [{**c, "used_by": await _using(session, str(c["id"]), staff_id)} for c in calendars]


async def choose_calendar(
    session: AsyncSession, gateway: GoogleCalendarGateway, staff_id: uuid.UUID, calendar_id: str
) -> None:
    """Elige un calendario de **su** cuenta. Los eventos de sus reservas por venir que
    viven en otro quedan pendientes de borrar."""
    calendars = await calendars_of(session, gateway, staff_id)
    chosen = next((c for c in calendars if c.get("id") == calendar_id), None)
    if chosen is None:
        raise CalendarError(422, "unknown_calendar")
    if chosen.get("used_by"):
        raise CalendarError(409, "calendar_in_use", used_by=chosen["used_by"])
    await _events_leave_calendar(session, staff_id, keep=calendar_id)
    try:
        async with session.begin_nested():
            await session.execute(
                sa.text(
                    "UPDATE reservation_staff_calendars SET calendar_id = :c, calendar_name = :n, "
                    "last_sync_at = NULL, last_error = NULL WHERE staff_id = :s"
                ),
                {
                    "c": calendar_id,
                    "n": str(chosen.get("name") or calendar_id)[:_TEXT_MAX],
                    "s": staff_id,
                },
            )
    except IntegrityError:
        # Las dos pasaron la comprobación: el índice para a la segunda (R12.4).
        raise CalendarError(
            409, "calendar_in_use", used_by=await _using(session, calendar_id, staff_id)
        ) from None


async def _events_leave_calendar(
    session: AsyncSession, staff_id: uuid.UUID, keep: str | None
) -> None:
    """Marca para borrar los eventos por venir de esa persona, salvo los de ``keep``."""
    rows = await session.execute(
        sa.select(Reservation.id, Reservation.external_event_id).where(
            Reservation.external_event_id.is_not(None),
            Reservation.external_event_id.not_like(f"{EVENT_MOVED}%"),
            Reservation.staff_id == staff_id,
            Reservation.ends_at > sa.func.now(),
        )
    )
    for reservation_id, stored in rows.all():
        if keep is not None and _parse_ref(stored).calendar_id == keep:
            continue
        await session.execute(
            sa.update(Reservation)
            .where(Reservation.id == reservation_id)
            .values(external_event_id=f"{EVENT_MOVED}{stored}")
        )


async def disconnect(session: AsyncSession, staff_id: uuid.UUID, *, now: datetime) -> None:
    """Deja de bloquear al momento y la fila dice «sin conectar». Quitar sus eventos y
    revocar la conexión es de la pasada siguiente: hacen falta las dos cosas en ese orden,
    y son llamadas a Google que no caben en una petición."""
    row = await staff_calendar(session, staff_id)
    await _forget_own_busy(session, staff_id)
    if row is None:
        return
    await _events_leave_calendar(session, staff_id, keep=None)
    if row.connection is None:
        await session.execute(
            sa.text("DELETE FROM reservation_staff_calendars WHERE staff_id = :s"), {"s": staff_id}
        )
        return
    await session.execute(
        sa.text(
            "UPDATE reservation_staff_calendars SET connection_status = :s, status_since = :now, "
            "last_error = NULL WHERE staff_id = :staff"
        ),
        {"s": DISCONNECTING, "now": now, "staff": staff_id},
    )


async def _finish_disconnects(
    session: AsyncSession,
    ctx: Ctx,
    gateway: GoogleCalendarGateway,
    calendars: list[StaffCalendar],
    now: datetime,
    errors: Mapping[uuid.UUID, str],
) -> None:
    """Quien se desconectó y ya no tiene eventos que quitar: se revoca y la fila se va. Si
    ya no se puede borrar nada (permiso perdido, o lleva demasiado), se revoca igual."""
    for row in calendars:
        if row.status != DISCONNECTING or row.connection is None:
            continue
        left = await _events_owned_by(session, row.staff_id, now)
        stuck = errors.get(row.staff_id) in _NEEDS_A_PERSON or (
            now - row.since >= DISCONNECT_GIVES_UP_AFTER
        )
        if left and not stuck:
            continue
        for reservation_id, stored in left:
            await _swap_ref(ctx, reservation_id, stored, None)
        await _revoke_quietly(ctx, gateway, row.staff_id, row.connection.connection_id)
        if row.previous is not None:
            await _revoke_quietly(ctx, gateway, row.staff_id, row.previous.connection_id)
        await session.execute(
            sa.text("DELETE FROM reservation_staff_calendars WHERE staff_id = :s"),
            {"s": row.staff_id},
        )


async def _events_owned_by(
    session: AsyncSession, staff_id: uuid.UUID, now: datetime
) -> list[tuple[uuid.UUID, str]]:
    rows = await session.execute(
        sa.select(Reservation.id, Reservation.staff_id, Reservation.external_event_id).where(
            Reservation.external_event_id.like(f"{EVENT_MOVED}%"),
            Reservation.ends_at > now - REMOVAL_WINDOW,
        )
    )
    out: list[tuple[uuid.UUID, str]] = []
    for reservation_id, current, stored in rows.all():
        ref = _parse_ref(stored)
        if (ref.owner or current) == staff_id:
            out.append((reservation_id, stored))
    return out


async def _unhealthy_stop_blocking(
    session: AsyncSession, ctx: Ctx, calendars: list[StaffCalendar], now: datetime
) -> None:
    """La conexión de una persona no está sana: nadie va a refrescar su ocupado hasta que
    alguien la vuelva a conectar, así que deja de bloquear. Lo dice una vez, no cada dos
    minutos. Sus reservas sin escribir esperan a la vuelta."""
    for row in calendars:
        if row.status != NEEDS_REAUTH:
            continue
        told = await session.execute(
            sa.text(
                "UPDATE reservation_staff_calendars SET last_error = :e "
                "WHERE staff_id = :s AND last_error IS NULL"
            ),
            {"e": ERROR_CONNECTION, "s": row.staff_id},
        )
        dropped = await session.execute(
            sa.text(
                "DELETE FROM reservation_busy WHERE staff_id = :s AND ends_at > :now "
                "AND source = :own"
            ),
            {"s": row.staff_id, "now": now, "own": BUSY_GOOGLE},
        )
        changed, gone = _rowcount(told), _rowcount(dropped)
        if changed or gone:
            log.warning(
                "reservation_calendar.connection_unhealthy",
                tenant_id=str(ctx.tenant_id),
                staff_id=str(row.staff_id),
                dropped=gone,
            )


def _rowcount(result: Any) -> int:
    return int(getattr(result, "rowcount", 0) or 0)


async def has_work(session: AsyncSession, *, now: datetime) -> bool:
    """Hay algo que sincronizar: alguien con una fila, la agenda de Google del negocio, o
    eventos que quitar de un calendario que ya no es de nadie."""
    mapped = await session.scalar(sa.text("SELECT 1 FROM reservation_staff_calendars LIMIT 1"))
    if mapped is not None or (await _business_google(session)).connection is not None:
        return True
    # Lo que queda de una conexión que se quitó: alguien tiene que limpiarlo.
    leftover = await session.scalar(
        sa.text("SELECT 1 FROM reservation_busy WHERE source = :src AND ends_at > :now LIMIT 1"),
        {"src": BUSY_BUSINESS, "now": now},
    )
    if leftover is not None:
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


def _failure(exc: Exception, otherwise: str) -> str:
    """El código de un fallo. Del proveedor, solo si es de permiso o de un calendario
    que ya no está; lo demás es lo que se estaba intentando."""
    kind = getattr(exc, "kind", None)
    if kind == "auth":
        return ERROR_AUTH
    if kind == "not_found":
        return ERROR_CALENDAR_GONE
    return otherwise


@asynccontextmanager
async def _own_tx(tenant_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
    """Una transacción corta y aparte, la única que escribe en ``reservations`` durante una
    pasada. Si no puede agarrar la fila en ``LOCK_TIMEOUT``, falla en vez de esperar."""
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        await session.execute(sa.text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))
        yield session


async def _swap_ref(ctx: Ctx, reservation_id: uuid.UUID, was: str | None, now: str | None) -> bool:
    """Cambia la referencia del evento, si sigue siendo la que se leyó: la reserva pudo moverse
    mientras tanto. Si no se puede ahora, la pasada siguiente lo vuelve a intentar."""
    try:
        async with _own_tx(ctx.tenant_id) as session:
            result = await session.execute(
                sa.update(Reservation)
                .where(
                    Reservation.id == reservation_id,
                    Reservation.external_event_id.is_(None)
                    if was is None
                    else Reservation.external_event_id == was,
                )
                .values(external_event_id=now)
            )
            return _rowcount(result) > 0
    except DBAPIError as exc:
        log.warning(
            "reservation_calendar.ref_not_saved",
            tenant_id=str(ctx.tenant_id),
            reservation_id=str(reservation_id),
            error_type=type(exc).__name__,
        )
        return False


async def _save_removed(ctx: Ctx, reservation_id: uuid.UUID, stored: str) -> None:
    """Quita la referencia, si sigue siendo la del evento borrado: el evento pudo
    marcarse como movido mientras tanto, y la reserva, ganar otro. Si no se puede ahora, la
    pasada siguiente lo borra otra vez, y borrar lo borrado no es un fallo."""
    bare = stored.removeprefix(EVENT_MOVED)
    try:
        async with _own_tx(ctx.tenant_id) as session:
            await session.execute(
                sa.update(Reservation)
                .where(
                    Reservation.id == reservation_id,
                    Reservation.external_event_id.in_((bare, f"{EVENT_MOVED}{bare}")),
                )
                .values(external_event_id=None)
            )
    except DBAPIError as exc:
        log.warning(
            "reservation_calendar.ref_not_saved",
            tenant_id=str(ctx.tenant_id),
            reservation_id=str(reservation_id),
            error_type=type(exc).__name__,
        )


async def _save_written(
    ctx: Ctx,
    reservation_id: uuid.UUID,
    staff_id: uuid.UUID,
    calendar_id: str,
    event_id: str,
    span: tuple[datetime, datetime],
) -> str | None:
    """Apunta el evento recién creado. La reserva pudo cambiar mientras se creaba: si
    es otra, queda como movido y la pasada siguiente lo arregla. Devuelve lo apuntado, o
    ``None`` si otra pasada ya le escribió el suyo o no se pudo apuntar: en los dos casos,
    este sobra."""
    ref = _event_ref(staff_id, calendar_id, event_id)
    try:
        async with _own_tx(ctx.tenant_id) as session:
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
                return None
            same = (
                row.staff_id == staff_id
                and (row.starts_at, row.ends_at) == span
                and row.status in _LIVE
            )
            stored = ref if same else f"{EVENT_MOVED}{ref}"
            await session.execute(
                sa.update(Reservation)
                .where(Reservation.id == reservation_id)
                .values(external_event_id=stored)
            )
        return stored
    except DBAPIError as exc:
        log.warning(
            "reservation_calendar.ref_not_saved",
            tenant_id=str(ctx.tenant_id),
            reservation_id=str(reservation_id),
            error_type=type(exc).__name__,
        )
        return None


def _connection_to_delete_with(row: StaffCalendar | None) -> Connection | None:
    """Con qué se llega a los eventos que escribió: la conexión de antes, mientras exista; si
    no, la suya si está en uso. Una pendiente o caída no sirve."""
    if row is None:
        return None
    if row.previous is not None:
        return row.previous
    return row.connection if row.status in (CONNECTED, DISCONNECTING) else None


async def _remove_events(
    session: AsyncSession,
    ctx: Ctx,
    gateway: GoogleCalendarGateway,
    calendars: Mapping[uuid.UUID, StaffCalendar],
    now: datetime,
    errors: dict[uuid.UUID, str],
    *,
    only: uuid.UUID | None = None,
) -> int:
    """Borra los eventos que sobran: los de reservas que ya no están vivas y los de las
    movidas, cada uno del calendario donde vive y con la conexión de quien lo escribió.

    Lo que nadie puede borrar se suelta: un dueño sin conexión, o un evento sin id, no puede
    dejar a la reserva sin su evento nuevo (R12.7). Si vuelve a verse, su marca lo delata."""
    rows = (
        await session.execute(
            sa.select(
                Reservation.id,
                Reservation.staff_id,
                Reservation.external_event_id,
                Reservation.status,
                Reservation.updated_at,
            ).where(
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
    for reservation_id, staff_id, stored, status, updated_at in rows:
        ref = _parse_ref(stored)
        owner = ref.owner or staff_id
        if owner is None or (only is not None and owner != only):
            continue
        row = calendars.get(owner)
        conn = _connection_to_delete_with(row)
        calendar_id = ref.calendar_id or (row.calendar_id if row is not None else None)
        if conn is None or calendar_id is None or ref.event_id == UNKNOWN_EVENT:
            await _swap_ref(ctx, reservation_id, stored, None)
            continue
        try:
            await gateway.delete_busy(conn, calendar_id, ref.event_id)
        except Exception as exc:
            _log_write_failure(ctx, owner, reservation_id, "delete", exc)
            code = _failure(exc, ERROR_WRITE)
            errors.setdefault(owner, code)
            waited = status in _LIVE and now - updated_at >= REMOVE_WAITS_AT_MOST
            if code == ERROR_AUTH or waited:
                await _swap_ref(ctx, reservation_id, stored, None)
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
    written_now: set[str],
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
        if kept is not None:
            written += 1
            written_now.add(kept)
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
    await _delete_quietly(ctx, gateway, conn, staff_id, reservation_id, calendar_id, event_id)


async def _delete_quietly(
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
            sa.text(
                "DELETE FROM reservation_busy WHERE staff_id = :s AND ends_at > :now "
                "AND source = :src"
            ),
            {"s": staff_id, "now": now, "src": BUSY_GOOGLE},
        )
    else:
        result = await session.execute(
            sa.text(
                "DELETE FROM reservation_busy WHERE staff_id = :s AND synced_at < :limit "
                "AND source = :src"
            ),
            {"s": staff_id, "limit": now - BUSY_STALE_AFTER, "src": BUSY_GOOGLE},
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
    written_now: set[str],
) -> int:
    """Cambia el ocupado futuro de una persona por lo que dice ahora su calendario, y
    corrige lo nuestro si alguien lo tocó allí."""
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
    known = await _marked_reservations(session, ctx, intervals, ours)
    count = 0
    for b in intervals:
        if b.event_id is not None and b.event_id in ours:
            continue  # nuestro «Ocupado»: ya es una reserva
        mine = known.get(b.marker) if b.marker else None
        if mine is not None:
            await _settle_marked(ctx, gateway, conn, staff_id, calendar_id, b, mine)
            continue  # nunca es ocupado: la cita chocaría consigo misma
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
    await _put_ours_back(session, ctx, staff_id, calendar_id, intervals, now, written_now)
    return count


async def _marked_reservations(
    session: AsyncSession, ctx: Ctx, intervals: list[Busy], ours: set[str]
) -> dict[str, Any]:
    """Las reservas de este cliente que nombran las marcas de lo leído. La de otro cliente, o
    una que no existe, no libera nada: se lee como ocupado."""
    ids: set[uuid.UUID] = set()
    for b in intervals:
        if b.marker and b.event_id not in ours:
            try:
                ids.add(uuid.UUID(b.marker))
            except ValueError:
                continue
    if not ids:
        return {}
    rows = await session.execute(
        sa.select(
            Reservation.id,
            Reservation.staff_id,
            Reservation.status,
            Reservation.starts_at,
            Reservation.ends_at,
            Reservation.external_event_id,
        ).where(Reservation.tenant_id == ctx.tenant_id, Reservation.id.in_(ids))
    )
    return {str(r.id): r for r in rows.all()}


def _same_span(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return abs(a_start - b_start) < _SAME_SPAN and abs(a_end - b_end) < _SAME_SPAN


async def _settle_marked(
    ctx: Ctx,
    gateway: GoogleCalendarGateway,
    conn: Connection,
    staff_id: uuid.UUID,
    calendar_id: str,
    event: Busy,
    mine: Any,
) -> None:
    """Un evento con nuestra marca que ninguna reserva tiene apuntado. Si es la cita de esa
    persona, a esa hora, y aún no tiene evento, es el suyo: la creación no devolvió el id o se
    perdió su referencia. Si no, sobra."""
    if event.event_id is None:
        return
    stored = mine.external_event_id
    has_none = stored is None or (
        not stored.startswith(EVENT_MOVED) and _parse_ref(stored).event_id == UNKNOWN_EVENT
    )
    fits = (
        mine.staff_id == staff_id
        and mine.status in _LIVE
        and _same_span(event.starts_at, event.ends_at, mine.starts_at, mine.ends_at)
    )
    if has_none and fits:
        adopted = _event_ref(staff_id, calendar_id, event.event_id)
        if await _swap_ref(ctx, mine.id, stored, adopted):
            log.info(
                "reservation_calendar.event_adopted",
                tenant_id=str(ctx.tenant_id),
                staff_id=str(staff_id),
                reservation_id=str(mine.id),
            )
            return
    await _delete_quietly(ctx, gateway, conn, staff_id, mine.id, calendar_id, event.event_id)


async def _put_ours_back(
    session: AsyncSession,
    ctx: Ctx,
    staff_id: uuid.UUID,
    calendar_id: str,
    intervals: list[Busy],
    now: datetime,
    written_now: set[str],
) -> None:
    """Reservas manda (R13.2 y R13.3): nuestro «Ocupado» borrado a mano se vuelve a escribir
    y uno movido a mano vuelve a la hora de la reserva, en la pasada siguiente. Solo se
    mira dentro de lo leído, y no lo escrito en esta pasada: la lectura puede no traerlo aún.

    En los dos casos se borra antes de escribir: si el evento sigue ahí y es el listado el que
    no lo trae, recrearlo dejaría un «Ocupado» más en cada vuelta. Uno borrado a mano da 404, que
    cuenta como borrado."""
    seen = {b.event_id: b for b in intervals if b.event_id is not None}
    rows = await session.execute(
        sa.select(
            Reservation.id,
            Reservation.starts_at,
            Reservation.ends_at,
            Reservation.external_event_id,
        ).where(
            Reservation.staff_id == staff_id,
            Reservation.status.in_(_LIVE),
            Reservation.ends_at > now,
            Reservation.starts_at < now + SYNC_AHEAD,
            Reservation.external_event_id.is_not(None),
            Reservation.external_event_id.not_like(f"{EVENT_MOVED}%"),
        )
    )
    for reservation_id, starts_at, ends_at, stored in rows.all():
        ref = _parse_ref(stored)
        if ref.event_id == UNKNOWN_EVENT or stored in written_now or ref.calendar_id != calendar_id:
            continue
        found = seen.get(ref.event_id)
        if found is not None and _same_span(found.starts_at, found.ends_at, starts_at, ends_at):
            continue
        await _swap_ref(ctx, reservation_id, stored, f"{EVENT_MOVED}{stored}")
        log.info(
            "reservation_calendar.event_put_back",
            tenant_id=str(ctx.tenant_id),
            staff_id=str(staff_id),
            reservation_id=str(reservation_id),
            how="deleted_there" if found is None else "moved_there",
        )


@dataclass(frozen=True)
class _BusinessGoogle:
    """La conexión de Google del negocio (spec 023). ``exists``: nadie la ha quitado.
    ``connection``: se puede leer ahora."""

    exists: bool = False
    connection: Connection | None = None


async def _business_google(session: AsyncSession) -> _BusinessGoogle:
    row = (
        await session.execute(
            sa.select(TenantConnector.status, TenantConnector.credentials_ref)
            .join(Connector, Connector.id == TenantConnector.connector_id)
            .where(
                Connector.slug == TOOLKIT,
                TenantConnector.status != TenantConnectorStatus.DISCONNECTED.value,
            )
            .limit(1)
        )
    ).first()
    if row is None:
        return _BusinessGoogle()
    readable = row.status in (
        TenantConnectorStatus.CONNECTED.value,
        TenantConnectorStatus.PARTIAL.value,
    )
    credentials = row.credentials_ref or {}
    connection_id, user_id = credentials.get("composio_connection_id"), credentials.get("user_id")
    if not readable or not connection_id or not user_id:
        return _BusinessGoogle(exists=True)
    return _BusinessGoogle(exists=True, connection=Connection(str(user_id), str(connection_id)))


async def _business_calendars(session: AsyncSession) -> list[str]:
    """Lo que el negocio usaba como agenda: su calendario principal y el que un agente tuviera
    elegido."""
    settings = await session.scalars(
        sa.select(AgentConnectorActivation.settings)
        .join(Connector, Connector.id == AgentConnectorActivation.connector_id)
        .where(Connector.slug == TOOLKIT)
    )
    chosen = {str(s["calendar_id"]) for s in settings if s and s.get("calendar_id")}
    return ["primary", *sorted(chosen - {"primary"})]


async def _read_business_busy(
    session: AsyncSession,
    ctx: Ctx,
    gateway: GoogleCalendarGateway,
    calendars: list[StaffCalendar],
    ours: set[str],
    now: datetime,
) -> int:
    """Lo que ya está en el Google del negocio bloquea a quien aún no conectó el suyo, para que
    esa hora no se vuelva a dar. Una fila por persona. Una fila de antes dice qué calendario era
    el suyo; sin ella, no se sabe de quién es la cita, y se bloquea a todos: dar dos veces una
    hora es peor que no darla (R12.13).

    Aquí no vale «con datos viejos no se bloquea»: no es ocupado de alguien que puede estar libre,
    son citas que ya se dieron. Si la lectura falla o la conexión se cae, lo leído sigue. Solo se va
    al quitar la conexión o cuando la persona conecta el suyo."""
    syncing = {c.staff_id for c in calendars if c.syncs}
    for staff_id in syncing:
        await session.execute(
            sa.text("DELETE FROM reservation_busy WHERE staff_id = :s AND source = :src"),
            {"s": staff_id, "src": BUSY_BUSINESS},
        )
    business = await _business_google(session) if ctx.mode == "services" else _BusinessGoogle()
    waiting = [m.id for m in await active_staff(session) if m.id not in syncing]
    if not business.exists or not waiting:
        await session.execute(
            sa.text("DELETE FROM reservation_busy WHERE source = :src"), {"src": BUSY_BUSINESS}
        )
        return 0
    conn = business.connection
    if conn is None:
        return 0  # se cayó: lo leído sigue bloqueando, porque son citas ya dadas
    shared = await _business_calendars(session)
    own = {
        c.staff_id: c.calendar_id
        for c in calendars
        if c.calendar_id and c.connection is None and c.status == NEEDS_REAUTH
    }
    read: dict[str, list[Busy] | str] = {}
    count = 0
    for staff_id in waiting:
        one = own.get(staff_id)
        wanted = [one] if one else shared
        if one:
            # El calendario de su fila puede ser de su propia cuenta: con esta no se ve.
            answer = await _read_business_calendar(gateway, ctx, conn, one, now, read)
            if answer == ERROR_CALENDAR_GONE:
                wanted = shared
        found: list[Busy] = []
        failure: str | None = None
        for calendar_id in wanted:
            answer = await _read_business_calendar(gateway, ctx, conn, calendar_id, now, read)
            if isinstance(answer, str):
                failure = answer
            else:
                found.extend(answer)
        if failure is not None:
            continue  # no se pudo leer: lo que ya se sabía sigue, porque son citas ya dadas
        count += await _replace_business_busy(session, ctx, staff_id, found, ours, now)
    return count


async def _read_business_calendar(
    gateway: GoogleCalendarGateway,
    ctx: Ctx,
    conn: Connection,
    calendar_id: str,
    now: datetime,
    read: dict[str, list[Busy] | str],
) -> list[Busy] | str:
    """Lo que dice ese calendario, o el código del fallo. Una vez por pasada: lo comparten
    todos los que no tienen el suyo."""
    if calendar_id in read:
        return read[calendar_id]
    answer: list[Busy] | str
    try:
        answer = await gateway.busy(conn, calendar_id, now, now + SYNC_AHEAD, tz=ctx.tz)
    except Exception as exc:
        answer = _failure(exc, ERROR_READ)
        log.warning(
            "reservation_calendar.business_read_failed",
            tenant_id=str(ctx.tenant_id),
            error_kind=answer,
            error_type=type(exc).__name__,
        )
    read[calendar_id] = answer
    return answer


async def _replace_business_busy(
    session: AsyncSession,
    ctx: Ctx,
    staff_id: uuid.UUID,
    intervals: list[Busy],
    ours: set[str],
    now: datetime,
) -> int:
    await session.execute(
        sa.text(
            "DELETE FROM reservation_busy WHERE staff_id = :s AND ends_at > :now AND source = :src"
        ),
        {"s": staff_id, "now": now, "src": BUSY_BUSINESS},
    )
    # Las reservas de antes dejaron su «Ocupado» aquí: ya son una reserva. Aquí no se toca nada.
    known = await _marked_reservations(session, ctx, intervals, ours)
    spans: set[tuple[datetime, datetime]] = set()
    for b in intervals:
        if (b.event_id is not None and b.event_id in ours) or (b.marker and b.marker in known):
            continue
        if b.ends_at > b.starts_at:
            spans.add((b.starts_at, b.ends_at))
    for starts_at, ends_at in spans:
        await session.execute(
            sa.text(
                "INSERT INTO reservation_busy (tenant_id, staff_id, starts_at, ends_at, synced_at, "
                "source) VALUES (:t, :s, :a, :b, :now, :src)"
            ),
            {
                "t": ctx.tenant_id,
                "s": staff_id,
                "a": starts_at,
                "b": ends_at,
                "now": now,
                "src": BUSY_BUSINESS,
            },
        )
    return len(spans)


async def _record_outcome(
    session: AsyncSession,
    calendars: list[StaffCalendar],
    errors: Mapping[uuid.UUID, str],
    now: datetime,
) -> None:
    """``last_sync_at`` es la última pasada en la que salió todo; ``last_error``, lo que
    falló en esta."""
    for row in calendars:
        code = errors.get(row.staff_id)
        if code is None:
            await session.execute(
                sa.text(
                    "UPDATE reservation_staff_calendars SET last_sync_at = :now, last_error = "
                    "CASE WHEN last_error = :told AND status_since > :limit THEN last_error END "
                    "WHERE staff_id = :s"
                ),
                {
                    "now": now,
                    "s": row.staff_id,
                    "told": ERROR_NEW_ACCOUNT_REFUSED,
                    "limit": now - PENDING_EXPIRES_AFTER,
                },
            )
        else:
            await session.execute(
                sa.text(
                    "UPDATE reservation_staff_calendars SET last_error = :e WHERE staff_id = :s"
                ),
                {"e": code, "s": row.staff_id},
            )


async def sync_tenant(
    session: AsyncSession,
    ctx: Ctx,
    gateway: GoogleCalendarGateway,
    *,
    now: datetime,
    only: uuid.UUID | None = None,
) -> dict[str, int]:
    """Una pasada, bajo la RLS del cliente; ``only``, la de un profesional. Primero se
    escribe: así lo que se lee ya incluye los eventos nuevos y no los borrados, y un fallo
    al leer no para nada. Cada uno con su conexión: lo de uno no toca a los demás."""
    stats = {"busy": 0, "written": 0, "deleted": 0}
    await session.execute(sa.text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))
    await settle_pending(session, ctx, gateway, now=now)
    calendars = await staff_calendars(session)
    errors: dict[uuid.UUID, str] = {}
    await _unhealthy_stop_blocking(session, ctx, calendars, now)
    stats["deleted"] = await _remove_events(
        session, ctx, gateway, {c.staff_id: c for c in calendars}, now, errors, only=only
    )
    await _finish_disconnects(session, ctx, gateway, calendars, now, errors)
    syncing = [c for c in calendars if c.syncs and (only is None or c.staff_id == only)]
    written_now: set[str] = set()
    for c in syncing:
        assert c.connection is not None and c.calendar_id is not None
        stats["written"] += await _write_events(
            session, ctx, gateway, c.connection, c.staff_id, c.calendar_id, now, errors, written_now
        )
    ours = await _our_events(session)
    for c in syncing:
        assert c.connection is not None and c.calendar_id is not None
        stats["busy"] += await _read_busy(
            session,
            ctx,
            gateway,
            c.connection,
            c.staff_id,
            c.calendar_id,
            ours,
            now,
            errors,
            written_now,
        )
    await _record_outcome(session, syncing, errors, now)
    if only is None:  # lo del negocio es de todos: un botón de una persona no lo lee
        stats["busy"] += await _read_business_busy(
            session, ctx, gateway, await staff_calendars(session), ours, now
        )
    await session.flush()
    return stats


async def let_go_of(tenant_id: uuid.UUID, connection_ids: list[str]) -> None:
    """Se borró el cliente: revoca la conexión de cada profesional. La cuenta de Google es de
    esa persona, y la fila que sabía qué conexión quitar ya no existe (spec 043, R12.8)."""
    gateway = default_gateway()
    for connection_id in connection_ids:
        try:
            await gateway.revoke(connection_id)
        except Exception as exc:
            log.warning(
                "reservation_calendar.revoke_failed",
                tenant_id=str(tenant_id),
                error_type=type(exc).__name__,
            )


def default_gateway() -> GoogleCalendarGateway:
    from nexus_api.services.connectors.runtime import get_composio_client

    return ComposioGoogleCalendar(get_composio_client())


__all__ = [
    "BUSY_BUSINESS",
    "BUSY_GOOGLE",
    "BUSY_STALE_AFTER",
    "CONNECTED",
    "DISCONNECTING",
    "ERROR_AUTH",
    "ERROR_CALENDAR_GONE",
    "ERROR_CALENDAR_IN_USE",
    "ERROR_CONNECTION",
    "ERROR_NEW_ACCOUNT_REFUSED",
    "ERROR_NO_CALENDAR",
    "ERROR_READ",
    "ERROR_WRITE",
    "MARK",
    "MAX_PAGES",
    "NEEDS_REAUTH",
    "PENDING",
    "PENDING_EXPIRES_AFTER",
    "REMOVE_WAITS_AT_MOST",
    "TOOLKIT",
    "UNKNOWN_EVENT",
    "Busy",
    "CalendarError",
    "ComposioGoogleCalendar",
    "Connection",
    "GoogleCalendarError",
    "GoogleCalendarGateway",
    "StaffCalendar",
    "calendars_of",
    "choose_calendar",
    "default_gateway",
    "disconnect",
    "has_work",
    "let_go_of",
    "settle_pending",
    "staff_calendar",
    "staff_calendars",
    "staff_user_id",
    "start_connection",
    "sync_tenant",
]
