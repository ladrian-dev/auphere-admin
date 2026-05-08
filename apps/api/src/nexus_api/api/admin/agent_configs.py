from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import scoped_session_from_path
from nexus_api.core.errors import AgentConfigConflict
from nexus_api.core.security import require_admin_token
from nexus_api.schemas.agent_config import (
    AgentConfigBundle,
    AgentConfigOut,
    AgentConfigStageIn,
)
from nexus_api.services import AgentConfigService

router = APIRouter()


@router.get(
    "/tenants/{tenant_id}/agent-config",
    response_model=AgentConfigBundle,
    dependencies=[Depends(require_admin_token)],
)
async def get_agent_config(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(scoped_session_from_path),
) -> AgentConfigBundle:
    svc = AgentConfigService(session)
    versions = await svc.list_versions()
    active = await svc.get_active()
    return AgentConfigBundle(
        active=AgentConfigOut.model_validate(active) if active else None,
        versions=[AgentConfigOut.model_validate(v) for v in versions],
    )


@router.put(
    "/tenants/{tenant_id}/agent-config",
    response_model=AgentConfigOut,
    status_code=status.HTTP_201_CREATED,
)
async def stage_agent_config(
    tenant_id: uuid.UUID,
    body: AgentConfigStageIn,
    session: AsyncSession = Depends(scoped_session_from_path),
    actor: str = Depends(require_admin_token),
) -> AgentConfigOut:
    svc = AgentConfigService(session)
    try:
        config = await svc.stage_new_version(
            actor=f"admin:{actor[:8]}",
            system_prompt_rendered=body.system_prompt_rendered,
            channels=body.channels,
            tools=body.tools,
            policies=body.policies,
            seed_template_ref=body.seed_template_ref,
            kg_schema_id=body.kg_schema_id,
        )
    except AgentConfigConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return AgentConfigOut.model_validate(config)


@router.post(
    "/tenants/{tenant_id}/agent-config/{version}/promote",
    response_model=AgentConfigOut,
)
async def promote_agent_config(
    tenant_id: uuid.UUID,
    version: int,
    session: AsyncSession = Depends(scoped_session_from_path),
    actor: str = Depends(require_admin_token),
) -> AgentConfigOut:
    svc = AgentConfigService(session)
    try:
        config = await svc.promote(version, actor=f"admin:{actor[:8]}")
    except AgentConfigConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return AgentConfigOut.model_validate(config)


@router.post(
    "/tenants/{tenant_id}/agent-config/{version}/rollback",
    response_model=AgentConfigOut,
)
async def rollback_agent_config(
    tenant_id: uuid.UUID,
    version: int,
    session: AsyncSession = Depends(scoped_session_from_path),
    actor: str = Depends(require_admin_token),
) -> AgentConfigOut:
    svc = AgentConfigService(session)
    try:
        config = await svc.rollback(version, actor=f"admin:{actor[:8]}")
    except AgentConfigConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return AgentConfigOut.model_validate(config)
