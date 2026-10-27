"""``GET /console/jobs/{job_id}`` — el estado de un trabajo largo (spec 047, T003).

Lo que tarda (leer la web, construir, probar, publicar, certificar) responde
``202 {job_id}``, y la consola consulta aquí con espera creciente (1, 2, 4…
hasta 10 s; ``contracts/console-api.md`` §Convenciones).

La ruta recibe solo el id del trabajo, sin ``{ref}``. Para no leer nada sin
cliente puesto:

1. ``job_tenant(job_id)`` (SECURITY DEFINER, migración 0175) devuelve **solo**
   el cliente del trabajo, nunca el trabajo;
2. ese cliente tiene que ser del partner del principal (``partner_tenants``);
3. solo entonces se abre la transacción con ese cliente (RLS) y se lee.

Un trabajo de otro partner y uno que no existe responden el mismo 404, byte a
byte: la respuesta nunca confirma que exista en otra parte. El coste no sale
nunca (C9), y un fallo viaja como ``error_code``: las palabras son de la consola.
"""

from __future__ import annotations

import uuid
from typing import cast

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.core.logging_context import bind_tenant
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import Job, PartnerTenant
from nexus_api.services import jobs as jobs_service

from .schemas import JobKind, JobOut, JobStatus

router = APIRouter()

JobId = Path(..., description="The id a 202 answered with.")


def unknown_job() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown job")


def job_out(job: Job) -> JobOut:
    """The console's view of a job: never its cost, never its client."""
    return JobOut(
        job_id=job.id,
        kind=cast(JobKind, job.kind),
        status=cast(JobStatus, job.status),
        agent_id=job.agent_id,
        progress=job.progress or {},
        questions=job.questions,
        result=job.result,
        error_code=job.error_code,
        created_at=job.created_at,
        finished_at=job.finished_at,
    )


async def _owned_tenant(
    session: AsyncSession, principal: ConsolePrincipal, job_id: uuid.UUID
) -> uuid.UUID | None:
    """The job's client, if it is one of the principal's partner's clients."""
    async with session.begin():
        tenant_id: uuid.UUID | None = await session.scalar(
            sa.text("SELECT job_tenant(:job_id)"), {"job_id": job_id}
        )
        if tenant_id is None:
            return None
        mapped = await session.scalar(
            sa.select(PartnerTenant.tenant_id).where(
                PartnerTenant.partner_id == principal.partner.id,
                PartnerTenant.tenant_id == tenant_id,
            )
        )
    return tenant_id if mapped is not None else None


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(
    job_id: uuid.UUID = JobId,
    principal: ConsolePrincipal = Depends(require_console_principal("clients:read")),
    session: AsyncSession = Depends(get_db_session),
) -> JobOut:
    tenant_id = await _owned_tenant(session, principal, job_id)
    if tenant_id is None:
        raise unknown_job()
    async with tenant_scoped_session(session, tenant_id):
        bind_tenant(tenant_id)
        # Lazy expiry: a job without a heartbeat past its window is written
        # ``failed``/``timeout`` here, in this same transaction.
        job = await jobs_service.get_job(session, job_id)
        if job is None:  # pragma: no cover - job_tenant just found it under RLS-off
            raise unknown_job()
        return job_out(job)


__all__ = ["job_out", "router", "unknown_job"]
