"""Spec 064, requisito 5.2 — ``inbox-autoclose-cron``.

Cada 5 minutos, en el planificador. Recorre los clientes activos, cada uno en
su sesión acotada, y avisa a la Bandeja de cada conversación cerrada **después**
de confirmar la transacción. Un cliente que falla no para a los demás.

Qué se cierra y qué no se prueba contra Postgres en
``apps/api/tests/integration/test_064_conversation_cycle.py``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest

from nexus_worker import bootstrap
from nexus_worker.streams import inbox_autoclose_cron as cron

NAME = "inbox-autoclose-cron"


def test_it_runs_every_five_minutes_in_the_scheduler() -> None:
    assert cron.DEFAULT_TICK_SECONDS == 5 * 60
    assert NAME in bootstrap.SCHEDULER_TASK_NAMES
    assert NAME not in bootstrap.RUNNER_TASK_NAMES
    assert NAME not in bootstrap.EGRESS_TASK_NAMES


class _World:
    """Three clients; the second one fails. Records the order of what happens."""

    def __init__(self) -> None:
        self.tenants = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
        self.closed = {
            self.tenants[0]: [uuid.uuid4(), uuid.uuid4()],
            self.tenants[2]: [uuid.uuid4()],
        }
        self.log: list[tuple[str, Any]] = []

    @asynccontextmanager
    async def scoped(self, _session: Any, tenant_id: uuid.UUID) -> AsyncIterator[None]:
        self.log.append(("begin", tenant_id))
        try:
            yield
        except Exception:
            self.log.append(("rollback", tenant_id))
            raise
        else:
            self.log.append(("commit", tenant_id))

    @asynccontextmanager
    async def session(self) -> AsyncIterator[object]:
        yield object()

    async def tick(self, _session: Any, tenant_id: uuid.UUID, _now: datetime) -> list[uuid.UUID]:
        if tenant_id == self.tenants[1]:
            raise RuntimeError("boom")
        return self.closed.get(tenant_id, [])

    async def publish(
        self, _redis: Any, *, tenant_id: uuid.UUID, event: str, conversation_id: uuid.UUID
    ) -> None:
        self.log.append(("publish", (tenant_id, event, conversation_id)))


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> _World:
    w = _World()

    async def tenants(_sm: Any) -> list[uuid.UUID]:
        return list(w.tenants)

    monkeypatch.setattr(cron, "active_tenant_ids", tenants)
    monkeypatch.setattr(cron, "tenant_scoped_session", w.scoped)
    monkeypatch.setattr(cron.inbox_lifecycle, "autoclose_tick", w.tick)
    monkeypatch.setattr(cron, "publish_inbox_event", w.publish)
    return w


async def test_a_pass_closes_each_client_in_its_own_session(world: _World) -> None:
    total = await cron.cron_pass(world.session, redis=None, now=datetime.now(UTC))
    assert total == 3
    assert [t for kind, t in world.log if kind == "begin"] == world.tenants


async def test_it_tells_the_inbox_only_after_the_commit(world: _World) -> None:
    await cron.cron_pass(world.session, redis=None, now=datetime.now(UTC))
    first = world.tenants[0]
    commit = world.log.index(("commit", first))
    published = [
        i for i, (kind, what) in enumerate(world.log) if kind == "publish" and what[0] == first
    ]
    assert len(published) == 2 and all(i > commit for i in published)
    assert {what[1] for kind, what in world.log if kind == "publish"} == {"conversation.updated"}
    assert [
        what[2] for kind, what in world.log if kind == "publish" and what[0] == first
    ] == world.closed[first]


async def test_a_client_that_fails_does_not_stop_the_rest(world: _World) -> None:
    total = await cron.cron_pass(world.session, redis=None, now=datetime.now(UTC))
    failed, last = world.tenants[1], world.tenants[2]
    assert ("rollback", failed) in world.log
    assert not [w for kind, w in world.log if kind == "publish" and w[0] == failed]
    assert ("commit", last) in world.log
    assert total == 3  # los dos de la primera y el de la tercera
