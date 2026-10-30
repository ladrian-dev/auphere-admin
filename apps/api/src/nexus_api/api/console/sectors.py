"""``GET /console/sectors`` — los sectores con guía de Auphere, para el selector de
Datos básicos (spec 047, enmienda del 2026-10-29: requisito 57.5; contrato §10).

``{"sectors": [{"key", "label"}]}``, en el orden de las guías. «Otro» no va: la
consola lo ofrece con su etiqueta libre (``PUT …/business/basics`` con
``sector: {key: "otro", label}``). Es un catálogo de la plataforma: sin cliente y
sin nada de ningún partner.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.services.business import sector as sector_service

router = APIRouter(tags=["console-business"])


class SectorOptionOut(BaseModel):
    key: str
    label: str


class SectorsOut(BaseModel):
    sectors: list[SectorOptionOut]


@router.get("/sectors", response_model=SectorsOut)
async def list_sectors(
    _principal: ConsolePrincipal = Depends(require_console_principal("clients:read")),
) -> SectorsOut:
    return SectorsOut(sectors=[SectorOptionOut(**option) for option in sector_service.options()])


__all__ = ["router"]
