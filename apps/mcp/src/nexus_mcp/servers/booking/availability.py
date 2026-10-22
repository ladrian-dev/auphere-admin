"""Local availability search.

Block D's booking-server is a relational facade. ``check_availability``
needs to produce a list of free slots for a given date + service. Without
AgendaPro (Block E) we approximate from the local ``appointments`` table:

- Business hours: the tenant's ``business_hours`` in its ``timezone``, read
  through ``nexus_api.services.business_hours`` — one reader for every shape
  ever stored (bug ``horario-del-negocio-en-tres-formas``). A closed day, or a
  day the stored hours do not name, has no slots. A tenant with no hours at
  all keeps the historical 10:00-19:00.
- A day may have several ranges (lunch and dinner); a slot never straddles
  the gap between two of them.
- Slot duration: argument ``duration_min`` (default 30).
- Step granularity: 30 min, counted from the start of each range.
- A slot is free if no existing appointment for the same barber overlaps.
  When ``barber_id`` is None we list slots with ``barber_id=null`` if the
  shop has at least one un-allocated time at that point.

This is honest enough for Phase 1 dev/testing. When Block E lands
``CheckAvailability`` will delegate to AgendaPro for tenants that use it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time, timedelta
from datetime import date as Date  # noqa: N812

from nexus_api.db.models import Appointment, AppointmentStatus, Tenant
from nexus_api.services.business_hours import WEEKDAYS, parse_business_hours
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_DAY_START = time(10, 0)
DEFAULT_DAY_END = time(19, 0)
SLOT_STEP_MIN = 30


async def _resolve_tenant_hours(
    session: AsyncSession, tenant_id: uuid.UUID, on_date: Date
) -> list[tuple[datetime, datetime]]:
    """The open ranges of ``on_date`` in UTC, in order. Empty means closed.

    The tenant has a ``timezone`` (IANA name, e.g. ``America/Santiago``) and an
    optional ``business_hours`` JSONB; the hours are local to the business.
    """
    tenant = await session.get(Tenant, tenant_id)
    tz_name = tenant.timezone if tenant else "UTC"
    hours = parse_business_hours(tenant.business_hours if tenant else None)

    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(tz_name)
    except Exception:
        tz = UTC  # type: ignore[assignment]

    if hours is None:
        day_ranges = [(DEFAULT_DAY_START, DEFAULT_DAY_END)]
    else:
        day_ranges = hours[WEEKDAYS[on_date.weekday()]]

    return [
        (
            datetime.combine(on_date, start_t).replace(tzinfo=tz).astimezone(UTC),
            datetime.combine(on_date, end_t).replace(tzinfo=tz).astimezone(UTC),
        )
        for start_t, end_t in day_ranges
    ]


async def find_free_slots(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    on_date: Date,
    duration_min: int,
    barber_id: uuid.UUID | None,
) -> list[tuple[datetime, datetime, uuid.UUID | None]]:
    ranges = await _resolve_tenant_hours(session, tenant_id, on_date)
    if not ranges:
        return []
    day_start, day_end = ranges[0][0], ranges[-1][1]
    step = timedelta(minutes=SLOT_STEP_MIN)
    duration = timedelta(minutes=duration_min)

    stmt = select(Appointment).where(
        Appointment.starts_at < day_end,
        Appointment.ends_at > day_start,
        Appointment.status.in_(
            (
                AppointmentStatus.BOOKED,
                AppointmentStatus.CONFIRMED,
            )
        ),
    )
    if barber_id is not None:
        stmt = stmt.where(Appointment.barber_id == barber_id)
    existing = list((await session.execute(stmt)).scalars().all())

    slots: list[tuple[datetime, datetime, uuid.UUID | None]] = []
    for range_start, range_end in ranges:
        cursor = range_start
        while cursor + duration <= range_end:
            slot_end = cursor + duration
            clash = any(not (a.ends_at <= cursor or a.starts_at >= slot_end) for a in existing)
            if not clash:
                slots.append((cursor, slot_end, barber_id))
            cursor += step
    return slots
