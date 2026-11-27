"""Spec 082 — la garantía 1 en la línea en vivo, con Reservas dentro.

El aviso ``reservations.changed`` viaja por el canal del negocio
(``inbox:{tenant}``), y la línea lo toma del negocio de la sesión, nunca de
quien llama. Desde la 082 la línea admite a una persona con Reservas y sin
Bandeja. Lo que se fija aquí:

- la línea de una persona del negocio A solo reenvía lo publicado en A;
- cada persona recibe solo los avisos de sus módulos: Reservas sin Bandeja no
  oye conversaciones, Bandeja sin Reservas no oye reservas;
- sin ninguno de los dos módulos, la línea no se abre (403);
- una escritura real de Reservas en A avisa a A y a nadie más, y sin datos.
"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from nexus_api.api.console.lite import inbox_stream as stream_route
from nexus_api.services.business.writes import drain_after_commit
from nexus_api.services.inbox_stream import (
    RESERVATIONS_EVENT,
    inbox_channel,
    publish_inbox_event,
    publish_reservations_changed,
)
from tests.conftest import add_client_member, future_day, make_client_access, make_reservas

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

STREAM = "/console/lite/inbox/stream"


class _Request:
    def __init__(self, turns: int) -> None:
        self.turns = turns

    async def is_disconnected(self) -> bool:
        self.turns -= 1
        return self.turns < 0


def _principal(tenant_id: uuid.UUID, *modules: str) -> Any:
    return SimpleNamespace(tenant_id=tenant_id, phone_id=None, has=lambda m: m in modules)


async def _heard(fake_redis: Any, principal: Any, publish: Any) -> list[dict[str, Any]]:
    response = await stream_route.stream(
        request=_Request(turns=6),  # type: ignore[arg-type]
        principal=principal,
        redis=fake_redis,
    )
    events = response.body_iterator.__aiter__()
    assert (await events.__anext__())["event"] == "ready"
    await publish()
    return [e for e in [e async for e in events] if e["event"] != "ping"]


@pytest.fixture(autouse=True)
def _fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stream_route, "HEARTBEAT_SECONDS", 0.01)


async def test_a_line_relays_only_its_own_business(fake_redis) -> None:
    mine, theirs = uuid.uuid4(), uuid.uuid4()

    async def publish() -> None:
        await publish_reservations_changed(fake_redis, tenant_id=theirs)
        await publish_reservations_changed(fake_redis, tenant_id=mine)

    got = await _heard(fake_redis, _principal(mine, "reservas"), publish)
    assert [e["event"] for e in got] == [RESERVATIONS_EVENT]


async def test_reservas_without_inbox_hears_no_conversation(fake_redis) -> None:
    mine = uuid.uuid4()

    async def publish() -> None:
        await publish_inbox_event(
            fake_redis, tenant_id=mine, event="message.new", conversation_id=uuid.uuid4()
        )
        await publish_reservations_changed(fake_redis, tenant_id=mine)

    got = await _heard(fake_redis, _principal(mine, "reservas"), publish)
    assert [e["event"] for e in got] == [RESERVATIONS_EVENT]


async def test_inbox_without_reservas_hears_no_booking(fake_redis) -> None:
    mine, conv = uuid.uuid4(), uuid.uuid4()

    async def publish() -> None:
        await publish_reservations_changed(fake_redis, tenant_id=mine)
        await publish_inbox_event(
            fake_redis, tenant_id=mine, event="message.new", conversation_id=conv
        )

    got = await _heard(fake_redis, _principal(mine, "inbox"), publish)
    assert [e["event"] for e in got] == ["message.new"]


async def test_without_inbox_or_reservas_the_line_does_not_open(
    client, db_session, console_world
) -> None:
    w = console_world["a"]
    await make_client_access(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"], modules=("panel",)
    )
    member = await add_client_member(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"]
    )
    assert (await client.get(STREAM, headers=member["headers"]())).status_code == 403


async def test_a_real_booking_write_tells_only_its_business(
    client, db_session, console_world, fake_redis
) -> None:
    a, b = console_world["a"], console_world["b"]
    shop = await make_reservas(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
    pubsub = fake_redis.pubsub()
    await pubsub.subscribe(inbox_channel(a["tenant_id"]), inbox_channel(b["tenant_id"]))
    for _ in range(2):  # las confirmaciones; si no, la primera lectura vacía corta el bucle
        assert (await pubsub.get_message(timeout=1))["type"] == "subscribe"
    h = shop["headers"]
    made = await client.post(
        "/console/lite/reservas/bookings",
        headers=h(),
        json={
            "date": future_day().isoformat(),
            "time": "10:00",
            "staff_id": str(shop["lucia"]),
            "service_id": str(shop["corte"]),
            "contact": {"name": "Ana Pérez", "phone": "+56911112222"},
        },
    )
    assert made.status_code == 201, made.text
    booking = made.json()
    cancelled = await client.post(
        f"/console/lite/reservas/bookings/{booking['id']}/cancel",
        headers={**h(), "If-Match": str(booking["version"])},
        json={"notify": False, "offer_slot": False},
    )
    assert cancelled.status_code == 200, cancelled.text
    await drain_after_commit()

    heard: list[tuple[str, str]] = []
    while (
        msg := await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.05)
    ) is not None:
        heard.append((str(msg["channel"]), str(msg["data"])))
    await pubsub.aclose()

    assert heard, "la escritura de Reservas no avisó"
    assert {ch for ch, _ in heard} == {inbox_channel(a["tenant_id"])}
    for _, raw in heard:
        body = json.loads(raw)
        assert body["event"] == RESERVATIONS_EVENT
        # Sin datos: ni la reserva, ni el nombre, ni el teléfono.
        assert set(body) == {"event", "at"}
        assert booking["id"] not in raw and "Ana" not in raw and "5691111" not in raw
