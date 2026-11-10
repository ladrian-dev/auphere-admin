"""Conciliación diaria con Meta — spec 047, T037 (requisito 2.6).

Cada día se cuadra, por canal, lo que Meta entregó al webhook con lo que quedó
guardado. El webhook anota el ``wamid`` de cada entrante que encola
(``nexus_api.services.meta_reconciliation``); este cron lo busca en
``messages``. Lo que Meta entregó y la base no tiene se perdió por el camino
—el stream, el consumidor, la DLQ— y es exactamente lo que el requisito 2 dice
que no puede pasar: Auphere se entera (``ops.meta_reconciliation``, en el admin
y en el registro con nivel de error, una vez al día). Desde la spec 051
(requisito 9.2) no hay correo: lo recoge la monitorización.

- **Por ``wamid``, no por hora.** Un mensaje entregado a las 23:59:59 y guardado
  a las 00:00:01 está guardado; se busca con una hora de margen a cada lado.
- **Idempotente.** Cada canal y día deja una fila en
  ``meta_reconciliation_runs`` (la vista del admin es T172) y un día ya cuadrado
  no se vuelve a cuadrar ni a avisar. El cron mira cada hora y cuadra el día de
  ayer: sobrevive a un reinicio, a un despliegue y a una réplica de más.
- **Un día sin anotaciones no se cuadra.** Sin conjunto en Redis (no hubo
  tráfico, o caducó) no hay con qué comparar, y una fila de ceros no dice nada.
- **Sin texto.** Ni cuerpos ni teléfonos: identificadores y cuentas (§I).

Corre en la familia del scheduler (elección de líder: una instancia).
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import sqlalchemy as sa
import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Channel, MetaReconciliationRun, Tenant
from nexus_api.services.meta_reconciliation import delivered_key
from redis.asyncio import Redis
from sqlalchemy.dialects.postgresql import insert as pg_insert

log = structlog.get_logger(__name__)

#: El nombre de la tarea en el planificador (``wk/bootstrap.py``).
TASK_NAME = "meta-reconciliation-cron"
#: Mira cada hora; cuadra el día de ayer una sola vez.
DEFAULT_TICK_SECONDS = 3600.0
#: El margen alrededor del día para encontrar lo guardado.
_MARGIN = timedelta(hours=1)

_STORED_SQL = sa.text(
    """
    SELECT DISTINCT m.provider_message_id
      FROM messages m
      JOIN conversations c ON c.id = m.conversation_id
     WHERE c.channel_id = :ch
       AND m.direction = 'inbound'
       AND m.provider_message_id = ANY(CAST(:wamids AS text[]))
       AND m.created_at >= :since
       AND m.created_at < :until
    """
)


@dataclass
class ReconciliationReport:
    day: date
    channels: int = 0
    channels_with_diff: int = 0
    missing: int = 0
    diffs: list[dict[str, Any]] = field(default_factory=list)


def _decode(values: Any) -> list[str]:
    return sorted(v.decode() if isinstance(v, bytes) else str(v) for v in (values or ()))


async def _reconcile_tenant(
    tenant_id: uuid.UUID, day: date, redis: Redis, report: ReconciliationReport
) -> None:
    start = datetime.combine(day, time.min, tzinfo=UTC)
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        channel_ids = list(
            (await session.execute(sa.select(Channel.id).where(Channel.provider == "meta")))
            .scalars()
            .all()
        )
        if not channel_ids:
            return
        done = set(
            (
                await session.execute(
                    sa.select(MetaReconciliationRun.channel_id).where(
                        MetaReconciliationRun.date == day
                    )
                )
            )
            .scalars()
            .all()
        )
        for channel_id in channel_ids:
            if channel_id in done:
                continue
            delivered = _decode(await redis.smembers(delivered_key(channel_id, day)))
            if not delivered:
                continue
            stored = set(
                (
                    await session.execute(
                        _STORED_SQL,
                        {
                            "ch": channel_id,
                            "wamids": delivered,
                            "since": start - _MARGIN,
                            "until": start + timedelta(days=1) + _MARGIN,
                        },
                    )
                )
                .scalars()
                .all()
            )
            stored_count = len(stored)
            diff = len(delivered) - stored_count
            await session.execute(
                pg_insert(MetaReconciliationRun)
                .values(
                    tenant_id=tenant_id,
                    channel_id=channel_id,
                    date=day,
                    meta_count=len(delivered),
                    stored_count=stored_count,
                    diff=diff,
                )
                .on_conflict_do_nothing(constraint="uq_meta_reconciliation_day")
            )
            report.channels += 1
            if diff:
                report.channels_with_diff += 1
                report.missing += diff
                report.diffs.append(
                    {"tenant_id": str(tenant_id), "channel_id": str(channel_id), "missing": diff}
                )


async def reconcile_day(day: date, *, redis: Redis | None = None) -> ReconciliationReport:
    """Cuadra ``day`` (UTC) en todos los clientes y avisa a Auphere si falta algo."""
    if redis is None:
        from nexus_api.core.redis_client import get_redis

        redis = get_redis()
    report = ReconciliationReport(day=day)
    sm = get_sessionmaker()
    async with sm() as session:
        # ``tenants`` is the platform table (no tenant_id): listing it needs no
        # scope. Every per-client read below runs under that client's RLS.
        tenant_ids = list((await session.execute(sa.select(Tenant.id))).scalars().all())
    for tenant_id in tenant_ids:
        try:
            await _reconcile_tenant(tenant_id, day, redis, report)
        except Exception as exc:
            # Un cliente que no se pudo cuadrar no tapa a los demás; mañana se
            # ve que le falta la fila.
            log.error("meta_reconciliation.tenant_failed", tenant_id=str(tenant_id), error=str(exc))
    if report.diffs:
        await _alert(report)
    log.info(
        "meta_reconciliation.done",
        day=day.isoformat(),
        channels=report.channels,
        channels_with_diff=report.channels_with_diff,
        missing=report.missing,
    )
    return report


async def _alert(report: ReconciliationReport) -> None:
    """``ops.meta_reconciliation``: el registro con nivel de error, que recoge
    la monitorización, y la fila de cada canal para el admin (T172)."""
    log.error(
        "ops.meta_reconciliation",
        day=report.day.isoformat(),
        missing=report.missing,
        channels_with_diff=report.channels_with_diff,
        channels=report.diffs,
        hint="Revisa la DLQ del stream de entrantes y el consumidor.",
    )


async def run_meta_reconciliation_cron(
    *,
    stop: asyncio.Event,
    tick_seconds: float = DEFAULT_TICK_SECONDS,
    redis: Redis | None = None,
) -> None:
    """Cada ``tick_seconds``, cuadra el día de ayer (UTC) si aún no lo está."""
    log.info("meta_reconciliation_cron.start", tick_seconds=tick_seconds)
    while not stop.is_set():
        try:
            yesterday = datetime.now(UTC).date() - timedelta(days=1)
            await reconcile_day(yesterday, redis=redis)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("meta_reconciliation_cron.tick_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("meta_reconciliation_cron.stopped")


__all__ = [
    "DEFAULT_TICK_SECONDS",
    "TASK_NAME",
    "ReconciliationReport",
    "reconcile_day",
    "run_meta_reconciliation_cron",
]
