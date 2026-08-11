"""WP-07: the three-service split covers every task exactly once.

The dangerous failure modes of splitting a 20-task process are silent: a
task assigned to two families runs twice (duplicate sends, duplicate crons)
and a task assigned to none dies without a trace. These tests pin the
name-contract and that the factories actually produce it.
"""

from __future__ import annotations

import asyncio
import contextlib
from types import SimpleNamespace

import pytest

from nexus_worker import bootstrap
from nexus_worker.config import get_worker_settings

pytestmark = pytest.mark.asyncio

# The full task inventory of the pre-split worker (main.py at WP-06) plus
# the per-service heartbeat. If a new task is added to a family, add it
# here too — consciously.
ALL_EXPECTED = {
    "heartbeat",
    "promote-subscriber",
    "inbound-consumer",
    "stream-claimer",
    "owner-fanout-consumer",
    "outbound-dispatcher",
    "owner-outbox-dispatcher",
    "operator-alerter",
    "grade-consumer",
    "platform-watcher",
    "reminder-cron",
    "agent-sales-poll-cron",
    "partner-receipt-cron",
    "isolation-event-drainer",
    "no-show-scrape-cron",
    "cost-rollup-cron",
    "isolation-watcher",
    "whatsapp-health-cron",
    "tiktok-token-refresh-cron",
    "async-booking-cron",
    "continuous-eval-cron",
    "memory-versions-retention-cron",
    "owner-consultation-timeout-sweep",
    "owner-fanout-sweep",
    "connector-reconcile-cron",
    # WP-13
    "partition-maintenance-cron",
    "checkpoint-retention-cron",
    # WP-29
    "data-retention-cron",
}


def test_families_are_disjoint_and_complete() -> None:
    overlap_rs = bootstrap.RUNNER_TASK_NAMES & bootstrap.SCHEDULER_TASK_NAMES
    overlap_re = bootstrap.RUNNER_TASK_NAMES & bootstrap.EGRESS_TASK_NAMES
    overlap_se = bootstrap.SCHEDULER_TASK_NAMES & bootstrap.EGRESS_TASK_NAMES
    # Heartbeat is per-process by design; nothing else may repeat.
    assert overlap_rs == {"heartbeat"}
    assert overlap_re == {"heartbeat"}
    assert overlap_se == {"heartbeat"}
    union = (
        bootstrap.RUNNER_TASK_NAMES | bootstrap.SCHEDULER_TASK_NAMES | bootstrap.EGRESS_TASK_NAMES
    )
    assert union == ALL_EXPECTED


def _dummy_ctx() -> SimpleNamespace:
    return SimpleNamespace(
        service_name="nexus-test",
        worker_settings=get_worker_settings(),
        redis=object(),
        stop=asyncio.Event(),
        loader=object(),
        channel_adapters={},
        meta_client=object(),
        agendapro_public_pool=object(),
        outcome_grader=None,
    )


async def _names_of(tasks: list[asyncio.Task]) -> set[str]:
    names = {t.get_name() for t in tasks}
    for t in tasks:
        t.cancel()
    with contextlib.suppress(Exception):
        await asyncio.gather(*tasks, return_exceptions=True)
    return names


async def test_factories_produce_the_contract() -> None:
    ctx = _dummy_ctx()
    assert await _names_of(bootstrap.runner_tasks(ctx, pipeline=None)) == set(
        bootstrap.RUNNER_TASK_NAMES
    )
    assert await _names_of(bootstrap.scheduler_tasks(ctx)) == set(bootstrap.SCHEDULER_TASK_NAMES)
    assert await _names_of(bootstrap.egress_tasks(ctx)) == set(bootstrap.EGRESS_TASK_NAMES)


async def test_combined_families_have_one_heartbeat() -> None:
    ctx = _dummy_ctx()
    tasks = (
        bootstrap.runner_tasks(ctx, pipeline=None)
        + bootstrap.scheduler_tasks(ctx, heartbeat=False)
        + bootstrap.egress_tasks(ctx, heartbeat=False)
    )
    names = [t.get_name() for t in tasks]
    assert names.count("heartbeat") == 1
    for t in tasks:
        t.cancel()
    with contextlib.suppress(Exception):
        await asyncio.gather(*tasks, return_exceptions=True)
