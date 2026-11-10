"""Lo común de los tres consumidores de coexistencia — spec 047, T110 (requisitos
30.8, 30.11 y 30.12).

El webhook de Meta deja los ecos, el historial y los contactos de la app WhatsApp
Business en tres streams de Redis (``nexus:meta:echoes``, ``:history`` y
``:state_sync``) y responde enseguida. Hasta la 047 nadie los leía. Cada
consumidor está en su módulo (``meta_echoes_consumer``, ``meta_history_consumer``
y ``meta_state_sync_consumer``); aquí, el bucle que comparten y cómo se encuentra
el número de un evento.

Todos escriben con la RLS del cliente que el webhook ya resolvió (``tenant_id``
viaja en el evento). Un evento que falla va al buzón de descarte con su error y se
acusa: dejarlo en el PEL bloquearía a los de detrás.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
import structlog
from nexus_api.core.streams import xadd_capped
from nexus_api.db.models import Channel
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

IDLE_SECONDS = 2.0
BATCH = 20
GROUP = "coexistence-workers"

Handler = Callable[[dict[str, str]], Awaitable[str]]


def decode(raw: dict[Any, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in raw.items():
        ks = key.decode() if isinstance(key, bytes) else str(key)
        vs = value.decode() if isinstance(value, bytes) else str(value)
        out[ks] = vs
    return out


def digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def parse_ts(raw: Any) -> datetime | None:
    """Meta manda segundos epoch como texto; ISO en lo que ya pasó por el webhook."""
    if raw in (None, ""):
        return None
    text = str(raw)
    if text.isdigit():
        return datetime.fromtimestamp(int(text), UTC)
    with contextlib.suppress(ValueError):
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


async def find_channel(
    session: AsyncSession, *, phone_number_id: str | None, business_phone: str | None = None
) -> Channel | None:
    """El número de Meta del evento, dentro del cliente de la sesión: por su
    ``phone_number_id`` y, si no, por el número que se ve."""
    base = sa.select(Channel).where(Channel.provider == "meta")
    if phone_number_id:
        found: Channel | None = await session.scalar(
            base.where(Channel.config["phone_number_id"].astext == phone_number_id).limit(1)
        )
        if found is not None:
            return found
    wanted = digits(business_phone)
    if wanted:
        for channel in (await session.scalars(base)).all():
            if digits(channel.provider_identifier) == wanted:
                return channel
    return None


async def ensure_group(redis: Any, stream: str) -> None:
    from redis.exceptions import ResponseError

    try:
        await redis.xgroup_create(stream, GROUP, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def drain_once(redis: Any, stream: str, handler: Handler, *, consumer_name: str) -> int:
    """Una pasada: lee hasta ``BATCH`` eventos, aplica cada uno y lo acusa."""
    await ensure_group(redis, stream)
    batches = await redis.xreadgroup(GROUP, consumer_name, {stream: ">"}, count=BATCH, block=100)
    entries = [entry for _stream, items in (batches or []) for entry in items]
    for raw_id, raw_fields in entries:
        entry_id = raw_id.decode() if isinstance(raw_id, bytes) else str(raw_id)
        fields = decode(raw_fields)
        try:
            status = await handler(fields)
            log.info("coexistence.applied", stream=stream, entry_id=entry_id, status=status)
        except Exception as exc:
            log.error(
                "coexistence.dead_lettered",
                stream=stream,
                entry_id=entry_id,
                tenant_id=fields.get("tenant_id"),
                error=str(exc)[:200],
            )
            await xadd_capped(
                redis,
                f"{stream}:dlq",
                {
                    **fields,
                    "dlq_source_stream": stream,
                    "dlq_source_entry_id": entry_id,
                    "dlq_error": str(exc)[:500],
                },
            )
        await redis.xack(stream, GROUP, entry_id)
    return len(entries)


async def run_consumer(
    redis: Any,
    stream: str,
    handler: Handler,
    *,
    stop: asyncio.Event,
    consumer_name: str,
    idle_seconds: float = IDLE_SECONDS,
) -> None:
    """El bucle de un consumidor de la familia runner. Sale con ``stop``; un
    fallo de una pasada no lo mata."""
    log.info("coexistence.consumer_start", stream=stream, group=GROUP)
    while not stop.is_set():
        try:
            attended = await drain_once(redis, stream, handler, consumer_name=consumer_name)
            if attended == 0:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=idle_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("coexistence.consumer_tick_failed", stream=stream, error=str(exc)[:200])
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=1.0)
    log.info("coexistence.consumer_stopped", stream=stream)


def tenant_of(fields: dict[str, str]) -> uuid.UUID:
    return uuid.UUID(fields["tenant_id"])


__all__ = [
    "GROUP",
    "decode",
    "digits",
    "drain_once",
    "find_channel",
    "parse_ts",
    "run_consumer",
    "tenant_of",
]
