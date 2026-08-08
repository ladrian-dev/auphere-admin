"""``nexus-scheduler`` — crons and sweeps. Runs as a singleton (WP-08 adds
advisory locks so a second replica during a rollout duplicates nothing)."""

from __future__ import annotations

import asyncio

from nexus_worker.bootstrap import run_service
from nexus_worker.logging import configure_logging


def run() -> None:
    configure_logging()
    asyncio.run(run_service("nexus-scheduler", scheduler=True))


if __name__ == "__main__":
    run()
