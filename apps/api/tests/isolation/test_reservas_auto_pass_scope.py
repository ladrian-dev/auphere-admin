"""Spec 048, T026 — guarantee 1: the automatic pass to Reservas of one client
neither reads nor writes anything of another (requirement 3.7).

The release task lists the clients with the migrations role, and then each one
passes in its own transaction, under its RLS (``admin.as_tenant``). Here B is
the bait: it has everything A's pass could pick up by mistake —

- a saved sector «restaurante» (A has none: it must stay appointments per
  person, not become capacity by reading B's profile);
- Reservas with a «Corte» service and «Lucía» on its team (A's appointment
  «Corte» with «Lucía» must not match them: A's Reservas is empty);
- its own agent with ``booking.*``, a draft, tests and appointments.

Passing A leaves every row of B exactly as it was.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa

from tests.conftest import make_reservas
from tests.integration.reservations._legacy_world import (
    agent_with_booking,
    appointment,
    barber,
    business_sector,
    customer,
    read,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

_B_ROWS = {
    "agent_configs": "SELECT id, status::text, tools, system_prompt_rendered, spec "
    "FROM agent_configs WHERE tenant_id = :t ORDER BY version",
    "agents": "SELECT id, draft_revision FROM agents WHERE tenant_id = :t ORDER BY id",
    "agent_tests": "SELECT id, stale FROM agent_tests WHERE tenant_id = :t ORDER BY id",
    "reservations": "SELECT id FROM reservations WHERE tenant_id = :t ORDER BY id",
    "reservation_settings": "SELECT mode, capacity_kind, version FROM reservation_settings "
    "WHERE tenant_id = :t",
    "client_access": "SELECT enabled, modules FROM client_access WHERE tenant_id = :t",
    "appointments": "SELECT id, status::text FROM appointments WHERE tenant_id = :t ORDER BY id",
    "audit_log": "SELECT id FROM audit_log WHERE tenant_id = :t ORDER BY id",
}


async def _snapshot(db_session, tenant_id: uuid.UUID) -> dict[str, Any]:
    """Every row of the client that the pass could touch (as the platform, no RLS)."""
    out: dict[str, Any] = {}
    for name, sql in _B_ROWS.items():
        rows = (await db_session.execute(sa.text(sql), {"t": tenant_id})).all()
        out[name] = [tuple(r) for r in rows]
    await db_session.commit()
    return out


async def test_passing_one_client_leaves_the_other_untouched(db_session, console_world) -> None:
    from nexus_api.db.base import get_sessionmaker
    from nexus_api.db.models import Reservation, ReservationSettings
    from nexus_api.services.reservations import auto_pass

    a, b = console_world["a"], console_world["b"]
    starts = (datetime.now(UTC) + timedelta(days=3)).replace(
        hour=15, minute=0, second=0, microsecond=0
    )

    # A: books with booking.*, no sector, no Reservas, one future «Corte» with Lucía.
    agent_a = await agent_with_booking(db_session, a["tenant_id"])
    cust_a = await customer(db_session, a["tenant_id"])
    lucia_a = await barber(db_session, a["tenant_id"], "Lucía")
    db_session.add(appointment(a["tenant_id"], cust_a, lucia_a, "Corte", starts))
    await db_session.commit()

    # B: the bait.
    await business_sector(db_session, b["tenant_id"], "restaurante")
    await make_reservas(db_session, partner_id=b["partner_id"], tenant_id=b["tenant_id"])
    await agent_with_booking(db_session, b["tenant_id"], draft=True, tests=True)
    cust_b = await customer(db_session, b["tenant_id"])
    lucia_b = await barber(db_session, b["tenant_id"], "Lucía")
    db_session.add(appointment(b["tenant_id"], cust_b, lucia_b, "Corte", starts))
    await db_session.commit()

    before = await _snapshot(db_session, b["tenant_id"])
    report = await auto_pass.pass_one(get_sessionmaker(), a["tenant_id"], now=datetime.now(UTC))

    assert report is not None
    # A's pass saw only A: its agent, its empty Reservas, its own appointment.
    assert [p.agent_id for p in report.published] == [agent_a]
    assert report.imports.imported == []
    assert [n["reason"] for n in report.imports.not_imported] == ["service_missing"]

    async def a_state(session):  # type: ignore[no-untyped-def]
        return (
            (await session.execute(sa.select(ReservationSettings))).scalar_one(),
            await session.scalar(sa.select(sa.func.count()).select_from(Reservation)),
        )

    settings_a, reservations_a = await read(a["tenant_id"], a_state)
    assert (settings_a.mode, settings_a.capacity_kind) == ("services", None), (
        "A's mode came from B's sector"
    )
    assert reservations_a == 0

    assert await _snapshot(db_session, b["tenant_id"]) == before
