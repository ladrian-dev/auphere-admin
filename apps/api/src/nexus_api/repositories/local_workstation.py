"""Repositorios del puesto de trabajo en la máquina del partner (migración 0106).

**El ``tenant_id`` nunca llega del llamante.** Sale del contexto de petición
(``require_current_tenant``) y la RLS decide; por eso ningún método público de este
módulo acepta un parámetro ``tenant_id``, y ``test_10_repos_reject_explicit_tenant``
lo comprueba por introspección.

La lista blanca tiene una regla que no está en el esquema y sí aquí: **añadir un
ejecutable no es una operación del turno**. Estos repositorios la escriben, pero solo
los llaman los endpoints de consola, donde hay una persona detrás (Requisito 2.1).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import (
    LocalArgumentGrant,
    LocalExecutable,
    LocalExecution,
    PartnerDevice,
)

#: Espacio de nombres del uuid5 de los permisos de argumentos. Fijo y versionado:
#: cambiarlo re-crearía todos los permisos existentes como filas nuevas.
GRANT_NAMESPACE = uuid.UUID("6f2b1f7a-0f1a-4b6e-9f2c-8a3d5e7c1b40")


def grant_id_for(tenant_id: uuid.UUID, executable_id: uuid.UUID, argv_signature: str) -> uuid.UUID:
    """uuid5 determinista: dos aprobaciones simultáneas no crean dos permisos."""
    return uuid.uuid5(GRANT_NAMESPACE, f"{tenant_id}:{executable_id}:{argv_signature}")


class PartnerDeviceRepository:
    """Dispositivos declarados. La presencia se deriva del latido, no se guarda."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active(self) -> Sequence[PartnerDevice]:
        require_current_tenant()
        stmt = (
            select(PartnerDevice)
            .where(PartnerDevice.revoked_at.is_(None))
            .order_by(PartnerDevice.enrolled_at)
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def get(self, device_id: uuid.UUID) -> PartnerDevice | None:
        require_current_tenant()
        return await self._session.get(PartnerDevice, device_id)

    async def enrol(
        self,
        *,
        principal_id: str,
        display_name: str,
        platform: str,
        workdir: str,
        app_version: str | None = None,
    ) -> PartnerDevice:
        tenant_id = require_current_tenant()
        device = PartnerDevice(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            principal_id=principal_id,
            display_name=display_name,
            platform=platform,
            workdir=workdir,
            app_version=app_version,
        )
        self._session.add(device)
        await self._session.flush()
        return device

    async def record_heartbeat(self, device_id: uuid.UUID, *, at: datetime | None = None) -> None:
        """Solo mueve ``last_heartbeat_at``. No hay estado que actualizar (§V)."""
        require_current_tenant()
        device = await self._session.get(PartnerDevice, device_id)
        if device is not None:
            device.last_heartbeat_at = at or datetime.now(UTC)

    async def revoke(self, device_id: uuid.UUID) -> None:
        """Borrar no existe: se archiva."""
        require_current_tenant()
        device = await self._session.get(PartnerDevice, device_id)
        if device is not None and device.revoked_at is None:
            device.revoked_at = datetime.now(UTC)


class LocalExecutableRepository:
    """La lista blanca. Arranca vacía por tenant y no hay lista global."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active(self) -> Sequence[LocalExecutable]:
        require_current_tenant()
        stmt = (
            select(LocalExecutable)
            .where(LocalExecutable.removed_at.is_(None))
            .order_by(LocalExecutable.executable)
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def find_active(self, executable: str) -> LocalExecutable | None:
        """La consulta que hace el gate. Devuelve ``None`` si no está permitido."""
        require_current_tenant()
        stmt = select(LocalExecutable).where(
            LocalExecutable.executable == executable,
            LocalExecutable.removed_at.is_(None),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def add(self, *, executable: str, added_by: str) -> LocalExecutable:
        """Solo desde la consola y con la persona nombrada (Requisito 2.1)."""
        tenant_id = require_current_tenant()
        row = LocalExecutable(
            id=uuid.uuid4(), tenant_id=tenant_id, executable=executable, added_by=added_by
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def archive(self, executable_id: uuid.UUID) -> None:
        require_current_tenant()
        row = await self._session.get(LocalExecutable, executable_id)
        if row is not None and row.removed_at is None:
            row.removed_at = datetime.now(UTC)


class LocalArgumentGrantRepository:
    """Permisos de argumentos. Nunca crean ejecutables (Requisito 2.2)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_active(
        self, *, executable_id: uuid.UUID, argv_signature: str
    ) -> LocalArgumentGrant | None:
        require_current_tenant()
        stmt = select(LocalArgumentGrant).where(
            LocalArgumentGrant.executable_id == executable_id,
            LocalArgumentGrant.argv_signature == argv_signature,
            LocalArgumentGrant.revoked_at.is_(None),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def grant(
        self, *, executable_id: uuid.UUID, argv_signature: str, action_id: uuid.UUID
    ) -> uuid.UUID:
        """UPSERT idempotente sobre el uuid5: una carrera no crea dos permisos.

        ``action_id`` apunta a la aprobación durable de ``companion.actions``, que es
        donde viven ``state_hash``, ``decided_at`` y ``decided_by`` (§IV). Aquí no se
        duplica ninguno de los tres: habría dos sitios donde mirar quién aprobó qué.
        """
        tenant_id = require_current_tenant()
        grant_id = grant_id_for(tenant_id, executable_id, argv_signature)
        stmt = (
            pg_insert(LocalArgumentGrant)
            .values(
                id=grant_id,
                tenant_id=tenant_id,
                executable_id=executable_id,
                argv_signature=argv_signature,
                action_id=action_id,
            )
            .on_conflict_do_nothing(index_elements=[LocalArgumentGrant.id])
        )
        await self._session.execute(stmt)
        return grant_id

    async def revoke(self, grant_id: uuid.UUID) -> None:
        require_current_tenant()
        row = await self._session.get(LocalArgumentGrant, grant_id)
        if row is not None and row.revoked_at is None:
            row.revoked_at = datetime.now(UTC)


class LocalExecutionRepository:
    """Auditoría. Se escribe también cuando se deniega (Requisito 8.3)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_denial(
        self,
        *,
        device_id: uuid.UUID,
        executable: str,
        argv_signature: str,
        denial_reason: str,
    ) -> LocalExecution:
        """Una denegación sin motivo es una denegación que nadie puede auditar."""
        tenant_id = require_current_tenant()
        row = LocalExecution(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            device_id=device_id,
            executable=executable,
            argv_signature=argv_signature,
            outcome="denegada",
            denial_reason=denial_reason,
            ended_at=datetime.now(UTC),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def start(
        self,
        *,
        device_id: uuid.UUID,
        executable: str,
        argv_signature: str,
        grant_id: uuid.UUID | None,
    ) -> LocalExecution:
        tenant_id = require_current_tenant()
        row = LocalExecution(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            device_id=device_id,
            executable=executable,
            argv_signature=argv_signature,
            grant_id=grant_id,
            outcome="completada",  # se corrige al cerrar; nunca se queda sin cerrar
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def finish(
        self,
        execution_id: uuid.UUID,
        *,
        outcome: str,
        exit_code: int | None,
        children_reaped: int,
    ) -> None:
        """Cierra el asiento. ``children_reaped`` es la cuenta del Requisito 12.3."""
        require_current_tenant()
        row = await self._session.get(LocalExecution, execution_id)
        if row is not None:
            row.outcome = outcome
            row.exit_code = exit_code
            row.children_reaped = children_reaped
            row.ended_at = datetime.now(UTC)

    async def recent(self, limit: int = 50) -> Sequence[LocalExecution]:
        require_current_tenant()
        stmt = select(LocalExecution).order_by(LocalExecution.started_at.desc()).limit(limit)
        return (await self._session.execute(stmt)).scalars().all()


__all__ = [
    "GRANT_NAMESPACE",
    "LocalArgumentGrantRepository",
    "LocalExecutableRepository",
    "LocalExecutionRepository",
    "PartnerDeviceRepository",
    "grant_id_for",
]
