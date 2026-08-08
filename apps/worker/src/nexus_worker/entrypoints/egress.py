"""``nexus-egress`` — outbound delivery. Scales by pending outbound rows;
replicas coordinate via ``SKIP LOCKED``, no leader needed."""

from __future__ import annotations

import asyncio

from nexus_worker.bootstrap import run_service
from nexus_worker.logging import configure_logging


def run() -> None:
    configure_logging()
    asyncio.run(run_service("nexus-egress", egress=True))


if __name__ == "__main__":
    run()
