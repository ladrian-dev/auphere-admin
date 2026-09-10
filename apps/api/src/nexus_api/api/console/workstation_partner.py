"""``/console/workstation`` — el puesto de trabajo a nivel de partner (spec 002).

La 001 colgó el puesto de cada cliente porque modeló la máquina por tenant. La
002 la pone donde está: **la máquina es del partner y de la persona que la
emparejó**; los ejecutables —que sí son del cliente— se quedan en
``/console/clients/{ref}/workstation/executables``.

Reglas que se ven en cada ruta:

* Ninguna acepta ``partner_id``, ``principal_id`` ni ``tenant_id``: salen de la
  sesión y de la RLS. El cliente se nombra por ``client_ref``.
* Ninguna acepta un ``workdir``: la consola **no** teclea rutas (Requisito 7.1).
  El directorio lo declara la máquina por el puente.
* «Archivar» nunca borra.
* Qué máquinas se ven lo decide la RLS: la persona ve las suyas; con
  ``workstation:write`` la dependencia fija ``app.workstation_manager`` y se ven
  todas las del partner con su dueña (Requisito 5.2).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.core.partner_context import apply_partner_to_session, partner_context
from nexus_api.core.tenant_context import apply_tenant_to_session, tenant_context
from nexus_api.db.models import (
    AuditLog,
    DeviceClientLink,
    LocalExecutable,
    PartnerDevice,
    PartnerMembership,
    PartnerTenant,
)
from nexus_api.repositories.local_workstation import (
    DeviceClientLinkRepository,
    DevicePairingCodeRepository,
    PartnerDeviceRepository,
)
from nexus_api.services.device_pairing import CODE_TTL, display_code
from nexus_api.services.device_presence import derive_presence

from .deps import unknown_client
from .schemas_workstation import (
    LinkClientIn,
    MachineClientOut,
    MachineOut,
    MachineRenameIn,
    PairingCodeOut,
    SetupOut,
    SetupStepOut,
)

router = APIRouter(prefix="/workstation")

REASON_ARCHIVED_FROM_CONSOLE = "archivada_consola"


@dataclass(frozen=True)
class WorkstationScope:
    principal: ConsolePrincipal
    session: AsyncSession

    @property
    def manager(self) -> bool:
        return "workstation:write" in self.principal.permissions


def workstation_scope(*required: str) -> Callable[..., AsyncIterator[WorkstationScope]]:
    """Transacción con los tres GUC del puesto: partner, persona y —si toca— gestor."""
    principal_dep = require_console_principal(*required)

    async def _dependency(
        principal: ConsolePrincipal = Depends(principal_dep),
        session: AsyncSession = Depends(get_db_session),
    ) -> AsyncIterator[WorkstationScope]:
        async with session.begin():
            await apply_partner_to_session(
                session,
                principal.partner.id,
                principal_id=principal.user_id,
                workstation_manager="workstation:write" in principal.permissions,
            )
            with partner_context(str(principal.partner.id)):
                yield WorkstationScope(principal=principal, session=session)

    return _dependency


def _audit(scope: WorkstationScope, action: str, device: PartnerDevice, **after: object) -> None:
    scope.session.add(
        AuditLog(
            tenant_id=None,
            actor=scope.principal.actor,
            action=action,
            target=f"partner:{scope.principal.partner.id}",
            after_json={"machine": device.display_name, "device_id": str(device.id), **after},
        )
    )


async def _refs(scope: WorkstationScope) -> dict[uuid.UUID, tuple[str, str | None]]:
    rows = await scope.session.execute(
        select(
            PartnerTenant.tenant_id, PartnerTenant.external_client_ref, PartnerTenant.client_name
        ).where(PartnerTenant.partner_id == scope.principal.partner.id)
    )
    return {tenant_id: (ref, name) for tenant_id, ref, name in rows.all()}


async def _owners(scope: WorkstationScope, user_ids: set[str]) -> dict[str, str | None]:
    if not user_ids:
        return {}
    rows = await scope.session.execute(
        select(PartnerMembership.user_id, PartnerMembership.display_name).where(
            PartnerMembership.partner_id == scope.principal.partner.id,
            PartnerMembership.user_id.in_(user_ids),
        )
    )
    return {user_id: display_name for user_id, display_name in rows.all()}


async def _machine_out(scope: WorkstationScope, device: PartnerDevice) -> MachineOut:
    refs = await _refs(scope)
    owners = await _owners(scope, {device.principal_id})
    links = await DeviceClientLinkRepository(scope.session).active_for_device(device.id)
    return MachineOut(
        id=device.id,
        display_name=device.display_name,
        hostname=device.hostname,
        platform=device.platform,
        app_version=device.app_version,
        presence=derive_presence(device.last_heartbeat_at),
        last_heartbeat_at=device.last_heartbeat_at,
        enrolled_at=device.enrolled_at,
        owner_user_id=device.principal_id,
        owner_display_name=owners.get(device.principal_id),
        mine=device.principal_id == scope.principal.user_id,
        archived_at=device.revoked_at,
        archived_reason=device.revoked_reason,
        clients=[
            MachineClientOut(
                ref=refs[link.tenant_id][0],
                name=refs[link.tenant_id][1],
                workdir=link.workdir,
                needs_directory=link.workdir is None,
            )
            for link in links
            if link.tenant_id in refs
        ],
    )


async def _visible_device(scope: WorkstationScope, device_id: uuid.UUID) -> PartnerDevice:
    """La RLS ya decidió si existe para quien pregunta; aquí solo se traduce a 404."""
    device = await PartnerDeviceRepository(scope.session).get(device_id)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="machine not found")
    return device


# ── emparejar ───────────────────────────────────────────────────────────


@router.post("/pairing-codes", response_model=PairingCodeOut, status_code=status.HTTP_201_CREATED)
async def issue_pairing_code(
    scope: WorkstationScope = Depends(workstation_scope("workstation:pair")),
) -> PairingCodeOut:
    """Emite el código que la barra canjeará. Uno vivo por persona."""
    code, row = await DevicePairingCodeRepository(scope.session).issue(
        principal_id=scope.principal.user_id
    )
    scope.session.add(
        AuditLog(
            tenant_id=None,
            actor=scope.principal.actor,
            action="device.pair_code_issued",
            target=f"partner:{scope.principal.partner.id}",
            after_json={"expires_at": row.expires_at.isoformat()},
        )
    )
    return PairingCodeOut(
        code=display_code(code),
        expires_at=row.expires_at,
        ttl_seconds=int(CODE_TTL.total_seconds()),
    )


# ── máquinas ────────────────────────────────────────────────────────────


@router.get("/devices", response_model=list[MachineOut])
async def list_machines(
    include_archived: bool = False,
    scope: WorkstationScope = Depends(workstation_scope("workstation:read")),
) -> list[MachineOut]:
    devices = await PartnerDeviceRepository(scope.session).list_visible(
        include_archived=include_archived
    )
    return [await _machine_out(scope, d) for d in devices]


@router.patch("/devices/{device_id}", response_model=MachineOut)
async def rename_machine(
    device_id: uuid.UUID,
    body: MachineRenameIn,
    scope: WorkstationScope = Depends(workstation_scope("workstation:pair")),
) -> MachineOut:
    device = await _visible_device(scope, device_id)
    renamed = await PartnerDeviceRepository(scope.session).rename(
        device.id, display_name=body.display_name
    )
    if renamed is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="machine is archived")
    return await _machine_out(scope, renamed)


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_machine(
    device_id: uuid.UUID,
    scope: WorkstationScope = Depends(workstation_scope("workstation:pair")),
) -> None:
    """Archiva. Borrar no existe. El siguiente latido recibe ``device_archived``."""
    device = await _visible_device(scope, device_id)
    if device.revoked_at is None:
        await PartnerDeviceRepository(scope.session).archive(
            device.id, reason=REASON_ARCHIVED_FROM_CONSOLE
        )
        _audit(scope, "device.archived", device, reason=REASON_ARCHIVED_FROM_CONSOLE)


# ── clientes por máquina ────────────────────────────────────────────────


async def _mapping_or_404(scope: WorkstationScope, ref: str) -> PartnerTenant:
    mapping = await scope.session.get(PartnerTenant, (scope.principal.partner.id, ref))
    if mapping is None:
        raise unknown_client()
    return mapping


@router.post(
    "/devices/{device_id}/clients",
    response_model=MachineClientOut,
    status_code=status.HTTP_201_CREATED,
)
async def link_client(
    device_id: uuid.UUID,
    body: LinkClientIn,
    scope: WorkstationScope = Depends(workstation_scope("workstation:pair")),
) -> MachineClientOut:
    """Vincula un cliente a la máquina **sin directorio**: ése lo declara la máquina."""
    device = await _visible_device(scope, device_id)
    if device.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="machine is archived")
    mapping = await _mapping_or_404(scope, body.client_ref)
    await apply_tenant_to_session(scope.session, mapping.tenant_id)
    with tenant_context(mapping.tenant_id):
        link = await DeviceClientLinkRepository(scope.session).link(
            device_id=device.id, created_by=scope.principal.user_id
        )
    return MachineClientOut(
        ref=mapping.external_client_ref,
        name=mapping.client_name,
        workdir=link.workdir,
        needs_directory=link.workdir is None,
    )


@router.delete("/devices/{device_id}/clients/{ref}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_client(
    device_id: uuid.UUID,
    ref: str,
    scope: WorkstationScope = Depends(workstation_scope("workstation:pair")),
) -> None:
    # El ref se resuelve antes que la máquina: un cliente ajeno es un 404 opaco
    # idéntico al de un cliente inexistente (regla CP-04, `test_console_scope`).
    mapping = await _mapping_or_404(scope, ref)
    device = await _visible_device(scope, device_id)
    await apply_tenant_to_session(scope.session, mapping.tenant_id)
    with tenant_context(mapping.tenant_id):
        await DeviceClientLinkRepository(scope.session).unlink(device.id)


# ── la puesta en marcha, derivada por persona ───────────────────────────


@router.get("/setup", response_model=SetupOut)
async def setup(
    scope: WorkstationScope = Depends(workstation_scope("workstation:pair")),
) -> SetupOut:
    """Los cuatro pasos de **quien llama**, calculados de los datos en cada visita.

    No hay tabla: nada que pueda mentir (Requisito 6.2).
    """
    repo = PartnerDeviceRepository(scope.session)
    mine = [d for d in await repo.list_visible() if d.principal_id == scope.principal.user_id]
    links: list[DeviceClientLink] = []
    link_repo = DeviceClientLinkRepository(scope.session)
    for device in mine:
        links.extend(await link_repo.active_for_device(device.id))
    without_dir = [link for link in links if link.workdir is None]
    linked_tenants = {link.tenant_id for link in links}
    tenants_without_exec: set[uuid.UUID] = set()
    for tenant_id in linked_tenants:
        await apply_tenant_to_session(scope.session, tenant_id)
        with tenant_context(tenant_id):
            has_exec = await scope.session.scalar(
                select(LocalExecutable.id).where(LocalExecutable.removed_at.is_(None)).limit(1)
            )
        if has_exec is None:
            tenants_without_exec.add(tenant_id)
    if linked_tenants:
        # Volver al ámbito de partner tras recorrer los tenants.
        await apply_partner_to_session(
            scope.session,
            scope.principal.partner.id,
            principal_id=scope.principal.user_id,
            workstation_manager=scope.manager,
        )
    steps = [
        SetupStepOut(key="paired", done=bool(mine), pending=0 if mine else 1),
        SetupStepOut(key="clients", done=bool(links), pending=0 if links else 1),
        SetupStepOut(
            key="directories", done=bool(links) and not without_dir, pending=len(without_dir)
        ),
        SetupStepOut(
            key="executables",
            done=bool(linked_tenants) and not tenants_without_exec,
            pending=len(tenants_without_exec),
        ),
    ]
    return SetupOut(complete=all(s.done for s in steps), steps=steps)


__all__ = ["router", "workstation_scope"]
