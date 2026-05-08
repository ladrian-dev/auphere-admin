"""Tool catalog — global, no RLS. Read-only from API in block B (writes via migration)."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import ToolCatalog, ToolStatus


class ToolCatalogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self, *, include_deprecated: bool = False) -> Sequence[ToolCatalog]:
        stmt = select(ToolCatalog).order_by(ToolCatalog.name)
        if not include_deprecated:
            stmt = stmt.where(ToolCatalog.status != ToolStatus.DEPRECATED)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_name(self, name: str) -> ToolCatalog | None:
        stmt = select(ToolCatalog).where(ToolCatalog.name == name)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
