"""El otro extremo del puente — Requisitos 6.1, 6.2 y 6.3.

**No va bajo `/console`**, y no es cosmética: `/console/*` lo llama una persona con
una sesión, y lo audita `test_console_scope` con reglas pensadas para eso. Esto lo
llama una **máquina** con una credencial de dispositivo. Mezclarlos obligaría a
relajar las reglas de un sitio para que cupiera el otro.

**Todo es respuesta a un sondeo.** No hay ninguna ruta que empuje hacia la máquina
del partner: ``poll`` devuelve lo que haya, y si no hay nada devuelve una lista
vacía. Instalar esto no abre un puerto en casa de nadie (Requisito 6.1).

**El `tenant_id` no llega del llamante**, ni siquiera aquí: viaja dentro de la
firma de la credencial y la RLS decide después. Es §I aplicado a un canal nuevo.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import _tenant_scoped, get_db_session
from nexus_api.repositories.local_workstation import (
    LocalExecutionRepository,
    PartnerDeviceRepository,
)
from nexus_api.services.device_credential import (
    DeviceClaims,
    DeviceCredentialError,
    verify_device_token,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/device", tags=["device-bridge"])


async def require_device(
    authorization: Annotated[str | None, Header()] = None,
) -> DeviceClaims:
    """Resuelve qué dispositivo llama. Falla cerrado ante cualquier duda."""
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    try:
        return verify_device_token(token)
    except DeviceCredentialError as exc:
        # Se registra el intento (Requisito 6.4) sin filtrar el motivo al llamante:
        # decirle *por qué* falló su token le ayuda a acertar en el siguiente.
        log.warning("device_bridge.rejected", reason=str(exc))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from exc


async def device_scoped_session(
    claims: DeviceClaims = Depends(require_device),
    session: AsyncSession = Depends(get_db_session),
) -> AsyncIterator[AsyncSession]:
    """Sesión con RLS del tenant que **firma la credencial**, no de uno que llegue.

    Reutiliza la misma ceremonia que el resto de la API (`_tenant_scoped`): RLS,
    contextvar y transacción. Lo único que cambia es de dónde sale el tenant — de
    la firma, no de la ruta —, que es §I dicho para un canal que no tiene persona
    detrás.
    """
    async for scoped in _tenant_scoped(claims.tenant_id, session):
        yield scoped


class HeartbeatIn(BaseModel):
    app_version: str | None = Field(default=None, max_length=64)


class PollOut(BaseModel):
    """Lo que la plataforma tiene para esta máquina. Vacío es una respuesta."""

    work: list[dict[str, Any]] = Field(default_factory=list)


class ResultIn(BaseModel):
    execution_id: uuid.UUID
    outcome: str = Field(pattern="^(completada|expirada|terminada|denegada)$")
    exit_code: int | None = None
    children_reaped: int = 0


@router.post("/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
async def heartbeat(
    body: HeartbeatIn,
    claims: DeviceClaims = Depends(require_device),
    session: AsyncSession = Depends(device_scoped_session),
) -> None:
    """Late. **Solo** mueve `last_heartbeat_at`: no hay estado que desincronizar."""
    await PartnerDeviceRepository(session).record_heartbeat(claims.device_id)


@router.get("/poll", response_model=PollOut)
async def poll(claims: DeviceClaims = Depends(require_device)) -> PollOut:
    """Devuelve el trabajo pendiente de **esta** máquina.

    Hoy siempre vacío: el despachador que encola trabajo llega con la ejecución
    real. Existe ya porque es la mitad del contrato que hace que el puente sea
    saliente — sin ella, la tentación sería empujar desde la plataforma.
    """
    return PollOut(work=[])


@router.post("/result", status_code=status.HTTP_204_NO_CONTENT)
async def result(
    body: ResultIn,
    _: DeviceClaims = Depends(require_device),
    session: AsyncSession = Depends(device_scoped_session),
) -> None:
    """Cierra el asiento de auditoría. La salida del comando **no** viaja aquí."""
    await LocalExecutionRepository(session).finish(
        body.execution_id,
        outcome=body.outcome,
        exit_code=body.exit_code,
        children_reaped=body.children_reaped,
    )
