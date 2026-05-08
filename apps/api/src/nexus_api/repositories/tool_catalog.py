"""Tool catalog — global, no RLS. Read-only from API in block B (writes via migration)."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import ToolCatalog, ToolStatus


class ToolCatalogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(
        self,
        *,
        include_deprecated: bool = False,
        include_internal: bool = False,
    ) -> Sequence[ToolCatalog]:
        """Default excluye DEPRECATED e INTERNAL.

        ``include_internal=True`` lo necesita ``AgentConfigService._validate_tools``
        para que la whitelist se pueda chequear contra el catálogo completo
        (rechazo explícito si alguien intenta meter una internal). El
        operator panel (Bloque G) usa el default — los agentes no
        whitelistean internals, así que no las ofrecemos en la UI.
        """
        stmt = select(ToolCatalog).order_by(ToolCatalog.name)
        if not include_deprecated:
            stmt = stmt.where(ToolCatalog.status != ToolStatus.DEPRECATED)
        if not include_internal:
            stmt = stmt.where(ToolCatalog.status != ToolStatus.INTERNAL)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_name(self, name: str) -> ToolCatalog | None:
        stmt = select(ToolCatalog).where(ToolCatalog.name == name)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
