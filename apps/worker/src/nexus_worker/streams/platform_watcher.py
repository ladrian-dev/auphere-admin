"""Platform watcher (WP-06, plataforma v2 Fase 0) — alerts with a recipient.

Evaluates the platform-level alert conditions that no existing cron covers
and delivers each one to a human: email to ``NEXUS_OPERATOR_ALERT_EMAIL``
(plus ERROR log always), and — for the tenant-scoped burst — an audit_log
row that the operator alerter turns into the approved WhatsApp template.

The eight Fase-0 alerts and where they live:

1. queue oldest pending > 300 s               → HERE (``queue_backlog``)
2. entries in ``nexus:inbound:dlq``           → HERE (``dlq_entries``)
3. turn errors per tenant > 5 in 10 min       → HERE (``turn_error_burst``,
   also writes ``platform.turn_error_burst`` audit row → WhatsApp template)
4. new ``isolation_events`` row               → isolation_watcher (existing)
5. worker heartbeat missing > 3 min           → HERE (``worker_dead``)
6. llm cache read ratio < 0.3 sustained       → HERE (``cache_ratio_low``)
7. same Meta failure code > 20 in 10 min      → HERE (``meta_failure_burst``)
8. tenant daily cost > threshold              → cost_rollup_cron (existing)

Counters are fed by the hot paths (consumer, outbound dispatcher, LLM
provider) as windowed Redis keys — the watcher only reads. Every alert is
deduplicated in Redis (``SET NX EX``) so a persisting condition notifies
once per window, not once per tick.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from dataclasses import dataclass

import structlog
from redis.asyncio import Redis

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 60.0

INBOUND_STREAM = "nexus:inbound"
INBOUND_GROUP = "nexus-worker"
DLQ_STREAM = "nexus:inbound:dlq"


def _watched_streams() -> tuple[str, ...]:
    """WP-10: watch every configured inbound stream (tier streams + legacy),
    not just the historical single one."""
    try:
        from nexus_worker.config import get_worker_settings

        return get_worker_settings().inbound_streams_list or (INBOUND_STREAM,)
    except Exception:
        return (INBOUND_STREAM,)


QUEUE_AGE_THRESHOLD_S = 300.0
TURN_ERROR_THRESHOLD = 5
META_FAILURE_THRESHOLD = 20
CACHE_RATIO_THRESHOLD = 0.30
# Below this many input tokens in the hour the ratio is noise, not signal
# (e.g. one uncached call at 03:00 must not page anyone).
CACHE_RATIO_MIN_TOKENS = 100_000
HEARTBEAT_DEAD_AFTER_S = 180.0


def _expected_services() -> tuple[str, ...]:
    """WP-07: same env-driven contract as GET /health/workers
    (``NEXUS_EXPECTED_WORKER_SERVICES``)."""
    from nexus_api.config import get_settings

    return get_settings().expected_worker_services_list


# One notification per condition per this window (seconds).
DEDUP_TTL_S = 3_600


@dataclass
class Alert:
    kind: str
    dedup_key: str
    subject: str
    detail: str
    tenant_id: uuid.UUID | None = None
    count: int = 0


async def evaluate_alerts(redis: Redis, *, now: float | None = None) -> list[Alert]:
    """Pure-read evaluation of conditions 1-3 and 5-7. Never raises."""
    now = time.time() if now is None else now
    alerts: list[Alert] = []
    window = int(now) // 600
    hour_window = int(now) // 3600

    # 1 · queue backlog age — every configured inbound stream (WP-10)
    for watched in _watched_streams():
        with contextlib.suppress(Exception):
            summary = await redis.xpending(watched, INBOUND_GROUP)
            pending = int(summary.get("pending") or 0) if isinstance(summary, dict) else 0
            min_id = summary.get("min") if isinstance(summary, dict) else None
            if pending and min_id:
                min_id_str = min_id.decode() if isinstance(min_id, bytes) else str(min_id)
                entry_ms = int(min_id_str.split("-")[0])
                oldest_s = max(0.0, now - entry_ms / 1000.0)
                if oldest_s > QUEUE_AGE_THRESHOLD_S:
                    alerts.append(
                        Alert(
                            kind="queue_backlog",
                            dedup_key=f"nexus:alert:sent:queue_backlog:{watched}:{hour_window}",
                            subject="[Nexus] Cola inbound atascada",
                            detail=(
                                f"La entrada más vieja de {watched} lleva "
                                f"{oldest_s:.0f}s pendiente ({pending} entradas en el PEL)."
                            ),
                            count=pending,
                        )
                    )

    # 2 · DLQ entries
    with contextlib.suppress(Exception):
        dlq_len = int(await redis.xlen(DLQ_STREAM))
        if dlq_len > 0:
            alerts.append(
                Alert(
                    kind="dlq_entries",
                    dedup_key=f"nexus:alert:sent:dlq:{hour_window}",
                    subject="[Nexus] Mensajes en la DLQ",
                    detail=(
                        f"{dlq_len} entradas en {DLQ_STREAM}. Cada una es un mensaje "
                        "de cliente que agotó sus reintentos — revisar y reinyectar."
                    ),
                    count=dlq_len,
                )
            )

    # 3 · per-tenant turn error burst (current 10-min window)
    with contextlib.suppress(Exception):
        async for key in redis.scan_iter(match=f"nexus:alert:turn_errors:*:{window}", count=100):
            key_str = key.decode() if isinstance(key, bytes) else key
            raw = await redis.get(key_str)
            count = int(raw or 0)
            if count > TURN_ERROR_THRESHOLD:
                tenant_str = key_str.split(":")[3]
                with contextlib.suppress(ValueError):
                    alerts.append(
                        Alert(
                            kind="turn_error_burst",
                            dedup_key=f"nexus:alert:sent:turn_errors:{tenant_str}:{window}",
                            subject="[Nexus] Ráfaga de errores de turno",
                            detail=(
                                f"El tenant {tenant_str} lleva {count} turnos fallidos "
                                "en la ventana de 10 minutos."
                            ),
                            tenant_id=uuid.UUID(tenant_str),
                            count=count,
                        )
                    )

    # 5 · dead workers (heartbeat tracking via last-seen ledger)
    with contextlib.suppress(Exception):
        for service in _expected_services():
            alive = False
            async for _ in redis.scan_iter(match=f"nexus:health:{service}:*", count=10):
                alive = True
                break
            lastseen_key = f"nexus:alert:worker_lastseen:{service}"
            if alive:
                await redis.set(lastseen_key, str(now))
                continue
            raw_seen = await redis.get(lastseen_key)
            if raw_seen is None:
                # Never seen (fresh deploy) — start the clock now.
                await redis.set(lastseen_key, str(now))
                continue
            silent_for = now - float(raw_seen)
            if silent_for > HEARTBEAT_DEAD_AFTER_S:
                alerts.append(
                    Alert(
                        kind="worker_dead",
                        dedup_key=f"nexus:alert:sent:worker_dead:{service}:{hour_window}",
                        subject=f"[Nexus] Servicio sin latido: {service}",
                        detail=(
                            f"{service} no reporta heartbeat desde hace "
                            f"{silent_for:.0f}s (umbral {HEARTBEAT_DEAD_AFTER_S:.0f}s)."
                        ),
                    )
                )

    # 6 · cache read ratio (previous full hour has the complete picture;
    # evaluate the current hour once it has enough volume)
    with contextlib.suppress(Exception):
        input_tok = int(await redis.get(f"nexus:alert:llmtok:input:{hour_window}") or 0)
        cache_tok = int(await redis.get(f"nexus:alert:llmtok:cache_read:{hour_window}") or 0)
        total = input_tok + cache_tok
        if total >= CACHE_RATIO_MIN_TOKENS:
            ratio = cache_tok / total
            if ratio < CACHE_RATIO_THRESHOLD:
                alerts.append(
                    Alert(
                        kind="cache_ratio_low",
                        dedup_key=f"nexus:alert:sent:cache_ratio:{hour_window}",
                        subject="[Nexus] Prompt cache degradado",
                        detail=(
                            f"Cache read ratio {ratio:.2f} (< {CACHE_RATIO_THRESHOLD}) "
                            f"con {total} tokens en la hora. Hay un invalidador "
                            "silencioso en el prefijo del prompt — es la diferencia "
                            "entre $0,013 y $0,03 por turno."
                        ),
                    )
                )

    # 7 · Meta failure code burst
    with contextlib.suppress(Exception):
        async for key in redis.scan_iter(match=f"nexus:alert:metafail:*:{window}", count=100):
            key_str = key.decode() if isinstance(key, bytes) else key
            raw = await redis.get(key_str)
            count = int(raw or 0)
            if count > META_FAILURE_THRESHOLD:
                code = key_str.split(":")[3]
                alerts.append(
                    Alert(
                        kind="meta_failure_burst",
                        dedup_key=f"nexus:alert:sent:metafail:{code}:{window}",
                        subject=f"[Nexus] Fallos de envío Meta (código {code})",
                        detail=(
                            f"{count} envíos fallidos con el código {code} en la "
                            "ventana de 10 minutos."
                        ),
                        count=count,
                    )
                )

    return alerts


async def _write_tenant_audit_row(alert: Alert) -> None:
    """Tenant-scoped alerts also flow through the operator alerter → the
    tenant owner's WhatsApp, via the approved burst template."""
    import sqlalchemy as sa  # noqa: F401 - session helpers below
    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.base import get_sessionmaker
    from nexus_api.db.models import AuditLog

    assert alert.tenant_id is not None
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, alert.tenant_id):
        session.add(
            AuditLog(
                tenant_id=alert.tenant_id,
                actor="system:platform-watcher",
                action="platform.turn_error_burst",
                after_json={"threshold": alert.count},
            )
        )
        await session.commit()


