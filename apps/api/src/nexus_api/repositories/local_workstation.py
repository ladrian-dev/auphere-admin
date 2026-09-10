"""Repositorios del puesto de trabajo en la máquina del partner (migraciones 0106 y 0107).

**Ni el tenant, ni el partner, ni la persona llegan del llamante.** Salen del
contexto de petición (``require_current_tenant`` / ``require_current_partner``) y
la RLS decide; ``test_10_repos_reject_explicit_tenant`` lo comprueba por
introspección para el tenant.

Tres repositorios nuevos con la spec 002, y una regla que no está en el esquema y
sí aquí: **las máquinas se ven por la persona dueña**. ``list_visible`` no filtra
nada — es la RLS de ``partner_devices`` (dueña o gestor) la que decide qué filas
existen para quien pregunta. Un ``WHERE principal_id`` en el repositorio sería una
copia de la regla que alguien podría olvidar (Requisito 5.4).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.pairing_codes import CODE_TTL, generate_code, hash_code
from nexus_api.core.partner_context import require_current_partner
from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import (
    DeviceClientLink,
    DevicePairingCode,
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
    """Máquinas del partner. La presencia se deriva del latido, no se guarda."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_visible(self, *, include_archived: bool = False) -> Sequence[PartnerDevice]:
        """Las que la RLS deje ver: las propias, o todas si hay gestor en contexto."""
        require_current_partner()
        stmt = select(PartnerDevice).order_by(PartnerDevice.enrolled_at)
        if not include_archived:
            stmt = stmt.where(PartnerDevice.revoked_at.is_(None))
        return (await self._session.execute(stmt)).scalars().all()

    async def get(self, device_id: uuid.UUID) -> PartnerDevice | None:
        require_current_partner()
        return await self._session.get(PartnerDevice, device_id)

    async def pair(
        self,
        *,
        principal_id: str,
        display_name: str,
        hostname: str,
        platform: str,
        app_version: str | None = None,
    ) -> PartnerDevice:
        """Da de alta la máquina a nombre del partner en contexto y de la persona."""
        partner_id = require_current_partner()
        device = PartnerDevice(
            id=uuid.uuid4(),
            partner_id=uuid.UUID(str(partner_id)),
            principal_id=principal_id,
            display_name=display_name,
            hostname=hostname,
            platform=platform,
            app_version=app_version,
        )
        self._session.add(device)
        await self._session.flush()
        return device

    async def rename(self, device_id: uuid.UUID, *, display_name: str) -> PartnerDevice | None:
        require_current_partner()
        device = await self._session.get(PartnerDevice, device_id)
        if device is None or device.revoked_at is not None:
            return None
        device.display_name = display_name
        await self._session.flush()
        return device

    async def record_heartbeat(
        self, device_id: uuid.UUID, *, at: datetime | None = None, app_version: str | None = None
    ) -> None:
        """Solo mueve ``last_heartbeat_at``. No hay estado que actualizar (§V).

        ``app_version`` se acepta y se ignora a propósito: la versión se fija al
        emparejar y al renovar; el latido no toca otra columna (``T072``).
        """
        require_current_partner()
        device = await self._session.get(PartnerDevice, device_id)
        if device is not None:
            device.last_heartbeat_at = at or datetime.now(UTC)

    async def rotate_credential(
        self, device_id: uuid.UUID, *, app_version: str | None = None
    ) -> int:
        """Sube la generación y marca la rotación. Devuelve la generación nueva."""
        require_current_partner()
        device = await self._session.get(PartnerDevice, device_id)
        if device is None:
            raise LookupError("device not found")
        device.credential_generation += 1
        device.credential_rotated_at = datetime.now(UTC)
        if app_version:
            device.app_version = app_version
        await self._session.flush()
        return device.credential_generation

    async def archive(self, device_id: uuid.UUID, *, reason: str) -> PartnerDevice | None:
        """Borrar no existe: se archiva, y queda por qué. Terminal."""
        require_current_partner()
        device = await self._session.get(PartnerDevice, device_id)
        if device is None:
            return None
        if device.revoked_at is None:
            device.revoked_at = datetime.now(UTC)
            device.revoked_reason = reason
            await self._session.flush()
        return device

    async def archive_all_for_principal(self, principal_id: str, *, reason: str) -> int:
        """Todas las máquinas de una persona. Corre con el rol dueño: es mantenimiento
        de plataforma que ocurre cuando la persona ya no está (Requisito 11.4)."""
        result = await self._session.execute(
            update(PartnerDevice)
            .where(PartnerDevice.principal_id == principal_id, PartnerDevice.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC), revoked_reason=reason)
        )
        return int(getattr(result, "rowcount", 0) or 0)


