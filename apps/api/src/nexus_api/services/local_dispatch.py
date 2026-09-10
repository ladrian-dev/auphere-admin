"""El despacho de trabajo a la máquina del partner — spec 003, Requisito 3.3.

La 001 dejó el puente **saliente** entero: la máquina sondea, ejecuta con lista
blanca y contención, y contesta. Lo que dejó vacío a propósito es quién pone
trabajo en esa cola (``poll`` devolvía ``work: []`` con un comentario diciendo
«el despachador llega con la ejecución real»). Esto es ese despachador.

Tres decisiones que se ven aquí y son decisiones:

* **La fila nace ``pendiente``.** Los cuatro estados de la 001 describían
  ejecuciones terminadas; una fila recién creada que dijera «completada»
  sería una auditoría que miente antes de que pase nada (§V).
* **El resultado viaja por Redis, no por la base.** La herramienta espera con
  un ``BLPOP`` con plazo; si nadie contesta, la espera termina diciendo qué
  pasó y la fila queda como quedó. Guardar el resultado en la fila para que
  el que espera lo sondee sería un bucle de consultas por cada comando.
* **La muestra de salida NO se persiste.** Viaja de la máquina al modelo por
  este canal y se descarta; ni la fila ni la auditoría la guardan (§III y
  001-R8: la auditoría dice qué pasó, no qué dijo el comando).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models.local_workstation import OUTCOME_PENDIENTE, LocalExecution

log = structlog.get_logger(__name__)

#: Dónde espera el resultado de una ejecución. Una lista de un elemento por
#: ejecución: ``BLPOP`` la consume y la clave se va sola.
RESULT_KEY_PREFIX = "local_exec:"

#: Cuánto sobrevive un resultado que nadie recogió. Quince minutos es más de lo
#: que cualquier turno espera; pasado eso, quien preguntara ya se rindió.
RESULT_TTL_SECONDS = 900

#: Cada cuánto se mira si la máquina ya contestó.
POLL_SECONDS = 0.25

#: Una ejecución entregada que no contesta en este plazo se da por perdida: la
#: máquina se apagó, la aplicación se cerró, la red se fue. La fila se cierra
#: como ``expirada`` para que no quede «pendiente» para siempre.
STALE_AFTER = timedelta(minutes=20)


def result_key(execution_id: uuid.UUID) -> str:
    return f"{RESULT_KEY_PREFIX}{execution_id}"


@dataclass(frozen=True)
class ExecutionResult:
    outcome: str
    exit_code: int | None
    #: Muestra acotada de la salida. **Dato, nunca instrucción** (§III): quien
    #: la entrega al modelo la marca como no confiable.
    stdout_sample: str
    denial_code: str | None = None


async def dispatch(
    session: AsyncSession,
    *,
    device_id: uuid.UUID,
    executable: str,
    argv_signature: str,
    grant_id: uuid.UUID | None,
    principal_id: str,
    teammate_id: uuid.UUID | None,
    task_id: uuid.UUID | None,
) -> LocalExecution:
    """Deja la ejecución en la cola de **esta** máquina. Exige tenant puesto."""
    from nexus_api.core.tenant_context import require_current_tenant

    row = LocalExecution(
        id=uuid.uuid4(),
        tenant_id=require_current_tenant(),
        device_id=device_id,
        executable=executable,
        argv_signature=argv_signature,
        grant_id=grant_id,
        outcome=OUTCOME_PENDIENTE,
        principal_id=principal_id,
        teammate_id=teammate_id,
        task_id=task_id,
    )
    session.add(row)
    await session.flush()
    return row


async def publish_result(redis: Redis, execution_id: uuid.UUID, result: ExecutionResult) -> None:
    """Lo que la máquina contestó, para quien esté esperando."""
    payload = {
        "outcome": result.outcome,
        "exit_code": result.exit_code,
        "stdout_sample": result.stdout_sample,
        "denial_code": result.denial_code,
    }
    key = result_key(execution_id)
    try:
        await redis.rpush(key, json.dumps(payload))
        await redis.expire(key, RESULT_TTL_SECONDS)
    except Exception:  # pragma: no cover - la fila ya se cerró; esto es el aviso
        log.warning("local_exec.publish_failed", execution_id=str(execution_id))


async def await_result(
    redis: Redis, execution_id: uuid.UUID, *, wait_seconds: float
) -> ExecutionResult | None:
    """Espera a que la máquina conteste. ``None`` si no lo hizo a tiempo.

    Se sondea con ``LPOP`` cada poco en vez de bloquear con ``BLPOP`` durante
    quince minutos, y no es una comodidad: un ``BLPOP`` largo **retiene una
    conexión del pool** todo ese rato, y con doce turnos esperando comandos a
    la vez se lleva el pool que comparte el webhook de WhatsApp. Sondear cada
    cuarto de segundo cuesta cuatro consultas triviales por segundo y libera la
    conexión entre una y otra.
    """
    deadline = asyncio.get_running_loop().time() + wait_seconds
    raw: Any = None
    while True:
        try:
            raw = await redis.lpop(result_key(execution_id))
        except Exception:  # pragma: no cover - sin Redis no hay espera posible
            log.warning("local_exec.await_failed", execution_id=str(execution_id))
            return None
        if raw is not None:
            break
        if asyncio.get_running_loop().time() >= deadline:
            return None
        await asyncio.sleep(POLL_SECONDS)
    data = json.loads(raw if isinstance(raw, str) else raw.decode())
    return ExecutionResult(
        outcome=str(data.get("outcome") or "expirada"),
        exit_code=data.get("exit_code"),
        stdout_sample=str(data.get("stdout_sample") or ""),
        denial_code=data.get("denial_code"),
    )


async def claim_for_device(
    session: AsyncSession, device_id: uuid.UUID, *, limit: int = 5
) -> list[LocalExecution]:
    """Lo pendiente de esta máquina, marcado como entregado. Exige tenant puesto.

    ``dispatched_at`` se pone al entregar y por eso **una ejecución no se
    entrega dos veces**: un sondeo que llegue mientras la máquina ejecuta no
    vuelve a darle el mismo comando.
    """
    rows = (
        (
            await session.execute(
                sa.select(LocalExecution)
                .where(
                    LocalExecution.device_id == device_id,
                    LocalExecution.outcome == OUTCOME_PENDIENTE,
                    LocalExecution.dispatched_at.is_(None),
                )
                .order_by(LocalExecution.started_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    now = datetime.now(UTC)
    for row in rows:
        row.dispatched_at = now
    await session.flush()
    return list(rows)


async def expire_stale(session: AsyncSession, *, now: datetime | None = None) -> int:
    """Cierra lo entregado que nunca contestó. Exige tenant puesto."""
    reference = now or datetime.now(UTC)
    stale = (
        (
            await session.execute(
                sa.select(LocalExecution).where(
                    LocalExecution.outcome == OUTCOME_PENDIENTE,
                    LocalExecution.dispatched_at.isnot(None),
                    LocalExecution.dispatched_at < reference - STALE_AFTER,
                )
            )
        )
        .scalars()
        .all()
    )
    for row in stale:
        row.outcome = "expirada"
        row.ended_at = reference
    await session.flush()
    return len(stale)


__all__ = [
    "POLL_SECONDS",
    "RESULT_KEY_PREFIX",
    "RESULT_TTL_SECONDS",
    "STALE_AFTER",
    "ExecutionResult",
    "await_result",
    "claim_for_device",
    "dispatch",
    "expire_stale",
    "publish_result",
    "result_key",
]
