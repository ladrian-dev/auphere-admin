"""``nexus-runner`` — inbound turns. Scales horizontally by queue lag."""

from __future__ import annotations

import asyncio

from nexus_worker.bootstrap import run_service
from nexus_worker.logging import configure_logging


def run() -> None:
    configure_logging()
    asyncio.run(run_service("nexus-runner", runner=True))


if __name__ == "__main__":
    run()
