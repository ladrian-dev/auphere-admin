"""Reservas P3 — sincronizar el Google Calendar del equipo (spec 043, Historia 7).

Lo hace **el sistema**, no el agente: las herramientas de Google Calendar del
agente siguen bloqueadas (spec 023, «lo desconocido nace bloqueado»). Aquí se
usa la conexión que el cliente ya hizo en el proveedor de consentimientos, con
el mismo ``user_id = tenant_<slug>`` que el resto del runtime.

Dos sentidos, y en los dos lo mínimo:

- **entra** el «ocupado» de cada calendario asociado a una persona: solo inicio
  y fin (``reservation_busy``); ni título ni asistentes;
- **sale** cada reserva viva de esa persona como un evento **«Ocupado»**, sin
  nombre del cliente ni servicio; se mueve o se borra con la reserva.

Todo lo que sabe del proveedor vive en :class:`GoogleCalendarGateway`: los
nombres de las acciones y de sus argumentos son los del conector de Google
Calendar del proveedor. Las pruebas usan un doble de la puerta.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import (
    Connector,
    Reservation,
    Tenant,
    TenantConnector,
    TenantConnectorStatus,
)
from nexus_api.services.reservations.core import Ctx

#: Marca de nuestros propios eventos «Ocupado», para quien mire el calendario.
#: Lo nuestro se reconoce por el id del evento que guarda la reserva
#: (``external_event_id``), no por este texto: cualquiera puede escribirlo en la
#: descripción de una invitación y liberar así ese hueco (/cso, apéndice).
MARK = "auphere:reserva:"
SYNC_AHEAD = timedelta(days=60)
TOOLKIT = "googlecalendar"


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
        self, conn: Connection, calendar_id: str, start: datetime, end: datetime
    ) -> list[Busy]: ...

    async def create_busy(
        self, conn: Connection, calendar_id: str, start: datetime, end: datetime, marker: str
    ) -> str: ...

    async def delete_busy(self, conn: Connection, calendar_id: str, event_id: str) -> None: ...


class ComposioGoogleCalendar:
    """La puerta real, sobre el cliente del proveedor de consentimientos."""

    def __init__(self, client: Any) -> None:
        self._client = client

    async def _run(self, conn: Connection, slug: str, args: dict[str, Any]) -> dict[str, Any]:
        result = await self._client.execute_tool(
            tool_slug=slug, user_id=conn.user_id, connection_id=conn.connection_id, arguments=args
        )
        if result.error:
            raise RuntimeError(f"{slug}: {result.error}")
        return dict(result.data or {})

    async def list_calendars(self, conn: Connection) -> list[dict[str, str]]:
        data = await self._run(conn, "GOOGLECALENDAR_LIST_CALENDARS", {})
        items = data.get("items") or data.get("calendars") or []
        return [
            {"id": str(c.get("id")), "name": str(c.get("summary") or c.get("id"))}
            for c in items
            if isinstance(c, dict) and c.get("id")
        ]

    async def busy(
        self, conn: Connection, calendar_id: str, start: datetime, end: datetime
    ) -> list[Busy]:
        data = await self._run(
            conn,
            "GOOGLECALENDAR_LIST_EVENTS",
            {
                "calendarId": calendar_id,
                "timeMin": start.isoformat(),
                "timeMax": end.isoformat(),
                "singleEvents": True,
            },
        )
        out: list[Busy] = []
        for ev in data.get("items") or data.get("events") or []:
            if not isinstance(ev, dict) or ev.get("transparency") == "transparent":
                continue
            a = (ev.get("start") or {}).get("dateTime")
            b = (ev.get("end") or {}).get("dateTime")
            if a and b:
                ev_id = ev.get("id")
                out.append(
                    Busy(
                        datetime.fromisoformat(a),
                        datetime.fromisoformat(b),
                        str(ev_id) if ev_id else None,
                    )
                )
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
                "start_datetime": start.isoformat(),
                "event_duration_hour": minutes // 60,
                "event_duration_minutes": minutes % 60,
                "transparency": "opaque",
                "send_updates": False,
            },
        )
        return str(data.get("id") or (data.get("response_data") or {}).get("id") or "")

    async def delete_busy(self, conn: Connection, calendar_id: str, event_id: str) -> None:
        await self._run(
            conn, "GOOGLECALENDAR_DELETE_EVENT", {"calendar_id": calendar_id, "event_id": event_id}
        )


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


async def _mappings(session: AsyncSession) -> list[tuple[uuid.UUID, str]]:
    rows = await session.execute(
        sa.text("SELECT staff_id, calendar_id FROM reservation_staff_calendars")
    )
    return [(sid, cal) for sid, cal in rows.all()]


async def sync_tenant(
    session: AsyncSession,
    ctx: Ctx,
    gateway: GoogleCalendarGateway,
    conn: Connection,
    *,
    now: datetime,
) -> dict[str, int]:
    """Una pasada: entra el ocupado, salen los «Ocupado», se borran los de las
    reservas que ya no están vivas. Bajo la RLS del cliente."""
    stats = {"busy": 0, "written": 0, "deleted": 0}
    for staff_id, calendar_id in await _mappings(session):
        try:
            intervals = await gateway.busy(conn, calendar_id, now, now + SYNC_AHEAD)
        except Exception as exc:  # el resto de personas sigue
            await session.execute(
                sa.text(
                    "UPDATE reservation_staff_calendars SET last_error = :e WHERE staff_id = :s"
                ),
                {"e": str(exc)[:200], "s": staff_id},
            )
            continue
        await session.execute(
            sa.text("DELETE FROM reservation_busy WHERE staff_id = :s AND ends_at > :now"),
            {"s": staff_id, "now": now},
        )
        ours = set(
            (
                await session.execute(
                    sa.select(Reservation.external_event_id).where(
                        Reservation.staff_id == staff_id,
                        Reservation.external_event_id.is_not(None),
                    )
                )
            ).scalars()
        )
        for b in intervals:
            if b.event_id is not None and b.event_id in ours:
                continue  # nuestro «Ocupado»: ya es una reserva
            await session.execute(
                sa.text(
                    "INSERT INTO reservation_busy (tenant_id, staff_id, starts_at, ends_at) "
                    "VALUES (:t, :s, :a, :b)"
                ),
                {"t": ctx.tenant_id, "s": staff_id, "a": b.starts_at, "b": b.ends_at},
            )
            stats["busy"] += 1
        live = (
            await session.execute(
                sa.select(Reservation).where(
                    Reservation.staff_id == staff_id,
                    Reservation.status.in_(("pending", "confirmed")),
                    Reservation.ends_at > now,
                    Reservation.external_event_id.is_(None),
                )
            )
        ).scalars()
        for res in list(live):
            res.external_event_id = await gateway.create_busy(
                conn, calendar_id, res.starts_at, res.ends_at, f"{MARK}{res.id}"
            )
            stats["written"] += 1
        gone = (
            await session.execute(
                sa.select(Reservation).where(
                    Reservation.staff_id == staff_id,
                    Reservation.status.in_(("cancelled", "noshow")),
                    Reservation.external_event_id.is_not(None),
                )
            )
        ).scalars()
        for res in list(gone):
            await gateway.delete_busy(conn, calendar_id, str(res.external_event_id))
            res.external_event_id = None
            stats["deleted"] += 1
        await session.execute(
            sa.text(
                "UPDATE reservation_staff_calendars SET last_sync_at = :now, last_error = NULL "
                "WHERE staff_id = :s"
            ),
            {"now": now, "s": staff_id},
        )
    await session.flush()
    return stats


async def set_staff_calendar(
    session: AsyncSession,
    ctx: Ctx,
    staff_id: uuid.UUID,
    calendar_id: str | None,
    calendar_name: str | None,
) -> None:
    if calendar_id is None:
        await session.execute(
            sa.text("DELETE FROM reservation_staff_calendars WHERE staff_id = :s"), {"s": staff_id}
        )
        await session.execute(
            sa.text("DELETE FROM reservation_busy WHERE staff_id = :s"), {"s": staff_id}
        )
        return
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
    "MARK",
    "Busy",
    "ComposioGoogleCalendar",
    "Connection",
    "GoogleCalendarGateway",
    "connection_of",
    "default_gateway",
    "set_staff_calendar",
    "sync_tenant",
]
