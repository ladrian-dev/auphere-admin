"""Las pasadas de una suite terminan a la vez que su trabajo (bug
``pasadas-huerfanas-tras-fallar-el-trabajo``). La prueba con base y consumidor está en
``apps/api/tests/integration/builder/test_one_suite_at_a_time.py``; aquí, los dos caminos
por los que una se puede quedar corriendo."""

from __future__ import annotations

import asyncio

import pytest

from nexus_worker.jobs.handlers.agent_tests import _all_or_none

pytestmark = pytest.mark.asyncio


class Passes:
    def __init__(self) -> None:
        self.started = 0
        self.cancelled = 0
        self.finished = 0
        self.release = asyncio.Event()

    async def waits(self) -> None:
        self.started += 1
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        self.finished += 1


async def test_the_first_failure_comes_out_with_nothing_left_running() -> None:
    passes = Passes()

    async def blows_up() -> None:
        await asyncio.sleep(0)
        raise RuntimeError("la primera")

    before = asyncio.all_tasks()
    with pytest.raises(RuntimeError, match="la primera"):
        await _all_or_none([passes.waits(), blows_up(), passes.waits()])

    assert passes.started == passes.cancelled == 2
    assert asyncio.all_tasks() == before, "ninguna tarea sigue viva"


async def test_when_the_job_runs_out_of_time_they_all_stop() -> None:
    passes = Passes()
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(_all_or_none([passes.waits(), passes.waits()]), timeout=0.01)
    assert passes.started == passes.cancelled == 2


async def test_without_a_failure_they_all_finish() -> None:
    passes = Passes()
    passes.release.set()
    await _all_or_none([passes.waits(), passes.waits(), passes.waits()])
    assert passes.finished == 3 and passes.cancelled == 0
