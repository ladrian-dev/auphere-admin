"""Spec 043, requisito 15.4 y 15.5 — ``reservation-templates-cron``.

Cada 15 minutos, en la familia del planificador, y con un cliente de Meta que no
reintenta: una llamada que falla se vuelve a intentar en la pasada siguiente, no
dentro de esta.
"""

from __future__ import annotations

from nexus_worker import bootstrap
from nexus_worker.streams import reservation_templates_cron as cron


def test_it_runs_every_fifteen_minutes_in_the_scheduler() -> None:
    assert cron.DEFAULT_TICK_SECONDS == 15 * 60
    assert "reservation-templates-cron" in bootstrap.SCHEDULER_TASK_NAMES
    assert "reservation-templates-cron" not in bootstrap.RUNNER_TASK_NAMES
    assert "reservation-templates-cron" not in bootstrap.EGRESS_TASK_NAMES


async def test_its_meta_client_makes_one_attempt_per_call() -> None:
    client = cron.build_client()
    try:
        assert client._max_retries == 1
    finally:
        await client.close()
