"""Spec 064, requisito 2 — corregir una «Atendida» por la API de la consola.

La cita la cierra el cron (``done``); el reloj de la API se fija después de su
hora de fin. «No vino» y «Deshacer» dejan su evento con la persona, no escriben
al cliente final y mueven la cifra del mes.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from nexus_api.services.reservations import automation
from tests.conftest import future_day, make_reservas
from tests.integration.reservas._worker import (
    book,
    events,
    local,
    outbox,
    reservation,
    scoped,
    set_status,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

BASE = "/console/lite/reservas"
TZ = ZoneInfo("America/Santiago")


@pytest.fixture
async def salon(db_session, console_world) -> dict[str, Any]:
    w = console_world["a"]
    return await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])


@pytest.fixture
async def resto(db_session, console_world) -> dict[str, Any]:
    w = console_world["a"]
    return await make_reservas(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"], mode="capacity"
    )


def _clock(monkeypatch: pytest.MonkeyPatch, now: datetime) -> None:
    monkeypatch.setattr("nexus_api.api.console.lite.reservas._now", lambda: now)


async def _closed(shop: dict[str, Any], day: Any) -> Any:
    """Una cita de Servicios de las 10:00 que el cron cerró como ``done``."""
    res_id = await book(
        shop["tenant_id"], day=day, at="10:00", staff=shop["lucia"], service=shop["corte"]
    )
    async with scoped(shop["tenant_id"]) as s:
        assert await automation.mark_done(s, local(day, "10:31")) == 1
    return res_id


async def _act(client, shop, res_id, action: str) -> Any:
    row = await reservation(shop["tenant_id"], res_id)
    return await client.post(
        f"{BASE}/bookings/{res_id}/{action}",
        headers={**shop["headers"](), "If-Match": str(row.version)},
    )


async def test_a_closed_booking_is_corrected_and_put_back(client, salon, monkeypatch) -> None:
    day = future_day()
    res_id = await _closed(salon, day)
    # El mismo día por la noche: dentro de la ventana y dentro del mes.
    _clock(monkeypatch, datetime.combine(day, time(22, 0), tzinfo=TZ))
    before = len(await outbox(salon["tenant_id"]))

    detail = (await client.get(f"{BASE}/bookings/{res_id}", headers=salon["headers"]())).json()
    assert detail["status"] == "done"
    assert detail["allowed"] == ["noshow"]

    r = await _act(client, salon, res_id, "noshow")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "noshow"
    assert body["allowed"] == ["undo"]
    summary = (await client.get(f"{BASE}/summary", headers=salon["headers"]())).json()
    assert summary["month"]["noshow_pct"] == 100

    r = await _act(client, salon, res_id, "undo")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"
    assert r.json()["allowed"] == ["noshow"]
    summary = (await client.get(f"{BASE}/summary", headers=salon["headers"]())).json()
    assert summary["month"]["noshow_pct"] == 0

    # Quién lo hizo queda en el historial, y nada sale por WhatsApp.
    trail = await events(salon["tenant_id"], res_id)
    assert [(k, who) for k, who, _ in trail][-3:] == [
        ("done", "system"),
        ("noshow", "person"),
        ("undone", "person"),
    ]
    assert len(await outbox(salon["tenant_id"])) == before


async def test_after_seven_days_it_is_final(client, salon, monkeypatch) -> None:
    day = future_day()
    res_id = await _closed(salon, day)
    _clock(monkeypatch, datetime.combine(day + timedelta(days=8), time(9, 0), tzinfo=TZ))
    detail = (await client.get(f"{BASE}/bookings/{res_id}", headers=salon["headers"]())).json()
    assert detail["allowed"] == []
    r = await _act(client, salon, res_id, "noshow")
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "invalid_transition"


async def test_capacity_is_not_corrected(client, resto, monkeypatch) -> None:
    day = future_day()
    res_id = await book(resto["tenant_id"], day=day, at="13:00")
    await set_status(resto["tenant_id"], res_id, "done")
    _clock(monkeypatch, datetime.combine(day, time(22, 0), tzinfo=TZ))
    r = await _act(client, resto, res_id, "noshow")
    assert r.status_code == 409, r.text


async def test_the_cron_still_closes_and_leaves_a_noshow_alone(client, salon, monkeypatch) -> None:
    day = future_day()
    res_id = await _closed(salon, day)
    _clock(monkeypatch, datetime.combine(day, time(22, 0), tzinfo=TZ))
    assert (await _act(client, salon, res_id, "noshow")).status_code == 200
    other = await book(
        salon["tenant_id"], day=day, at="11:00", staff=salon["lucia"], service=salon["corte"]
    )
    async with scoped(salon["tenant_id"]) as s:
        # Cierra la que terminó y no vuelve a tocar la corregida.
        assert await automation.mark_done(s, local(day, "23:00")) == 1
    assert (await reservation(salon["tenant_id"], res_id)).status == "noshow"
    assert (await reservation(salon["tenant_id"], other)).status == "done"
