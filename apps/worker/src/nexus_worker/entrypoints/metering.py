"""``nexus-metering`` — ingesta de consumo (WP-18).

Servicio propio y no una tarea más del runner: su trabajo es escribir en
una tabla de facturación y no debe competir por los slots del turno ni
caerse con él. Escala por profundidad de ``nexus:usage``; las réplicas se
reparten el trabajo por grupo de consumidores, sin líder.
"""

from __future__ import annotations

import asyncio

from nexus_worker.bootstrap import run_service
from nexus_worker.logging import configure_logging


def run() -> None:
    configure_logging()
    asyncio.run(run_service("nexus-metering", metering=True))


if __name__ == "__main__":
    run()
