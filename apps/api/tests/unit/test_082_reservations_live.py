"""Spec 082 (requisitos 1.4 a 1.6) — el aviso ``reservations.changed``.

``core.add_event`` marca la sesión con el negocio que cambió, y el aviso sale
por ``inbox:{tenant}`` **después** del commit exterior: una vez por negocio y
por transacción, nunca si se deshace, y sin datos de la reserva ni del cliente.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.db.base import get_sessionmaker
from nexus_api.services.business.writes import drain_after_commit
from nexus_api.services.inbox_stream import RESERVATIONS_EVENT, inbox_channel
from nexus_api.services.reservations.live import mark_changed

pytestmark = pytest.mark.asyncio

A, B = uuid.uuid4(), uuid.uuid4()


@pytest.fixture
async def heard(fake_redis) -> AsyncIterator[Any]:
    pubsub = fake_redis.pubsub()
    await pubsub.subscribe(inbox_channel(A), inbox_channel(B))
    # Las dos confirmaciones de la suscripción: con ``ignore_subscribe_messages``
    # cada una contaría como un «no hay nada» y cortaría la lectura.
    for _ in range(2):
        assert (await pubsub.get_message(timeout=1))["type"] == "subscribe"

    async def read() -> list[tuple[str, dict[str, Any]]]:
        await drain_after_commit()
        out: list[tuple[str, dict[str, Any]]] = []
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.05)
            if msg is None:
                return out
            out.append((str(msg["channel"]), json.loads(msg["data"])))

    yield read
    await pubsub.aclose()


async def test_one_notice_per_business_after_the_commit(heard) -> None:
    async with get_sessionmaker()() as s:
        await s.execute(sa.text("select 1"))
        mark_changed(s, A)
        mark_changed(s, A)
        mark_changed(s, B)
        assert await heard() == [], "salió antes del commit"
        await s.commit()
    got = await heard()
    assert sorted(ch for ch, _ in got) == sorted([inbox_channel(A), inbox_channel(B)])


async def test_the_notice_carries_no_data(heard) -> None:
    async with get_sessionmaker()() as s:
        await s.execute(sa.text("select 1"))
        mark_changed(s, A)
        await s.commit()
    [(_, body)] = await heard()
    assert set(body) == {"event", "at"}
    assert body["event"] == RESERVATIONS_EVENT


async def test_a_rollback_says_nothing(heard) -> None:
    async with get_sessionmaker()() as s:
        await s.execute(sa.text("select 1"))
        mark_changed(s, A)
        await s.rollback()
    assert await heard() == []


async def test_an_undone_savepoint_does_not_swallow_a_later_change(heard) -> None:
    async with get_sessionmaker()() as s:
        await s.execute(sa.text("select 1"))
        nested = await s.begin_nested()
        mark_changed(s, A)
        mark_changed(s, B)
        await nested.rollback()
        mark_changed(s, A)
        await s.commit()
    got = await heard()
    assert [ch for ch, _ in got] == [inbox_channel(A)]


async def test_each_transaction_of_a_session_says_its_own(heard) -> None:
    async with get_sessionmaker()() as s:
        await s.execute(sa.text("select 1"))
        mark_changed(s, A)
        await s.commit()
        await s.execute(sa.text("select 1"))
        mark_changed(s, A)
        await s.commit()
    assert [ch for ch, _ in await heard()] == [inbox_channel(A), inbox_channel(A)]
