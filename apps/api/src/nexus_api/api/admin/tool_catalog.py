from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.security import require_admin_token
from nexus_api.repositories import ToolCatalogRepository
from nexus_api.schemas.tool_catalog import ToolCatalogOut

router = APIRouter()


@router.get(
    "/tool-catalog",
    response_model=list[ToolCatalogOut],
    dependencies=[Depends(require_admin_token)],
)
async def list_tools(
    include_deprecated: bool = Query(default=False),
    session: AsyncSession = Depends(get_db_session),
) -> list[ToolCatalogOut]:
    repo = ToolCatalogRepository(session)
    return [
        ToolCatalogOut.model_validate(t)
        for t in await repo.list_all(include_deprecated=include_deprecated)
    ]
