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
- **El precio se pone aquí** (WP-19): ``cost_usd`` sale de valorar la
  cantidad contra ``model_profiles``. Lo que no se puede valorar —modelo
  fuera de catálogo, medidor sin tarifa— entra con NULL y no con 0: un
  cero se suma en cualquier panel de margen como si el evento fuese
  gratis. Ver ``metering/pricing.py`` y la migración 0071.
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
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
import structlog
from nexus_api.core.streams import xadd_capped
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.metering.quota import billable_qty_for_meter, quota_tokens
from redis.asyncio import Redis
from redis.exceptions import ResponseError

from nexus_worker.metering.budget import add_spend
from nexus_worker.metering.collector import SOURCE_CHANNEL, USAGE_SOURCES, USAGE_STREAM
from nexus_worker.metering.pricing import get_catalog, get_unit_prices, price_row

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
    # Las entradas publicadas antes de la 0079 no llevan ``source``; son,
    # todas, tráfico de canal. Un valor DESCONOCIDO sí es un error: lo
    # rechazaría el CHECK de la tabla y tumbaría el INSERT del lote entero,
    # así que la entrada se va al DLQ ella sola y el resto del lote entra.
    source = fields.get("source") or SOURCE_CHANNEL
    if source not in USAGE_SOURCES:
        raise ValueError(f"'source' desconocido: {source!r}")
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
                # Placeholder: C3 aplica la cuota por llamada mas abajo,
                # cuando ya estan juntos los nativos del mismo call_seq.
                "billable_qty": event["quantity"],
                "cost_usd": None,
                "provider": event.get("provider"),
                "model": event.get("model"),
                "conversation_id": uuid.UUID(conversation_id) if conversation_id else None,
                "agent_config_id": uuid.UUID(agent_config_id) if agent_config_id else None,
                "idempotency_key": event["idempotency_key"],
                "source": source,
            }
        )
    _apply_quota_billable(rows)
    return tenant_id, rows


def _llm_call_key(row: dict[str, Any]) -> str:
    """Agrupa las filas nativas de UNA llamada: ``{turn}:{seq}:{meter}``."""
    key = str(row.get("idempotency_key") or "")
    meter = str(row.get("meter") or "")
    suffix = f":{meter}"
    if meter and key.endswith(suffix):
        return key[: -len(suffix)]
    return key


