"""Los agentes que sugiere el constructor del cliente — spec 047, enmienda del
2026-10-29 (requisito 60.6; contrato §10).

- ``GET /console/clients/{ref}/suggested-agents`` [``agents:read``] →
  ``{"agents": [{"id", "name", "description", "role"}]}``: los pendientes, sin los
  que ya existen como agente. ``role`` es ``reception | sales | billing | support``
  o ``null``.
- ``POST …/suggested-agents/{id}/dismiss`` [``agents:write``] → ``204``. Lo
  descartado no vuelve. Un id de otro cliente es el mismo ``404`` que uno
  inventado.

«Crear este agente» no tiene ruta: abre «Nuevo agente» con ``name`` y
``description`` rellenos y el agente nace con su primer borrador, como cualquiera.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from nexus_api.services.builder import suggested_agents as service

from .deps import ClientScope, client_scope

router = APIRouter(prefix="/clients/{ref}/suggested-agents", tags=["console-agents"])


class SuggestedAgentOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    role: Literal["reception", "sales", "billing", "support"] | None = None


class SuggestedAgentsOut(BaseModel):
    agents: list[SuggestedAgentOut]


@router.get("", response_model=SuggestedAgentsOut)
async def list_suggested_agents(
    scope: ClientScope = Depends(client_scope("agents:read")),
) -> SuggestedAgentsOut:
    rows = await service.list_open(scope.session)
    return SuggestedAgentsOut(
        agents=[
            SuggestedAgentOut(
                id=row.id,
                name=row.name,
                description=row.description,
                role=row.role,  # type: ignore[arg-type]
            )
            for row in rows
        ]
    )


@router.post("/{suggestion_id}/dismiss", status_code=status.HTTP_204_NO_CONTENT)
async def dismiss_suggested_agent(
    suggestion_id: uuid.UUID,
    scope: ClientScope = Depends(client_scope("agents:write")),
) -> Response:
    try:
        await service.dismiss(scope.session, suggestion_id, actor=scope.principal.actor)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail={"code": "unknown_suggested_agent"}
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
