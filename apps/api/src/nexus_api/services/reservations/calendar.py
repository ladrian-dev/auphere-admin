"""Reservas — Google Calendar del equipo (spec 043, Historia 7, P3).

Lo que el resto del módulo necesita saber de los calendarios: los choques de
cada reserva viva con un «ocupado» externo. Sin la tabla de la P3 (su migración
es independiente), no hay ninguno.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import Reservation
from nexus_api.services.reservations.calendar_sync import (
    BUSY_BUSINESS,
    DISCONNECTING,
    ERROR_AUTH,
    ERROR_CONNECTION,
    NEEDS_REAUTH,
    PENDING,
)
from nexus_api.services.reservations.core import Ctx


async def _has_busy_table(session: AsyncSession) -> bool:
    return bool(await session.scalar(sa.text("SELECT to_regclass('reservation_busy') IS NOT NULL")))


async def clashes_for(
    session: AsyncSession, ctx: Ctx, rows: Sequence[Reservation]
) -> dict[uuid.UUID, dict[str, Any]]:
    """``booking_id`` → ``{"source": "google", "local": {start, end}}`` para cada
    reserva viva de Servicios que pisa un «ocupado» de su persona."""
    live = [
        r
        for r in rows
        if r.mode == "services" and r.status in ("pending", "confirmed") and r.staff_id
    ]
    if not live or not await _has_busy_table(session):
        return {}
    out: dict[uuid.UUID, dict[str, Any]] = {}
    for r in live:
        hit = (
            await session.execute(
                sa.text(
                    "SELECT starts_at, ends_at FROM reservation_busy WHERE staff_id = :s "
                    "AND starts_at < :e AND ends_at > :b ORDER BY starts_at LIMIT 1"
                ),
                {"s": r.staff_id, "b": r.starts_at, "e": r.ends_at},
            )
        ).first()
        if hit is not None:
            a, b = ctx.local(hit[0]), ctx.local(hit[1])
            out[r.id] = {
                "source": "google",
                "local": {"start": a.strftime("%H:%M"), "end": b.strftime("%H:%M")},
            }
    return out


async def clash_count(session: AsyncSession, ctx: Ctx, now: datetime) -> int:
    """Choques de las reservas vivas futuras: la insignia del lateral."""
    if not await _has_busy_table(session):
        return 0
    count = await session.scalar(
        sa.text(
            "SELECT count(DISTINCT r.id) FROM reservations r JOIN reservation_busy b "
            "ON b.staff_id = r.staff_id AND b.starts_at < r.ends_at AND b.ends_at > r.starts_at "
            "WHERE r.status IN ('pending', 'confirmed') AND r.starts_at > :now"
        ),
        {"now": now},
    )
    return int(count or 0)


async def staff_calendar_status(session: AsyncSession) -> dict[uuid.UUID, dict[str, Any]]:
    """``staff_id`` → su estado para la pantalla, para quien tiene una fila. Quien se está
    desconectando ya no tiene ninguna: para la persona, ya está. ``last_error`` es un código
    de ``calendar_sync``, nunca el texto del proveedor. Sin la P3, nadie."""
    has = await session.scalar(
        sa.text("SELECT to_regclass('reservation_staff_calendars') IS NOT NULL")
    )
    if not has:
        return {}
    rows = (
        await session.execute(
            sa.text(
                "SELECT staff_id, calendar_id, calendar_name, last_sync_at, last_error, "
                "connection_status, account_label FROM reservation_staff_calendars "
                "WHERE connection_status <> :gone"
            ),
            {"gone": DISCONNECTING},
        )
    ).all()
    out: dict[uuid.UUID, dict[str, Any]] = {
        r.staff_id: {
            "status": _status_of(r.connection_status, r.calendar_id, r.last_error),
            "calendar_name": r.calendar_name,
            "account": r.account_label,
            "last_sync_at": r.last_sync_at,
            "last_error": r.last_error,
        }
        for r in rows
    }
    # R12.13: hay horas de esta persona que bloquea el Google del negocio.
    business = await session.scalars(
        sa.text(
            "SELECT DISTINCT staff_id FROM reservation_busy WHERE source = :src AND ends_at > now()"
        ),
        {"src": BUSY_BUSINESS},
    )
    for staff_id in business:
        out.setdefault(staff_id, {"status": "none"})["business_busy"] = True
    return out


def _status_of(connection: str, calendar_id: str | None, last_error: str | None) -> str:
    """Una salida por estado: ``pending``, a la espera de que se autorice; ``needs_reauth``,
    hay que volver a conectar; ``needs_calendar``, conectado y sin calendario; ``error``, algo
    falló en la última pasada y puede arreglarse solo o cambiando de calendario."""
    if connection == PENDING:
        return "pending"
    if connection == NEEDS_REAUTH or last_error in (ERROR_AUTH, ERROR_CONNECTION):
        return "needs_reauth"
    if calendar_id is None:
        return "needs_calendar"
    return "error" if last_error else "connected"


__all__ = ["clash_count", "clashes_for", "staff_calendar_status"]
