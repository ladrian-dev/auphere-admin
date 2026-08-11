"""Consumidor de consumo — ingesta (WP-18, plataforma v2 Fase 2).

Lee ``nexus:usage`` en grupo y convierte cada lote de turno en filas de
``usage_records``. Es la otra mitad de B3: el colector (WP-17) cuenta, esto
persiste.

Decisiones:

- **Idempotencia real, no "casi"**: `ON CONFLICT (idempotency_key,
  occurred_at) DO NOTHING`. Reprocesar el stream entero — tras un
  incidente, un despliegue con la BD caída, o un operador reproduciendo
  del DLQ — no crea ni una fila más. El ``occurred_at`` viaja en el
  payload precisamente para que el reintento conserve la misma clave.
- **Inserción agrupada POR TENANT**: `usage_records` tiene RLS forzada, así
  que cada lote entra dentro de su ``tenant_scoped_session``. Un insert
  masivo mezclando tenants ni siquiera sería posible, y eso es
  deliberado — es una tabla de facturación.
- **Sin precio**: se rellena ``quantity`` y ``billable_qty``; ``cost_usd``
  queda NULL hasta que exista ``model_profiles`` (WP-19). Ver 0071.
- **DLQ como WP-04**: una entrada envenenada (JSON roto, tenant ilegible)
  se mueve a ``nexus:usage:dlq`` con el payload íntegro y se acusa, en vez
  de bloquear el PEL para siempre. Un fallo TRANSITORIO (base caída) no
  acusa: la entrada se reintenta.

Lo que este servicio NO hace: reintentar precios, agregar por día ni
facturar. Solo mete hechos.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
import structlog
from nexus_api.core.streams import xadd_capped
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from redis.asyncio import Redis
from redis.exceptions import ResponseError

from nexus_worker.metering.collector import USAGE_STREAM

log = structlog.get_logger(__name__)

GROUP = "nexus-metering"
DLQ_STREAM = "nexus:usage:dlq"

# Entradas de stream leídas por vuelta. Cada entrada es un turno, así que
# esto es "turnos por lectura", no filas.
READ_BATCH = 200
# Filas por INSERT. El criterio de aceptación del plan mueve 10.000 de
# golpe y a este tamaño son 20 sentencias, no 10.000.
INSERT_CHUNK = 500
# Entregas antes de dar una entrada por envenenada (mismo criterio WP-04).
MAX_DELIVERY_ATTEMPTS = 5


async def ensure_group(redis: Redis) -> None:
    try:
        await redis.xgroup_create(USAGE_STREAM, GROUP, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def _decode(raw: dict[Any, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in raw.items():
        ks = k.decode() if isinstance(k, bytes) else str(k)
        vs = v.decode() if isinstance(v, bytes) else str(v)
        out[ks] = vs
    return out


def rows_from_entry(fields: dict[str, str]) -> tuple[uuid.UUID, list[dict[str, Any]]]:
    """Una entrada de stream → (tenant, filas listas para insertar).

    Lanza si la entrada es inservible; el llamante la manda al DLQ.
    """
    tenant_id = uuid.UUID(fields["tenant_id"])
    conversation_id = fields.get("conversation_id")
    agent_config_id = fields.get("agent_config_id")
    events = json.loads(fields["events"])
    if not isinstance(events, list):
        raise ValueError("'events' no es una lista")

    rows: list[dict[str, Any]] = []
    for event in events:
        rows.append(
            {
                "tenant_id": tenant_id,
                # El stream solo transporta texto; ``occurred_at`` tiene que
                # volver a ser datetime o asyncpg rechaza el bind. Además
                # es la clave de partición y la mitad de la clave de
                # idempotencia, así que se conserva EXACTO, sin redondeos.
                "occurred_at": datetime.fromisoformat(event["occurred_at"]),
                "meter": event["meter"],
                "quantity": event["quantity"],
                # Sin política de precios todavía, lo facturable es lo
                # medido. El precio (cost_usd) llega con WP-19.
                "billable_qty": event["quantity"],
                "provider": event.get("provider"),
                "model": event.get("model"),
                "conversation_id": uuid.UUID(conversation_id) if conversation_id else None,
                "agent_config_id": uuid.UUID(agent_config_id) if agent_config_id else None,
                "idempotency_key": event["idempotency_key"],
            }
        )
    return tenant_id, rows


_INSERT_SQL = sa.text(
    """
    INSERT INTO usage_records (
        tenant_id, occurred_at, meter, quantity, billable_qty,
        provider, model, conversation_id, agent_config_id, idempotency_key
    ) VALUES (
        :tenant_id, :occurred_at, :meter, :quantity, :billable_qty,
        :provider, :model, :conversation_id, :agent_config_id, :idempotency_key
    )
    ON CONFLICT (idempotency_key, occurred_at) DO NOTHING
    """
)


async def persist_rows(rows_by_tenant: dict[uuid.UUID, list[dict[str, Any]]]) -> int:
    """Inserta agrupando por tenant. Devuelve filas ENVIADAS (no insertadas:
    las que chocan con la clave de idempotencia se descartan en la base)."""
    sm = get_sessionmaker()
    sent = 0
    for tenant_id, rows in rows_by_tenant.items():
        if not rows:
            continue
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            for start in range(0, len(rows), INSERT_CHUNK):
                chunk = rows[start : start + INSERT_CHUNK]
                await session.execute(_INSERT_SQL, chunk)
                sent += len(chunk)
    return sent


async def _dead_letter(
    redis: Redis, *, entry_id: str, fields: dict[str, str], error: str, attempts: int
) -> None:
    await xadd_capped(
        redis,
        DLQ_STREAM,
        {
            **fields,
            "dlq_source_stream": USAGE_STREAM,
            "dlq_source_entry_id": entry_id,
            "dlq_error": error[:500],
            "dlq_attempts": str(attempts),
        },
    )
    await redis.xack(USAGE_STREAM, GROUP, entry_id)
    log.error("metering.dead_lettered", entry_id=entry_id, attempts=attempts, error=error[:200])


async def _delivery_count(redis: Redis, entry_id: str) -> int:
    try:
        pending = await redis.xpending_range(
            USAGE_STREAM, GROUP, min=entry_id, max=entry_id, count=1
        )
    except Exception:
        return 1
    if not pending:
        return 1
    info = pending[0]
    count = info.get("times_delivered") if isinstance(info, dict) else None
    return int(count) if count else 1


def _entries_from_response(response: Any) -> list[tuple[str, dict[str, str]]]:
    out: list[tuple[str, dict[str, str]]] = []
    for _stream, raw_entries in response or []:
        for raw_id, raw_fields in raw_entries:
            entry_id = raw_id.decode() if isinstance(raw_id, bytes) else str(raw_id)
            out.append((entry_id, _decode(raw_fields)))
    return out


async def _read_own_pending(
    redis: Redis, consumer_name: str, count: int
) -> list[tuple[str, dict[str, str]]]:
    """Lo que esta réplica leyó y no llegó a acusar."""
    response: Any = await redis.xreadgroup(
        GROUP, consumer_name, {USAGE_STREAM: "0"}, count=count, block=None
    )
    entries = _entries_from_response(response)
    if entries:
        log.info("metering.recovered_pending", entries=len(entries))
    return entries


async def _claim_orphans(
    redis: Redis, consumer_name: str, count: int
) -> list[tuple[str, dict[str, str]]]:
    """Trabajo de una réplica que murió con entradas en la mano.

    Sin esto, matar una réplica de metering pierde su consumo en curso: en
    una tabla de facturación eso es dinero. ``min_idle_time`` alto para no
    robarle trabajo a una réplica viva que simplemente va lenta.
    """
    try:
        result: Any = await redis.xautoclaim(
            USAGE_STREAM, GROUP, consumer_name, min_idle_time=120_000, count=count
        )
    except Exception as exc:  # pragma: no cover - depende del servidor
        log.warning("metering.xautoclaim_failed", error=str(exc))
        return []
    # (next_cursor, entries[, deleted]) según versión del servidor.
    raw_entries = result[1] if isinstance(result, (list, tuple)) and len(result) > 1 else []
    entries: list[tuple[str, dict[str, str]]] = []
    for raw_id, raw_fields in raw_entries or []:
        entry_id = raw_id.decode() if isinstance(raw_id, bytes) else str(raw_id)
        entries.append((entry_id, _decode(raw_fields)))
    if entries:
        log.info("metering.claimed_orphans", entries=len(entries))
    return entries


async def _read_new(
    redis: Redis, consumer_name: str, count: int
) -> list[tuple[str, dict[str, str]]]:
    # El stub de redis-py tipa la respuesta como Any|int|str porque XREADGROUP
    # varía de forma según opciones; aquí siempre es [(stream, [(id, fields)])].
    response: Any = await redis.xreadgroup(
        GROUP, consumer_name, {USAGE_STREAM: ">"}, count=count, block=None
    )
    return _entries_from_response(response)


async def drain_once(redis: Redis, *, consumer_name: str, count: int = READ_BATCH) -> int:
    """Una pasada completa: recupera, reclama, lee lo nuevo, persiste y acusa.

    Tres fuentes, en este orden y no en otro:

    1. **Lo propio pendiente** (``id="0"``): entradas que esta réplica ya
       leyó pero cuya persistencia falló. Leer solo ``">"`` las dejaría en
       el PEL para siempre — "no acusar para que se reintente" solo es
       cierto si algo vuelve a leerlas. Visto en staging el 2026-08-11: la
       migración 0071 no estaba aplicada, el INSERT rebotaba y el consumo
       se quedaba atascado sin recuperación.
    2. **Lo huérfano** (``XAUTOCLAIM``): entradas de una réplica que murió
       con trabajo en la mano. En una tabla de facturación, perderlas es
       perder dinero.
    3. **Lo nuevo** (``">"``).

    Separada del bucle para que los tests (y el criterio de aceptación del
    plan) puedan ejercer exactamente una vuelta.
    """
    await ensure_group(redis)

    entries: list[tuple[str, dict[str, str]]] = []
    entries += await _read_own_pending(redis, consumer_name, count)
    entries += await _claim_orphans(redis, consumer_name, count)
    entries += await _read_new(redis, consumer_name, count)
    if not entries:
        return 0

    parsed: dict[uuid.UUID, list[dict[str, Any]]] = {}
    ok_ids: list[str] = []
    for entry_id, fields in entries:
        try:
            tenant_id, rows = rows_from_entry(fields)
        except Exception as exc:
            # Payload inservible: reprocesarlo nunca va a funcionar.
            attempts = await _delivery_count(redis, entry_id)
            await _dead_letter(
                redis, entry_id=entry_id, fields=fields, error=str(exc), attempts=attempts
            )
            continue
        parsed.setdefault(tenant_id, []).extend(rows)
        ok_ids.append(entry_id)

    if not ok_ids:
        return 0

    # Persistir ANTES de acusar: si la base falla, las entradas siguen en
    # el PEL y se reintentan. Acusar primero perdería facturación.
    try:
        sent = await persist_rows(parsed)
    except Exception as exc:
        log.error("metering.persist_failed", entries=len(ok_ids), error=str(exc))
        for entry_id in ok_ids:
            attempts = await _delivery_count(redis, entry_id)
            if attempts >= MAX_DELIVERY_ATTEMPTS:
                await _dead_letter(
                    redis,
                    entry_id=entry_id,
                    fields={"tenant_id": "?"},
                    error=f"persist failed {attempts}x: {exc}",
                    attempts=attempts,
                )
        return 0

    await redis.xack(USAGE_STREAM, GROUP, *ok_ids)
    log.info("metering.ingested", entries=len(ok_ids), rows=sent, tenants=len(parsed))
    return len(ok_ids)


async def run_metering_consumer(
    redis: Redis,
    *,
    stop: asyncio.Event,
    consumer_name: str,
    block_ms: int = 5_000,
) -> None:
    """Bucle del servicio. Sale cuando ``stop`` se activa."""
    await ensure_group(redis)
    log.info("metering.consumer.start", stream=USAGE_STREAM, group=GROUP)
    while not stop.is_set():
        try:
            processed = await drain_once(redis, consumer_name=consumer_name)
            if processed == 0:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=block_ms / 1000)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("metering.consumer.tick_failed", error=str(exc))
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=1.0)
    log.info("metering.consumer.stopped")
