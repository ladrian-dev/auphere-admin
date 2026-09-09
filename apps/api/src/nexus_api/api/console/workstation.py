"""``/console/clients/{ref}/workstation`` — el puesto de trabajo del partner.

**La lista blanca de ejecutables solo se modifica aquí.** Ése es el punto entero del
Requisito 2: un ejecutable ausente de la lista no se puede aprobar en caliente
durante una conversación; entra por esta puerta, con una persona detrás y su nombre
en la fila. Lo que sí se aprueba en el turno son *argumentos* de un ejecutable ya
permitido, y eso no se toca desde aquí.

Por eso ``workstation:write`` no lo tiene el rol *builder*: añadir un ejecutable es
una decisión de seguridad, no de configuración.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status

from nexus_api.db.models import PartnerDevice
from nexus_api.repositories.local_workstation import (
    LocalExecutableRepository,
    LocalExecutionRepository,
    PartnerDeviceRepository,
)

from .deps import ClientScope, client_scope
from .schemas_workstation import (
    DeviceIn,
    DeviceOut,
    ExecutableIn,
    ExecutableOut,
    ExecutionOut,
)

router = APIRouter(prefix="/clients/{ref}/workstation")

#: Requisito 4.2 — el latido se emite cada 10 s y la presencia caduca a los 30.
#: La convención es la de Kubernetes y Consul, y cabe dentro del minuto de CE-004.
PRESENCE_EXPIRY = timedelta(seconds=30)


def _presence(device: PartnerDevice, *, now: datetime | None = None) -> str:
    """Deriva la presencia. No hay columna que consultar, y es a propósito."""
    if device.last_heartbeat_at is None:
        return "ausente"
    reference = now or datetime.now(UTC)
    return "presente" if reference - device.last_heartbeat_at < PRESENCE_EXPIRY else "ausente"


def _device_out(device: PartnerDevice) -> DeviceOut:
    return DeviceOut(
        id=device.id,
        display_name=device.display_name,
        platform=device.platform,
        workdir=device.workdir,
        app_version=device.app_version,
        last_heartbeat_at=device.last_heartbeat_at,
        presence=_presence(device),
        enrolled_at=device.enrolled_at,
    )


# ── dispositivos ───────────────────────────────────────────────────────


@router.get("/devices", response_model=list[DeviceOut])
async def list_devices(
    scope: ClientScope = Depends(client_scope("workstation:read")),
) -> list[DeviceOut]:
    devices = await PartnerDeviceRepository(scope.session).list_active()
    return [_device_out(d) for d in devices]


@router.post("/devices", response_model=DeviceOut, status_code=status.HTTP_201_CREATED)
async def enrol_device(
    payload: DeviceIn,
    scope: ClientScope = Depends(client_scope("workstation:write")),
) -> DeviceOut:
    device = await PartnerDeviceRepository(scope.session).enrol(
        principal_id=scope.principal.user_id,
        display_name=payload.display_name,
        platform=payload.platform,
        workdir=payload.workdir,
        app_version=payload.app_version,
    )
    return _device_out(device)


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_device(
    device_id: uuid.UUID,
    scope: ClientScope = Depends(client_scope("workstation:write")),
) -> None:
    """Archiva el dispositivo. Borrar no existe."""
    repo = PartnerDeviceRepository(scope.session)
    if await repo.get(device_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await repo.revoke(device_id)


# ── lista blanca ───────────────────────────────────────────────────────


@router.get("/executables", response_model=list[ExecutableOut])
async def list_executables(
    scope: ClientScope = Depends(client_scope("workstation:read")),
) -> list[ExecutableOut]:
    rows = await LocalExecutableRepository(scope.session).list_active()
    return [
        ExecutableOut(id=r.id, executable=r.executable, added_by=r.added_by, added_at=r.added_at)
        for r in rows
    ]


@router.post("/executables", response_model=ExecutableOut, status_code=status.HTTP_201_CREATED)
async def add_executable(
    payload: ExecutableIn,
    scope: ClientScope = Depends(client_scope("workstation:write")),
) -> ExecutableOut:
    """Añade un ejecutable a la lista blanca, con la persona que lo decidió."""
    row = await LocalExecutableRepository(scope.session).add(
        executable=payload.executable, added_by=scope.principal.user_id
    )
    return ExecutableOut(
        id=row.id, executable=row.executable, added_by=row.added_by, added_at=row.added_at
    )


@router.delete("/executables/{executable_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_executable(
    executable_id: uuid.UUID,
    scope: ClientScope = Depends(client_scope("workstation:write")),
) -> None:
    await LocalExecutableRepository(scope.session).archive(executable_id)


# ── auditoría ──────────────────────────────────────────────────────────


@router.get("/executions", response_model=list[ExecutionOut])
async def recent_executions(
    scope: ClientScope = Depends(client_scope("workstation:read")),
) -> list[ExecutionOut]:
    """Qué se ejecutó y qué se denegó. **No** qué dijo el comando (§III)."""
    rows = await LocalExecutionRepository(scope.session).recent()
    return [
        ExecutionOut(
            id=r.id,
            executable=r.executable,
            outcome=r.outcome,
            denial_code=r.denial_reason,
            started_at=r.started_at,
            ended_at=r.ended_at,
            exit_code=r.exit_code,
            children_reaped=r.children_reaped,
        )
        for r in rows
    ]
