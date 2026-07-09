"""Repository for the web chat widget config (migration 0050).

``tenant_widget_configs`` is NOT tenant-scoped (no RLS) — it is the layer
that decides which tenant a widget session may touch, resolved by the
public site key before any tenant scope exists.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import TenantWidgetConfig


class WidgetConfigRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_public_key(self, public_key: str) -> TenantWidgetConfig | None:
        result = await self._session.execute(
            sa.select(TenantWidgetConfig)
            .where(TenantWidgetConfig.public_key == public_key)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_for_tenant(self, tenant_id: uuid.UUID) -> TenantWidgetConfig | None:
        result = await self._session.execute(
            sa.select(TenantWidgetConfig).where(TenantWidgetConfig.tenant_id == tenant_id).limit(1)
        )
        return result.scalar_one_or_none()

    async def create(self, config: TenantWidgetConfig) -> TenantWidgetConfig:
        self._session.add(config)
        await self._session.flush()
        return config