async def _notify(alert: Alert) -> None:
    log.error(
        "platform_alert",
        kind=alert.kind,
        subject=alert.subject,
        detail=alert.detail,
        tenant_id=str(alert.tenant_id) if alert.tenant_id else None,
    )
    if alert.tenant_id is not None:
        with contextlib.suppress(Exception):
            await _write_tenant_audit_row(alert)
    from nexus_api.config import get_settings

    settings = get_settings()
    if settings.operator_alert_email:
        from nexus_api.services.email import send_email

        with contextlib.suppress(Exception):
            await send_email(
                to=settings.operator_alert_email,
                subject=alert.subject,
                html=f"<p>{alert.detail}</p><p>kind: <code>{alert.kind}</code></p>",
            )


async def process_tick(redis: Redis, *, now: float | None = None) -> list[Alert]:
    """One evaluation pass: dedup + notify. Returns the alerts DELIVERED."""
    delivered: list[Alert] = []
    for alert in await evaluate_alerts(redis, now=now):
        try:
            fresh = await redis.set(alert.dedup_key, "1", nx=True, ex=DEDUP_TTL_S)
        except Exception as exc:
            log.warning("platform_watcher.dedup_failed", error=str(exc))
            fresh = True  # better a duplicate page than silence
        if not fresh:
            continue
        await _notify(alert)
        delivered.append(alert)
    return delivered


async def run_platform_watcher(
    redis: Redis,
    *,
    stop: asyncio.Event,
    tick_seconds: float = DEFAULT_TICK_SECONDS,
) -> None:
    log.info("platform_watcher.start", tick_seconds=tick_seconds)
    while not stop.is_set():
        try:
            await process_tick(redis)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("platform_watcher.tick_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("platform_watcher.stopped")
