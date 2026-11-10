"""Spec 043 — piezas comunes de las pruebas de los crons de Reservas.

Las reservas se crean con el dominio (``core.create_booking``) como las crea el
negocio, y cada cron se prueba por su función por cliente con un ``now``
fijado: nada depende de la hora a la que corre la suite.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Channel,
    ChannelStatus,
    ChannelType,
    Message,
    Reservation,
    ReservationEvent,
    ReservationOutbox,
)
from nexus_api.services.reservations import core

TZ = ZoneInfo("America/Santiago")
PHONE = "+56911112222"
DIGITS = "56911112222"


@asynccontextmanager
async def scoped(tenant_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
    """Una transacción acotada al cliente, como la de cada cron."""
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        yield session


def local(day: date, hhmm: str) -> datetime:
    """La hora del negocio (Santiago) de ese día, como instante."""
    return datetime.combine(day, time.fromisoformat(hhmm), tzinfo=TZ)


async def book(
    tenant_id: uuid.UUID,
    *,
    day: date,
    at: str,
    status: str = "confirmed",
    phone: str | None = PHONE,
    name: str = "Ana",
    party: int = 2,
    staff: uuid.UUID | None = None,
    service: uuid.UUID | None = None,
) -> uuid.UUID:
    """Una reserva hecha por el negocio, sin aviso de confirmación."""
    async with scoped(tenant_id) as s:
        ctx = await core.load_ctx(s, tenant_id)
        assert ctx is not None
        res, _ = await core.create_booking(
            s,
            ctx,
            core.NewBooking(
                day=day,
                at=time.fromisoformat(at),
                origin="person",
                channel="phone",
                contact_name=name,
                contact_phone=phone,
                party_size=party,
                staff_id=staff,
                service_id=service,
                notify=False,
                status=status,
            ),
            actor=core.Actor("person", "Valeria"),
            now=datetime.now(UTC),
        )
        return res.id


async def reservation(tenant_id: uuid.UUID, res_id: uuid.UUID) -> Reservation:
    async with scoped(tenant_id) as s:
        row = await s.get(Reservation, res_id)
        assert row is not None
        return row


async def set_status(tenant_id: uuid.UUID, res_id: uuid.UUID, status: str) -> None:
    async with scoped(tenant_id) as s:
        await s.execute(
            sa.update(Reservation).where(Reservation.id == res_id).values(status=status)
        )


async def outbox(tenant_id: uuid.UUID) -> list[ReservationOutbox]:
    async with scoped(tenant_id) as s:
        rows = await s.execute(
            sa.select(ReservationOutbox).order_by(
                ReservationOutbox.created_at, ReservationOutbox.dedupe_key
            )
        )
        return list(rows.scalars())


async def events(tenant_id: uuid.UUID, res_id: uuid.UUID) -> list[tuple[str, str, dict[str, Any]]]:
    async with scoped(tenant_id) as s:
        rows = await s.execute(
            sa.select(ReservationEvent.kind, ReservationEvent.actor_kind, ReservationEvent.data)
            .where(ReservationEvent.reservation_id == res_id)
            .order_by(ReservationEvent.created_at)
        )
        return [(k, a, dict(d or {})) for k, a, d in rows.all()]


async def messages(tenant_id: uuid.UUID) -> list[Message]:
    async with scoped(tenant_id) as s:
        rows = await s.execute(sa.select(Message).order_by(Message.created_at))
        return list(rows.scalars())


async def add_line(db_session: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID:
    """El número de WhatsApp (Meta) del negocio."""
    channel = Channel(
        tenant_id=tenant_id,
        type=ChannelType.WHATSAPP,
        provider="meta",
        provider_identifier=f"+5622{uuid.uuid4().int % 10_000_000:07d}",
        status=ChannelStatus.ACTIVE,
    )
    db_session.add(channel)
    await db_session.commit()
    return channel.id


WEEKDAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def when(at: datetime) -> str:
    """«el jueves 23 a las 20:30», en la hora del negocio."""
    loc = at.astimezone(TZ)
    return f"el {WEEKDAYS[loc.weekday()]} {loc.day} a las {loc.strftime('%H:%M')}"
