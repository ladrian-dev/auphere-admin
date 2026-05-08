"""AgentConfig repository — versioned. Tenant scope enforced by RLS via
`SET LOCAL app.tenant_id`. Methods do NOT accept tenant_id; the active session
must already be tenant-scoped (architecture/agent-isolation.md tabla "Capas").
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.errors import AgentConfigConflict
from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import AgentConfig, AgentConfigStatus


class AgentConfigRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> Sequence[AgentConfig]:
        require_current_tenant()
        stmt = select(AgentConfig).order_by(desc(AgentConfig.version))
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get(self, config_id: uuid.UUID) -> AgentConfig | None:
        require_current_tenant()
        return await self._session.get(AgentConfig, config_id)

    async def get_active(self) -> AgentConfig | None:
        require_current_tenant()
        stmt = select(AgentConfig).where(AgentConfig.status == AgentConfigStatus.ACTIVE)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_version(self, version: int) -> AgentConfig | None:
        require_current_tenant()
        stmt = select(AgentConfig).where(AgentConfig.version == version)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _next_version(self) -> int:
        require_current_tenant()
        stmt = select(AgentConfig.version).order_by(desc(AgentConfig.version)).limit(1)
        result = await self._session.execute(stmt)
        latest = result.scalar()
        return (latest or 0) + 1

    async def create_staged(
        self,
        *,
        system_prompt_rendered: str,
        channels: list[dict[str, Any]],
        tools: list[str],
        policies: dict[str, Any],
        seed_template_ref: str | None,
        kg_schema_id: uuid.UUID | None,
        created_by: str | None,
    ) -> AgentConfig:
        tenant_id = require_current_tenant()
        version = await self._next_version()
        config = AgentConfig(
            tenant_id=tenant_id,
            version=version,
            status=AgentConfigStatus.STAGED,
            system_prompt_rendered=system_prompt_rendered,
            channels=channels,
            tools=tools,
            policies=policies,
            seed_template_ref=seed_template_ref,
            kg_schema_id=kg_schema_id,
            created_by=created_by,
        )
        self._session.add(config)
        await self._session.flush()
        return config

    async def promote(self, version: int, *, promoted_by: str | None) -> AgentConfig:
        require_current_tenant()
        target = await self.get_by_version(version)
        if target is None:
            raise AgentConfigConflict(f"version {version} not found")
        if target.status == AgentConfigStatus.ACTIVE:
            return target
        if target.status != AgentConfigStatus.STAGED:
            raise AgentConfigConflict(
                f"version {version} is {target.status.value}; only staged versions can be promoted"
            )

        # Demote any current active version.
        await self._session.execute(
            update(AgentConfig)
            .where(AgentConfig.status == AgentConfigStatus.ACTIVE)
            .values(status=AgentConfigStatus.ARCHIVED)
        )
        target.status = AgentConfigStatus.ACTIVE
        target.promoted_at = datetime.now(UTC)
        target.promoted_by = promoted_by
        await self._session.flush()
        await self._session.refresh(target)
        return target

    async def rollback(self, target_version: int, *, promoted_by: str | None) -> AgentConfig:
        """Re-promote a previously archived version. Current active becomes archived."""
        require_current_tenant()
        target = await self.get_by_version(target_version)
        if target is None:
            raise AgentConfigConflict(f"version {target_version} not found")
        if target.status == AgentConfigStatus.ACTIVE:
            return target
        if target.status not in {AgentConfigStatus.ARCHIVED, AgentConfigStatus.STAGED}:
            raise AgentConfigConflict(
                f"cannot rollback to version {target_version} (status={target.status.value})"
            )

        await self._session.execute(
            update(AgentConfig)
            .where(AgentConfig.status == AgentConfigStatus.ACTIVE)
            .values(status=AgentConfigStatus.ARCHIVED)
        )
        target.status = AgentConfigStatus.ACTIVE
        target.promoted_at = datetime.now(UTC)
        target.promoted_by = promoted_by
        await self._session.flush()
        await self._session.refresh(target)
        return target
