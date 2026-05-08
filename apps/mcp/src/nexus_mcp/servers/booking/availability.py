"""Local availability search.

Block D's booking-server is a relational facade. ``check_availability``
needs to produce a list of free slots for a given date + service. Without
AgendaPro (Block E) we approximate from the local ``appointments`` table:

- Business hours: 10:00-19:00 in the tenant's timezone (the `tenants`
  row carries `timezone` and `business_hours`; if `business_hours` is set
  we use it, else fall back to a sensible default).
- Slot duration: argument ``duration_min`` (default 30).
- Step granularity: 30 min (slots align to :00 / :30).
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
from typing import Any

from nexus_api.db.models import Appointment, AppointmentStatus, Tenant
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_DAY_START = time(10, 0)
DEFAULT_DAY_END = time(19, 0)
SLOT_STEP_MIN = 30


async def _resolve_tenant_hours(
    session: AsyncSession, tenant_id: uuid.UUID, on_date: Date
) -> tuple[datetime, datetime]:
    """Return ``(day_start, day_end)`` in UTC for the given date.

    The tenant has a ``timezone`` (IANA name, e.g. ``America/Santiago``)
    and an optional ``business_hours`` JSONB. We honour both. Block D
    keeps the ``business_hours`` schema simple — a dict like
    ``{"weekday": {"start": "10:00", "end": "19:00"}}`` — and falls back
    to defaults if absent.
    """
    tenant = await session.get(Tenant, tenant_id)
    tz_name = tenant.timezone if tenant else "UTC"
    hours = (tenant.business_hours or {}) if tenant else {}

    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(tz_name)
    except Exception:
        tz = UTC  # type: ignore[assignment]

    weekday_key = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")[
        on_date.weekday()
    ]
    spec: dict[str, Any] | None = hours.get(weekday_key) if isinstance(hours, dict) else None
    start_t = _parse_hhmm(spec.get("start") if spec else None, DEFAULT_DAY_START)
    end_t = _parse_hhmm(spec.get("end") if spec else None, DEFAULT_DAY_END)

    day_start_local = datetime.combine(on_date, start_t).replace(tzinfo=tz)
    day_end_local = datetime.combine(on_date, end_t).replace(tzinfo=tz)
    return day_start_local.astimezone(UTC), day_end_local.astimezone(UTC)


def _parse_hhmm(s: str | None, default: time) -> time:
    if not s:
        return default
    try:
        h, m = s.split(":")
        return time(int(h), int(m))
    except Exception:
        return default


async def find_free_slots(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    on_date: Date,
    duration_min: int,
    barber_id: uuid.UUID | None,
) -> list[tuple[datetime, datetime, uuid.UUID | None]]:
    day_start, day_end = await _resolve_tenant_hours(session, tenant_id, on_date)
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
    cursor = day_start
    while cursor + duration <= day_end:
        slot_end = cursor + duration
        clash = any(not (a.ends_at <= cursor or a.starts_at >= slot_end) for a in existing)
        if not clash:
            slots.append((cursor, slot_end, barber_id))
        cursor += step
    return slots
