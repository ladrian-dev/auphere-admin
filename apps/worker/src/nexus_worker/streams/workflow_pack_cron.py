"""Existing scheduler: tick workflow_crons. Dead crons do not fire."""

from __future__ import annotations

import asyncio
import contextlib

import structlog
from nexus_api.packs.cron import process_due_workflow_crons  # type: ignore[import-untyped]

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 30.0


async def run_workflow_pack_cron(
    *,
    stop: asyncio.Event,
    tick_seconds: float = DEFAULT_TICK_SECONDS,
) -> None:
    log.info("workflow_pack_cron.start", tick_seconds=tick_seconds)
    while not stop.is_set():
        try:
            fired = await process_due_workflow_crons()
            if fired:
                log.info("workflow_pack_cron.tick", fired=fired)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("workflow_pack_cron.tick_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("workflow_pack_cron.stopped")