class DeviceClientLinkRepository:
    """A qué clientes sirve una máquina y en qué directorio. Dato de tenant."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def active_for_tenant(self) -> Sequence[DeviceClientLink]:
        require_current_tenant()
        stmt = (
            select(DeviceClientLink)
            .where(DeviceClientLink.removed_at.is_(None))
            .order_by(DeviceClientLink.created_at)
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def active_for_device(self, device_id: uuid.UUID) -> Sequence[DeviceClientLink]:
        """Los vínculos de una máquina, entre tenants. Los filtra la política de lectura
        por máquina (a través de la RLS de ``partner_devices``), no un WHERE nuestro."""
        require_current_partner()
        stmt = (
            select(DeviceClientLink)
            .where(DeviceClientLink.device_id == device_id, DeviceClientLink.removed_at.is_(None))
            .order_by(DeviceClientLink.created_at)
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def find_active(self, device_id: uuid.UUID) -> DeviceClientLink | None:
        require_current_tenant()
        stmt = select(DeviceClientLink).where(
            DeviceClientLink.device_id == device_id, DeviceClientLink.removed_at.is_(None)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def link(self, *, device_id: uuid.UUID, created_by: str) -> DeviceClientLink:
        """Vincula sin directorio: ése lo declara la máquina (Requisito 7)."""
        tenant_id = require_current_tenant()
        existing = await self.find_active(device_id)
        if existing is not None:
            return existing
        row = DeviceClientLink(
            id=uuid.uuid4(),
            tenant_id=uuid.UUID(str(tenant_id)),
            device_id=device_id,
            workdir=None,
            created_by=created_by,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def declare_workdir(
        self, *, device_id: uuid.UUID, workdir: str
    ) -> DeviceClientLink | None:
        require_current_tenant()
        row = await self.find_active(device_id)
        if row is None:
            return None
        row.workdir = workdir
        row.declared_at = datetime.now(UTC)
        row.declared_by_device = True
        await self._session.flush()
        return row

    async def unlink(self, device_id: uuid.UUID) -> bool:
        require_current_tenant()
        row = await self.find_active(device_id)
        if row is None:
            return False
        row.removed_at = datetime.now(UTC)
        await self._session.flush()
        return True


class DevicePairingCodeRepository:
    """Códigos de emparejamiento. Se guarda el hash; el código se devuelve una vez."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def issue(self, *, principal_id: str) -> tuple[str, DevicePairingCode]:
        """Emite un código nuevo e invalida los vivos de la misma persona (uno por persona)."""
        partner_id = uuid.UUID(str(require_current_partner()))
        now = datetime.now(UTC)
        await self._session.execute(
            update(DevicePairingCode)
            .where(
                DevicePairingCode.partner_id == partner_id,
                DevicePairingCode.principal_id == principal_id,
                DevicePairingCode.consumed_at.is_(None),
                DevicePairingCode.expires_at > now,
            )
            .values(expires_at=now)
        )
        code = generate_code()
        row = DevicePairingCode(
            id=uuid.uuid4(),
            partner_id=partner_id,
            principal_id=principal_id,
            code_hash=hash_code(code),
            expires_at=now + CODE_TTL,
        )
        self._session.add(row)
        await self._session.flush()
        return code, row

    async def consume(self, code: str) -> DevicePairingCode | None:
        """Canje **atómico** y sin partner en contexto: corre con el rol dueño porque
        todavía no hay credencial. Partner y persona salen de la fila."""
        now = datetime.now(UTC)
        stmt = (
            update(DevicePairingCode)
            .where(
                DevicePairingCode.code_hash == hash_code(code),
                DevicePairingCode.consumed_at.is_(None),
                DevicePairingCode.expires_at > now,
            )
            .values(consumed_at=now)
            .returning(DevicePairingCode)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def bind_device(self, code_id: uuid.UUID, device_id: uuid.UUID) -> None:
        row = await self._session.get(DevicePairingCode, code_id)
        if row is not None:
            row.consumed_device_id = device_id


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
        """Solo desde la consola y con la persona nombrada (001-Requisito 2.1)."""
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
    """Permisos de argumentos. Nunca crean ejecutables (001-Requisito 2.2)."""

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
        """UPSERT idempotente sobre el uuid5: una carrera no crea dos permisos."""
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
    """Auditoría. Se escribe también cuando se deniega (001-Requisito 8.3)."""

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
    "DeviceClientLinkRepository",
    "DevicePairingCodeRepository",
    "LocalArgumentGrantRepository",
    "LocalExecutableRepository",
    "LocalExecutionRepository",
    "PartnerDeviceRepository",
    "grant_id_for",
]
