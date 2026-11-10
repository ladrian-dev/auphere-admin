"""``booking.check_availability`` con el horario que guarda de verdad cada pieza
(bug ``horario-del-negocio-en-tres-formas``).

Antes del arreglo, el horario del asistente del admin (``"09:00-18:00"``)
hacía reventar la herramienta con ``AttributeError`` y un día cerrado o la forma
de la semilla abrían de 10 a 19.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from nexus_api.core.tenant_context import tenant_context
from nexus_api.db.models import Tenant

from .conftest import all_whitelist

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

TZ = "America/Santiago"


def _next(weekday: int) -> date:
    """El próximo día de la semana pedido (0 = lunes), siempre en el futuro."""
    d = date.today() + timedelta(days=1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d


async def _set_hours(db_session, tenant_id, hours) -> None:
    tenant = await db_session.get(Tenant, tenant_id)
    tenant.timezone = TZ
    tenant.business_hours = hours
    await db_session.commit()


async def _slots(registry, tenant_id, on: date) -> list[tuple[str, str]]:
    with tenant_context(tenant_id):
        env = await registry.dispatch(
            "booking.check_availability",
            {"on_date": on.isoformat(), "service_name": "corte", "duration_min": 60},
            whitelist=all_whitelist(),
        )
    assert env.get("error") is None, env
    tz = ZoneInfo(TZ)
    out = []
    for s in env["result"]["slots"]:
        start = datetime.fromisoformat(s["starts_at"]).astimezone(tz)
        end = datetime.fromisoformat(s["ends_at"]).astimezone(tz)
        out.append((start.strftime("%H:%M"), end.strftime("%H:%M")))
    return out


ADMIN_HOURS = {
    "monday": "09:00-13:00",
    "tuesday": "09:00-13:00",
    "wednesday": "09:00-13:00",
    "thursday": "09:00-13:00",
    "friday": "09:00-13:00",
    "saturday": "closed",
    "sunday": "closed",
}


async def test_admin_hours_give_slots_inside_them(db_session, two_tenants, mcp_registry):
    a = two_tenants["a"]
    await _set_hours(db_session, a, ADMIN_HOURS)

    slots = await _slots(mcp_registry, a, _next(0))

    assert slots[0] == ("09:00", "10:00")
    assert slots[-1] == ("12:00", "13:00")
    assert all("09:00" <= s <= "12:00" for s, _ in slots)


async def test_closed_day_gives_no_slots(db_session, two_tenants, mcp_registry):
    a = two_tenants["a"]
    await _set_hours(db_session, a, ADMIN_HOURS)

    assert await _slots(mcp_registry, a, _next(6)) == []


async def test_seed_shape_is_honoured(db_session, two_tenants, mcp_registry):
    a = two_tenants["a"]
    await _set_hours(
        db_session,
        a,
        {
            **{d: {"open": "08:00", "close": "10:00"} for d in ("monday", "tuesday")},
            "sunday": None,
        },
    )

    assert await _slots(mcp_registry, a, _next(0)) == [
        ("08:00", "09:00"),
        ("08:30", "09:30"),
        ("09:00", "10:00"),
    ]
    assert await _slots(mcp_registry, a, _next(6)) == []


async def test_split_day_offers_nothing_across_the_break(db_session, two_tenants, mcp_registry):
    a = two_tenants["a"]
    await _set_hours(
        db_session,
        a,
        {"friday": [{"from": "13:00", "to": "15:00"}, {"from": "20:00", "to": "21:00"}]},
    )

    assert await _slots(mcp_registry, a, _next(4)) == [
        ("13:00", "14:00"),
        ("13:30", "14:30"),
        ("14:00", "15:00"),
        ("20:00", "21:00"),
    ]
