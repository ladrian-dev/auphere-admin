"""Grader diferido — la otra mitad de WP-21.

El pipeline saca del camino crítico los turnos de bajo riesgo y publica
aquí un trabajo. Este consumidor los gradúa después y escribe el
veredicto sobre la fila del mensaje que ya se envió.

La diferencia con el grader síncrono es una sola y es deliberada: **este
no reescribe la respuesta**. El mensaje ya salió; cambiarlo ahora sería
mentir sobre lo que el cliente leyó. El veredicto se guarda para los
evals continuos y para la mejora de prompt, que es el uso que justifica
seguir graduándolo.

Prioridad baja de verdad: si el consumidor se retrasa o se cae, no pasa
nada para el cliente final — el turno ya se respondió. Por eso el bucle
espera cuando no hay trabajo y no compite por réplicas con el runner.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from typing import Any

import sqlalchemy as sa
import structlog
from nexus_api.core.streams import xadd_capped
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from redis.asyncio import Redis
from redis.exceptions import ResponseError

from nexus_worker.guardrails import load_rubric_text, rubric_for_intent

log = structlog.get_logger(__name__)

GRADE_STREAM = "nexus:grade"
GROUP = "nexus-grade"
# El veredicto diferido es material de análisis, no de operación: si se
# acumulan más de esto es que el consumidor lleva caído mucho tiempo y
# perder lo más viejo es preferible a llenar Redis.
MAX_STREAM_LEN = 50_000
READ_BATCH = 50


async def publish_grade_job(
    *,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    intent: str,
    user_message: str,
    response: str,
    tool_calls: list[dict[str, Any]] | None = None,
) -> None:
    """Encola un turno para graduar después. Nunca lanza.

    Perder un veredicto diferido cuesta una muestra de calidad; romper el
    turno por no poder encolarlo cuesta una conversación.
    """
    try:
        # Import diferido a propósito: ligar ``get_redis`` al cargar el
        # módulo se queda con la función original y esquiva cualquier
        # sustitución del cliente (fixtures, un doble en un runbook).
        from nexus_api.core.redis_client import get_redis

        await xadd_capped(
            get_redis(),
            GRADE_STREAM,
            {
                "tenant_id": str(tenant_id),
                "conversation_id": str(conversation_id),
                "message_id": str(message_id),
                "intent": intent,
                "user_message": user_message[:4000],
                "response": response[:4000],
                # El grader juzga la respuesta CONTRA lo que las
                # herramientas devolvieron; sin esto no puede
                # distinguir un dato inventado de uno consultado.
                "tool_calls": json.dumps(tool_calls or [])[:8000],
            },
            maxlen=MAX_STREAM_LEN,
        )
    except Exception as exc:
        log.warning("grade.publish_failed", tenant_id=str(tenant_id), error=str(exc))


async def ensure_group(redis: Redis) -> None:
    try:
        await redis.xgroup_create(GRADE_STREAM, GROUP, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def _decode(raw: dict[Any, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in raw.items():
        ks = k.decode() if isinstance(k, bytes) else str(k)
        out[ks] = v.decode() if isinstance(v, bytes) else str(v)
    return out


_VERDICT_SQL = sa.text(
    """
    UPDATE messages
       SET outcome_overall = :overall,
           outcome_retries = 0,
           outcome_feedback = :feedback
     WHERE id = :mid
       AND outcome_overall = 'deferred'
    """
)


async def _record_verdict(
    tenant_id: uuid.UUID, message_id: uuid.UUID, *, overall: str, feedback: str
) -> None:
    """Escribe el veredicto sobre la fila del mensaje.

    ``AND outcome_overall = 'deferred'`` no es defensivo por costumbre: si
    el mensaje ya se regraduó por otra vía (o el trabajo se reprocesa),
    esta condición hace la operación idempotente sin necesitar una tabla
    de control.
    """
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        await session.execute(
            _VERDICT_SQL,
            {"mid": str(message_id), "overall": overall, "feedback": feedback[:2000]},
        )
        await session.commit()


async def drain_once(
    redis: Redis, *, grader: Any, consumer_name: str, count: int = READ_BATCH
) -> int:
    """Una pasada: lee, gradúa, escribe el veredicto y acusa."""
    await ensure_group(redis)

    response: Any = await redis.xreadgroup(
        GROUP, consumer_name, {GRADE_STREAM: ">"}, count=count, block=None
    )
    entries: list[tuple[str, dict[str, str]]] = []
    for _stream, raw_entries in response or []:
        for raw_id, raw_fields in raw_entries:
            entry_id = raw_id.decode() if isinstance(raw_id, bytes) else str(raw_id)
            entries.append((entry_id, _decode(raw_fields)))
    if not entries:
        return 0

    for entry_id, fields in entries:
        try:
            tenant_id = uuid.UUID(fields["tenant_id"])
            message_id = uuid.UUID(fields["message_id"])
        except Exception as exc:
            # Un payload inservible no se reintenta nunca con éxito. Se
            # acusa y se sigue: bloquear el PEL por una muestra de
            # calidad sería desproporcionado.
            log.warning("grade.unparseable_entry", entry_id=entry_id, error=str(exc))
            await redis.xack(GRADE_STREAM, GROUP, entry_id)
            continue

        intent = fields.get("intent") or "fallback"
        try:
            rubric_body = load_rubric_text(rubric_for_intent(intent))
            if rubric_body is None:
                # El operador activó el grader pero no hay rúbrica en
                # disco. Marcarlo ``skipped`` y no ``error`` distingue
                # "no se pudo graduar" de "salió mal", que es lo que
                # mirará quien audite la calidad del agente.
                overall, feedback = "skipped", "sin rúbrica para el intent"
            else:
                verdict = await grader.grade(
                    tenant_id=tenant_id,
                    intent=intent,
                    rubric_body=rubric_body,
                    draft_response=fields.get("response") or "",
                    tool_envelopes=json.loads(fields.get("tool_calls") or "[]"),
                )
                overall = str(verdict.overall)
                feedback = str(verdict.feedback or "")
        except Exception as exc:
            # El grader falló (proveedor caído, rúbrica ausente). Se marca
            # ``error`` y se acusa: reintentar indefinidamente una muestra
            # de calidad gastaría LLM sin que nadie lo esté esperando.
            log.warning("grade.deferred_failed", tenant_id=str(tenant_id), error=str(exc))
            overall, feedback = "error", str(exc)[:500]

        with contextlib.suppress(Exception):
            await _record_verdict(tenant_id, message_id, overall=overall, feedback=feedback)
        await redis.xack(GRADE_STREAM, GROUP, entry_id)

    log.info("grade.deferred_batch", entries=len(entries))
    return len(entries)


async def run_grade_consumer(
    redis: Redis,
    *,
    grader: Any,
    stop: asyncio.Event,
    consumer_name: str,
    idle_seconds: float = 10.0,
) -> None:
    """Bucle del servicio. Sale cuando ``stop`` se activa."""
    if grader is None:
        # Sin grader construido (dev sin claves) no hay nada que hacer, y
        # dejar el bucle girando en vacío solo ensucia los logs.
        log.info("grade.consumer.disabled_no_grader")
        return
    await ensure_group(redis)
    log.info("grade.consumer.start", stream=GRADE_STREAM, group=GROUP)
    while not stop.is_set():
        try:
            processed = await drain_once(redis, grader=grader, consumer_name=consumer_name)
            if processed == 0:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=idle_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("grade.consumer.tick_failed", error=str(exc))
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=1.0)
    log.info("grade.consumer.stopped")


__all__ = [
    "GRADE_STREAM",
    "GROUP",
    "drain_once",
    "publish_grade_job",
    "run_grade_consumer",
]
