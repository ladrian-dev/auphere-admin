from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import Channel


class ChannelRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> Sequence[Channel]:
        require_current_tenant()
        stmt = select(Channel).order_by(Channel.created_at.asc())
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get(self, channel_id: uuid.UUID) -> Channel | None:
        require_current_tenant()
        return await self._session.get(Channel, channel_id)
