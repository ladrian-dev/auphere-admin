from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.security import require_admin_token
from nexus_api.repositories import TenantRepository
from nexus_api.schemas.tenant import TenantOut

router = APIRouter()


@router.get(
    "/tenants",
    response_model=list[TenantOut],
    dependencies=[Depends(require_admin_token)],
)
async def list_tenants(
    session: AsyncSession = Depends(get_db_session),
) -> list[TenantOut]:
    repo = TenantRepository(session)
    return [TenantOut.model_validate(t) for t in await repo.list_all()]


@router.get(
    "/tenants/{tenant_id}",
    response_model=TenantOut,
    dependencies=[Depends(require_admin_token)],
)
async def get_tenant(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> TenantOut:
    repo = TenantRepository(session)
    tenant = await repo.get(tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"tenant {tenant_id} not found"
        )
    return TenantOut.model_validate(tenant)
