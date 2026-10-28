"""«Completar con el constructor» — spec 047, T098 (requisito 18; ``console-api.md`` §3).

``POST /clients/{ref}/business/builder`` [``clients:write``] → ``202 {job_id}``.
El trabajo deja sus propuestas como sugerencias de la ficha («Sugerido ·
confirma»), que se aceptan, editan o descartan una a una con
``POST …/business/suggestions/{id}/decide``, y los agentes que propone en su
resultado, sin crearlos.
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, Path, status
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.services import jobs as jobs_service

from .deps import require_build_room, resolve_mapping

log = structlog.get_logger(__name__)

router = APIRouter()


class BuilderJobOut(BaseModel):
    job_id: uuid.UUID


@router.post(
    "/clients/{ref}/business/builder",
    response_model=BuilderJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def complete_with_builder(
    ref: str = Path(...),
    principal: ConsolePrincipal = Depends(require_console_principal("clients:write")),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> BuilderJobOut:
    await require_build_room(principal.partner.id)
    mapping = await resolve_mapping(session, principal, ref)
    async with tenant_scoped_session(session, mapping.tenant_id):
        job = await jobs_service.create_job(
            session, kind="client_builder", created_by=principal.user_id
        )
        out = BuilderJobOut(job_id=job.id)
    try:
        await jobs_service.enqueue_job(redis, job)
    except Exception as exc:  # la fila es la verdad
        log.warning("console.client_builder.enqueue_failed", error=type(exc).__name__)
    return out


__all__ = ["router"]