def _apply_quota_billable(rows: list[dict[str, Any]]) -> None:
    """billable_qty = politica C3; quantity sigue siendo el nativo.

    El colector emite una fila por campo (input bruto, output, cache_read,
    cache_write). Si billable_qty copiara quantity en input, un libro que
    sume input + cache_read doble-cuenta. La cuota de input es el uncached;
    la de cache_read es 0.1x; cache_write no come tope. cost_usd sigue
    saliendo de quantity x tarifa (ADR-007).
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        meter = str(row.get("meter") or "")
        if meter.startswith("llm."):
            groups.setdefault(_llm_call_key(row), []).append(row)
    for group in groups.values():
        cache_read = 0
        prompt = 0
        for row in group:
            if row["meter"] == "llm.cache_read":
                cache_read = int(row["quantity"] or 0)
            elif row["meter"] == "llm.input_tokens":
                prompt = int(row["quantity"] or 0)
        for row in group:
            row["billable_qty"] = billable_qty_for_meter(
                str(row["meter"]),
                row["quantity"],
                prompt_tokens=prompt,
                cache_read=cache_read,
            )


_INSERT_SQL = sa.text(
    """
    INSERT INTO usage_records (
        tenant_id, occurred_at, meter, quantity, billable_qty, cost_usd,
        provider, model, conversation_id, agent_config_id, idempotency_key,
        source
    ) VALUES (
        :tenant_id, :occurred_at, :meter, :quantity, :billable_qty, :cost_usd,
        :provider, :model, :conversation_id, :agent_config_id, :idempotency_key,
        :source
    )
    ON CONFLICT (idempotency_key, occurred_at) DO NOTHING
    """
)


def _turn_quota(rows: list[dict[str, Any]]) -> dict[str, int]:
    """turn_id -> quota_tokens() C3, agrupando por llamada."""
    calls: dict[str, dict[str, int]] = {}
    for row in rows:
        meter = str(row.get("meter") or "")
        if not meter.startswith("llm."):
            continue
        call = _llm_call_key(row)
        g = calls.setdefault(call, {"prompt": 0, "cache": 0, "output": 0})
        qty = int(row.get("quantity") or 0)
        if meter == "llm.input_tokens":
            g["prompt"] = qty
        elif meter == "llm.cache_read":
            g["cache"] = qty
        elif meter == "llm.output_tokens":
            g["output"] = qty
    turns: dict[str, int] = {}
    for call, g in calls.items():
        turn = call.rsplit(":", 1)[0] if ":" in call else call
        turns[turn] = turns.get(turn, 0) + quota_tokens(
            prompt_tokens=g["prompt"], cache_read=g["cache"], output_tokens=g["output"]
        )
    return turns


async def _debit_channel_wallet(tenant_id: uuid.UUID, rows: list[dict[str, Any]]) -> None:
    source = str((rows[0] or {}).get("source") or SOURCE_CHANNEL) if rows else SOURCE_CHANNEL
    if source != SOURCE_CHANNEL:
        return
    partner_id = await _partner_for(tenant_id)
    if partner_id is None:
        return
    from nexus_api.metering.wallet import debit_wallet

    for turn, qty in _turn_quota(rows).items():
        if qty <= 0:
            continue
        try:
            await debit_wallet(
                partner_id=partner_id,
                tenant_id=tenant_id,
                qty=qty,
                idempotency_key=f"channel:{turn}",
            )
        except Exception as exc:
            log.warning(
                "metering.wallet_debit_failed",
                tenant_id=str(tenant_id),
                turn=turn,
                error=str(exc),
            )


async def persist_rows(rows_by_tenant: dict[uuid.UUID, list[dict[str, Any]]]) -> int:
    """Inserta agrupando por tenant. Devuelve filas ENVIADAS (no insertadas:
    las que chocan con la clave de idempotencia se descartan en la base).

    Valora justo antes de insertar (WP-19). El catálogo se lee una vez por
    pasada, no por fila: son decenas de filas que cambian casi nunca.
    Que la valoración falle no puede impedir la ingesta — la cantidad
    medida es el dato irrecuperable, el precio siempre se puede volver a
    calcular sobre las filas con ``cost_usd IS NULL``.
    """
    sm = get_sessionmaker()
    sent = 0
    try:
        catalog = await get_catalog()
        unit_prices = await get_unit_prices()
    except Exception as exc:  # pragma: no cover - get_catalog ya traga lo suyo
        log.warning("metering.pricing_unavailable", error=str(exc))
        catalog, unit_prices = {}, {}

    for tenant_id, rows in rows_by_tenant.items():
        if not rows:
            continue
        if catalog or unit_prices:
            for row in rows:
                row["cost_usd"] = price_row(row, catalog, unit_prices)
            # WP-20 — el contador de presupuesto se alimenta AQUÍ, con el
            # precio ya calculado. Va unos segundos por detrás del gasto
            # real (el metering es asíncrono) y es un compromiso asumido:
            # consultarlo en el camino crítico tiene que costar una
            # lectura de Redis, no un agregado sobre ``usage_records``.
            await _bump_budget(tenant_id, rows)
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            for start in range(0, len(rows), INSERT_CHUNK):
                chunk = rows[start : start + INSERT_CHUNK]
                await session.execute(_INSERT_SQL, chunk)
                sent += len(chunk)
        await _debit_channel_wallet(tenant_id, rows)
    return sent


_PARTNER_SQL = sa.text("SELECT partner_id FROM partner_tenants WHERE tenant_id = :t LIMIT 1")
# El mapa tenant → partner cambia con altas y bajas, no con turnos.
_partner_of: dict[uuid.UUID, uuid.UUID | None] = {}


async def _partner_for(tenant_id: uuid.UUID) -> uuid.UUID | None:
    if tenant_id in _partner_of:
        return _partner_of[tenant_id]
    try:
        sm = get_sessionmaker()
        async with sm() as session:
            found = await session.scalar(_PARTNER_SQL, {"t": str(tenant_id)})
    except Exception as exc:
        # Sin resolver el partner solo se pierde el contador agregado del
        # partner; el del tenant sigue subiendo. No se cachea el fallo.
        log.warning("metering.partner_lookup_failed", tenant_id=str(tenant_id), error=str(exc))
        return None
    resolved = uuid.UUID(str(found)) if found else None
    _partner_of[tenant_id] = resolved
    return resolved


async def _bump_budget(tenant_id: uuid.UUID, rows: list[dict[str, Any]]) -> None:
    """Suma el coste de este lote a los contadores de tenant y partner.

    **Solo cuenta el tráfico de canal.** El contador de WP-20 existe para
    degradar o cortar el servicio cuando un tenant se pasa de gasto; si las
    pruebas del operador lo alimentasen, revisar un agente a fondo apagaría
    el grader del cliente en producción — un daño causado por quien estaba
    intentando mejorarle el servicio. Lo mismo, y con más motivo, para el
    Companion (CO-01): ese gasto es de una persona del partner operando la
    consola, no del cliente final, y hacerlo pesar sobre el presupuesto del
    cliente sería cobrarle por una conversación en la que no estuvo.

    Ambos quedan medidos en ``usage_records`` con su ``source``, que es
    donde se ven; lo que no hacen es disparar una política pensada para
    otra cosa. El filtro es por lista blanca — un ``source`` nuevo no entra
    en el presupuesto de nadie por omisión.
    """
    total = sum(
        (
            r["cost_usd"]
            for r in rows
            if r.get("cost_usd") is not None and r.get("source") == SOURCE_CHANNEL
        ),
        Decimal(0),
    )
    if total <= 0:
        return
    try:
        from nexus_api.core.redis_client import get_redis

        redis = get_redis()
        await add_spend(redis, scope="tenant", scope_id=tenant_id, amount=total)
        partner_id = await _partner_for(tenant_id)
        if partner_id is not None:
            await add_spend(redis, scope="partner", scope_id=partner_id, amount=total)
    except Exception as exc:
        log.warning("metering.budget_bump_failed", tenant_id=str(tenant_id), error=str(exc))


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
