"""Las sugerencias semanales de cada agente, en el planificador — spec 047, T174
(requisitos 51.3, 51.5 y 51.6; research D34).

Cada hora, una pasada por los agentes publicados de los clientes de partners con
la consola nueva: a cada uno al que aún no se le leyó la semana pasada (de lunes a
lunes, UTC) se le leen sus conversaciones **dentro de su cliente** y se le
proponen mejoras agregadas. Lo que hay detrás es de la API
(``nexus_api.services.improvement.suggestions``); aquí solo lo que es del worker:

- **el modelo**: el de la tarea ``summarize`` por el proveedor de siempre
  (``runtime/llm.py``), con el modelo del constructor. Con ``llm_use_inmemory``
  (local y pruebas) no hay modelo y no se propone nada; las pruebas pasan uno de
  mentira por ``complete_factory``;
- **el medidor**: cada pasada va en el turno de uso de su trabajo
  (``job:{id}``) con ``source = suggestions``: la partida «Construcción y
  pruebas», nunca la bolsa del cliente. Con la partida agotada, ese partner no
  tiene sugerencias hasta que vuelva a haber sitio;
- **una vez por agente y semana**: la semana queda en el ``progress`` de su
  trabajo; una pasada fallida se reintenta en la hora siguiente, como mucho tres
  veces.

Corre **sin persona** y en el planificador (un solo proceso). Registro:
``run_weekly_suggestions_cron(stop=…)`` con el nombre
``weekly-suggestions-cron``.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import structlog
from nexus_api.services.improvement import suggestions as svc

from nexus_worker.metering.collector import SOURCE_SUGGESTIONS, usage_turn

log = structlog.get_logger(__name__)

#: El nombre de la tarea en el planificador (``bootstrap.py``).
TASK_NAME = "weekly-suggestions-cron"
#: Mira cada hora; a cada agente le toca una vez por semana.
DEFAULT_TICK_SECONDS = 3600.0
#: El papel de la llamada: la tarea ``summarize`` del router.
ROLE = "summarize"

CompleteFactory = Callable[[uuid.UUID], svc.Complete | None]


def default_complete(tenant_id: uuid.UUID) -> svc.Complete | None:
    """El modelo de verdad; ``None`` en local con el proveedor en memoria."""
    from nexus_worker.config import get_worker_settings
    from nexus_worker.jobs.handlers.agent_draft import build_model
    from nexus_worker.runtime.llm import LiteLLMProvider

    if get_worker_settings().llm_use_inmemory:
        return None
    provider = LiteLLMProvider(context_management=None)
    model = build_model()

    async def complete(messages: list[dict[str, str]]) -> str:
        return await provider.acomplete(
            tenant_id=tenant_id, role=ROLE, model=model, messages=messages
        )

    return complete


async def _build_room(partner_id: uuid.UUID) -> bool:
    """¿Le queda «Construcción y pruebas» al partner? Sin sitio, no se genera."""
    from nexus_api.services.wallet.bags import WalletError
    from nexus_api.services.wallet.build_budget import require_room_for_partner

    try:
        await require_room_for_partner(partner_id)
    except WalletError:
        return False
    return True


async def suggestions_tick(
    *,
    complete_factory: CompleteFactory | None = None,
    now: datetime | None = None,
) -> int:
    """Una pasada: las sugerencias que tocan. Devuelve cuántas se crearon."""
    now = now or datetime.now(UTC)
    make_complete = complete_factory or default_complete
    room: dict[uuid.UUID, bool] = {}
    created = 0
    for due in await svc.due_agents(now=now):
        complete = make_complete(due.tenant_id)
        if complete is None:
            continue
        if due.partner_id not in room:
            room[due.partner_id] = await _build_room(due.partner_id)
        if not room[due.partner_id]:
            continue
        try:
            batch = await svc.open_week(
                due.tenant_id, due.agent_id, partner_id=due.partner_id, now=now
            )
            if batch is None:
                continue
            async with usage_turn(
                tenant_id=due.tenant_id,
                turn_id=f"job:{batch.job_id}",
                source=SOURCE_SUGGESTIONS,
                agent_id=due.agent_id,
            ):
                report = await svc.generate(batch, complete=complete, now=now)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error(
                "weekly_suggestions_cron.agent_failed",
                tenant_id=str(due.tenant_id),
                agent_id=str(due.agent_id),
                error=type(exc).__name__,
            )
            continue
        created += len(report.created)
    return created


async def run_weekly_suggestions_cron(
    *,
    stop: asyncio.Event,
    tick_seconds: float = DEFAULT_TICK_SECONDS,
    complete_factory: CompleteFactory | None = None,
) -> None:
    """Cada ``tick_seconds``, la pasada. Vuelve con ``stop``."""
    log.info("weekly_suggestions_cron.start", tick_seconds=tick_seconds)
    while not stop.is_set():
        try:
            created = await suggestions_tick(complete_factory=complete_factory)
            if created:
                log.info("weekly_suggestions_cron.created", created_count=created)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("weekly_suggestions_cron.tick_failed", error=type(exc).__name__)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("weekly_suggestions_cron.stopped")


__all__ = [
    "DEFAULT_TICK_SECONDS",
    "ROLE",
    "TASK_NAME",
    "default_complete",
    "run_weekly_suggestions_cron",
    "suggestions_tick",
]
