"""All-in-one worker entry point.

WP-07 split the worker into three services (``nexus-runner``,
``nexus-scheduler``, ``nexus-egress`` — see ``bootstrap.py`` for the task
map). This module keeps the historical single-process shape:

- **local dev**: one process, everything running, no orchestration.
- **rollback path**: if the split deployment misbehaves, returning to a
  single service is a ``startCommand`` change back to ``nexus-worker`` —
  no code revert needed.

Production runs the three entrypoints; tests build the same components
piece-by-piece in fixtures so they can substitute the in-memory provider,
the in-memory checkpointer and a fake Redis.
"""

from __future__ import annotations

import asyncio

from nexus_worker.bootstrap import run_service
from nexus_worker.logging import configure_logging

configure_logging()


async def _amain() -> None:
    await run_service("nexus-worker", runner=True, scheduler=True, egress=True)


def run() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    run()
