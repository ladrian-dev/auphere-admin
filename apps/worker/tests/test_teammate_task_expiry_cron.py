"""El barrido de tareas vencidas corre sin persona y no muere por un fallo."""

from __future__ import annotations

import asyncio

import pytest

from nexus_worker.streams import teammate_task_expiry_cron as cron

pytestmark = pytest.mark.asyncio


async def test_the_sweep_runs_and_stops_when_asked(monkeypatch):
    ticks = {"n": 0}

    async def _sweep() -> int:
        ticks["n"] += 1
        return 2

    monkeypatch.setattr(cron, "sweep_expired_tasks", _sweep)
    stop = asyncio.Event()
    task = asyncio.create_task(cron.run_teammate_task_expiry_cron(stop=stop, tick_seconds=0.01))
    await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(task, timeout=1)
    assert ticks["n"] >= 1


async def test_a_failing_tick_does_not_kill_the_cron(monkeypatch):
    calls = {"n": 0}

    async def _sweep() -> int:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("la base no estaba")
        return 0

    monkeypatch.setattr(cron, "sweep_expired_tasks", _sweep)
    stop = asyncio.Event()
    task = asyncio.create_task(cron.run_teammate_task_expiry_cron(stop=stop, tick_seconds=0.01))
    await asyncio.sleep(0.06)
    stop.set()
    await asyncio.wait_for(task, timeout=1)
    assert calls["n"] >= 2, "un tick que falla se registra y el siguiente ocurre"
