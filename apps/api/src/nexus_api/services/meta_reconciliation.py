"""Lo que Meta entregó, por canal y día — spec 047, requisito 2.6 (T037).

El webhook anota aquí el ``wamid`` de cada entrante que Meta le entrega y que
encola: un conjunto de Redis por canal y día (UTC), que caduca solo. El cron
diario del worker (``nexus_worker.streams.meta_reconciliation_cron``) lo cuadra
con los entrantes guardados en ``messages``: lo que está aquí y no en la base
se perdió entre el webhook y la base.

**Solo identificadores.** Ni el cuerpo, ni el teléfono, ni el nombre: un
``wamid`` y la hora (§I, ``contracts/events.md`` §5).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import structlog
from redis.asyncio import Redis

log = structlog.get_logger(__name__)

_PREFIX = "nexus:meta:delivered"
#: El día se cuadra al día siguiente; dos días de margen por si el cron cae.
DELIVERED_TTL_S = 4 * 24 * 3600


def delivered_key(channel_id: uuid.UUID, day: date) -> str:
    return f"{_PREFIX}:{channel_id}:{day.isoformat()}"


async def record_delivered(
    redis: Redis, *, channel_id: uuid.UUID, wamid: str, at: datetime | None = None
) -> None:
    """Anota un entrante entregado. Nunca lanza: perder la anotación cuesta un
    falso positivo en el cuadre, no un mensaje."""
    day = (at or datetime.now(UTC)).astimezone(UTC).date()
    key = delivered_key(channel_id, day)
    try:
        await redis.sadd(key, wamid)
        await redis.expire(key, DELIVERED_TTL_S)
    except Exception as exc:  # pragma: no cover - Redis caído: el webhook sigue
        log.warning("meta_reconciliation.record_failed", channel_id=str(channel_id), error=str(exc))


__all__ = ["DELIVERED_TTL_S", "delivered_key", "record_delivered"]
