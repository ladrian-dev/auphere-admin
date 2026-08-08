"""WP-08: two schedulers against the same database — one set of effects.

``run_exclusive`` is the property under test: the second instance stays
hot-standby (its task family never starts), and takes over when the leader
releases. Uses the real Postgres advisory lock — that IS the mechanism.
"""

from __future__ import annotations

import asyncio

import pytest

from nexus_api.core.leader import run_exclusive

pytestmark = pytest.mark.asyncio

LOCK = "nexus:test-scheduler-singleton"


def _family(tag: str, journal: list[str]):
    """A stand-in cron family: notes that it started, then idles."""

    def start() -> list[asyncio.Task]:
        async def body() -> None:
            journal.append(tag)
            await asyncio.sleep(60)

        return [asyncio.create_task(body(), name=f"family-{tag}")]

    return start


async def test_second_scheduler_is_standby_and_takes_over(db_session) -> None:
    journal: list[str] = []
    stop_a = asyncio.Event()
    stop_b = asyncio.Event()

    task_a = asyncio.create_task(
        run_exclusive(
            LOCK,
            stop=stop_a,
            start_tasks=_family("a", journal),
            retry_seconds=0.1,
            ping_seconds=0.5,
        )
    )
    await asyncio.sleep(0.5)
    task_b = asyncio.create_task(
        run_exclusive(
            LOCK,
            stop=stop_b,
            start_tasks=_family("b", journal),
            retry_seconds=0.1,
            ping_seconds=0.5,
        )
    )
    await asyncio.sleep(1.0)

    # Exactly one family running while both instances are alive.
    assert journal == ["a"]

    # Leader stops → lock released → the standby must take over.
    stop_a.set()
    await asyncio.wait_for(task_a, timeout=5.0)
    for _ in range(50):
        if "b" in journal:
            break
        await asyncio.sleep(0.1)
    assert journal == ["a", "b"]

    stop_b.set()
    await asyncio.wait_for(task_b, timeout=5.0)


async def test_family_stops_when_leadership_lost(db_session) -> None:
    """A cancelled leader term cancels its family tasks (no zombie crons)."""
    journal: list[str] = []
    stop = asyncio.Event()
    family_tasks: list[asyncio.Task] = []

    def start() -> list[asyncio.Task]:
        async def body() -> None:
            journal.append("started")
            await asyncio.sleep(60)

        task = asyncio.create_task(body())
        family_tasks.append(task)
        return [task]

    leader = asyncio.create_task(
        run_exclusive(LOCK + ":lost", stop=stop, start_tasks=start, retry_seconds=0.1, ping_seconds=0.2)
    )
    await asyncio.sleep(0.5)
    assert journal == ["started"]

    stop.set()
    await asyncio.wait_for(leader, timeout=5.0)
    assert family_tasks[0].cancelled() or family_tasks[0].done()
