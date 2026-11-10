"""La fila del trabajo, vista desde el worker (spec 047, T003).

``JobStore`` es lo único que el consumidor necesita de la base: las mismas
transiciones que ``nexus_api.services.jobs``, cada una en su propia transacción
con el cliente puesto. :class:`DbJobStore` es la de verdad; las pruebas sin
base usan una en memoria con el mismo contrato.

El cliente llega en la entrada del stream y se usa **solo** para abrir la
transacción: con la RLS, un ``tenant_id`` que no es el del trabajo no
encuentra nada, y cada escritura es un ``UPDATE … WHERE status = …`` que se da
una vez o ninguna.

Al empezar, la misma transacción lee el partner del cliente (``partner_tenants``,
o ``tenants.partner_id``): el consumidor lo ata al proxy de modelos.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.metering.wallet import partner_id_for_tenant
from nexus_api.services import jobs as jobs_service
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexus_worker.jobs.registry import StartedJob


class JobStore(Protocol):
    async def start(self, tenant_id: uuid.UUID, job_id: uuid.UUID) -> StartedJob | None: ...

    async def heartbeat(self, tenant_id: uuid.UUID, job_id: uuid.UUID) -> bool: ...

    async def progress(
        self,
        tenant_id: uuid.UUID,
        job_id: uuid.UUID,
        *,
        step: str | None = None,
        block: dict[str, Any] | None = None,
    ) -> bool: ...

    async def finish(
        self, tenant_id: uuid.UUID, job_id: uuid.UUID, *, result: dict[str, Any], cost_micros: int
    ) -> bool: ...

    async def fail(
        self, tenant_id: uuid.UUID, job_id: uuid.UUID, *, error_code: str, cost_micros: int = 0
    ) -> bool: ...

    async def settle(self, tenant_id: uuid.UUID, job_id: uuid.UUID) -> str | None:
        """Lee el trabajo con la caducidad perezosa y devuelve su estado."""
        ...


class DbJobStore:
    """``JobStore`` sobre Postgres: una transacción corta por llamada."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._sessionmaker = sessionmaker

    def _session(self) -> AsyncSession:
        return (self._sessionmaker or get_sessionmaker())()

    async def start(self, tenant_id: uuid.UUID, job_id: uuid.UUID) -> StartedJob | None:
        async with self._session() as session, tenant_scoped_session(session, tenant_id):
            job = await jobs_service.start_job(session, job_id)
            if job is None:
                return None
            return StartedJob(
                job_id=job.id,
                tenant_id=job.tenant_id,
                kind=job.kind,
                agent_id=job.agent_id,
                created_by=job.created_by,
                draft_revision=job.draft_revision,
                partner_id=await partner_id_for_tenant(session, job.tenant_id),
            )

    async def heartbeat(self, tenant_id: uuid.UUID, job_id: uuid.UUID) -> bool:
        async with self._session() as session, tenant_scoped_session(session, tenant_id):
            beat: bool = await jobs_service.heartbeat(session, job_id)
            return beat

    async def progress(
        self,
        tenant_id: uuid.UUID,
        job_id: uuid.UUID,
        *,
        step: str | None = None,
        block: dict[str, Any] | None = None,
    ) -> bool:
        async with self._session() as session, tenant_scoped_session(session, tenant_id):
            noted: bool = await jobs_service.report_progress(
                session, job_id, step=step, block=block
            )
            return noted

    async def finish(
        self, tenant_id: uuid.UUID, job_id: uuid.UUID, *, result: dict[str, Any], cost_micros: int
    ) -> bool:
        async with self._session() as session, tenant_scoped_session(session, tenant_id):
            done: bool = await jobs_service.finish_job(
                session, job_id, result=result, cost_micros=cost_micros
            )
            return done

    async def fail(
        self, tenant_id: uuid.UUID, job_id: uuid.UUID, *, error_code: str, cost_micros: int = 0
    ) -> bool:
        async with self._session() as session, tenant_scoped_session(session, tenant_id):
            failed: bool = await jobs_service.fail_job(
                session, job_id, error_code=error_code, cost_micros=cost_micros
            )
            return failed

    async def settle(self, tenant_id: uuid.UUID, job_id: uuid.UUID) -> str | None:
        async with self._session() as session, tenant_scoped_session(session, tenant_id):
            job = await jobs_service.get_job(session, job_id)
            status: str | None = None if job is None else job.status
            return status


__all__ = ["DbJobStore", "JobStore"]
