"""Requisito 4 — la presencia se deriva del latido, y el catálogo la obedece.

La regla que gobierna todo esto: **no hay columna de estado**. Si la hubiera, se
quedaría diciendo «conectada» el día que muera el proceso que debía actualizarla,
y §V no admite una pantalla que miente. Derivar cuesta un cálculo por lectura y
paga con que la mentira sea imposible, no improbable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from nexus_api.core.partner_context import partner_context
from nexus_api.db.models import Partner, PartnerDevice
from nexus_api.repositories.local_workstation import PartnerDeviceRepository
from nexus_api.services.device_presence import (
    HEARTBEAT_INTERVAL,
    PRESENCE_EXPIRY,
    catalog_includes_local_tools,
    derive_presence,
)

pytestmark = pytest.mark.asyncio


async def _partner(session) -> uuid.UUID:
    partner_id = uuid.uuid4()
    session.add(Partner(id=partner_id, name="Pres", slug=f"pr-{partner_id.hex[:6]}"))
    await session.commit()
    await session.execute(
        text(
            "SELECT set_config('app.partner_id', :p, true), set_config('app.principal_id', 'user_pres', true)"
        ),
        {"p": str(partner_id)},
    )
    return partner_id


def test_a_device_that_never_beat_is_absent():
    assert derive_presence(None) == "ausente"


def test_within_the_window_it_is_present():
    assert derive_presence(datetime.now(UTC) - PRESENCE_EXPIRY / 2) == "presente"


def test_past_the_window_it_is_absent():
    assert derive_presence(datetime.now(UTC) - PRESENCE_EXPIRY - timedelta(seconds=1)) == "ausente"


def test_there_is_room_to_lose_beats_before_declaring_absence():
    """Con un solo latido perdido no se declara ausencia: sería ruido, no señal."""
    assert PRESENCE_EXPIRY >= HEARTBEAT_INTERVAL * 2


def test_the_window_fits_inside_the_minute_ce004_demands():
    assert timedelta(minutes=1) > PRESENCE_EXPIRY


def test_the_local_tools_leave_the_catalog_when_the_device_goes():
    assert catalog_includes_local_tools("presente") is True
    assert catalog_includes_local_tools("ausente") is False


async def test_the_heartbeat_is_the_only_thing_that_moves(db_session):
    """Latir no cambia nada más: no hay estado que pueda quedar desincronizado."""
    partner_id = await _partner(db_session)
    with partner_context(str(partner_id)):
        repo = PartnerDeviceRepository(db_session)
        device = await repo.pair(
            principal_id="user_pres",
            display_name="portátil",
            hostname="portatil.local",
            platform="macos",
        )
        assert device.last_heartbeat_at is None
        assert derive_presence(device.last_heartbeat_at) == "ausente"

        await repo.record_heartbeat(device.id)
        assert derive_presence(device.last_heartbeat_at) == "presente"


async def test_there_is_no_status_column_to_go_stale(db_session):
    """La garantía es estructural: no existe dónde guardar una presencia caducada."""
    columns = {c.name for c in PartnerDevice.__table__.columns}
    assert "status" not in columns
    assert "presence" not in columns
    assert "is_online" not in columns
    assert "last_heartbeat_at" in columns
