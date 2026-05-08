"""AgentConfigService — orchestrates AgentConfigRepository + AuditRepository
+ ToolCatalogRepository, applying validation rules from
architecture/agent-assembly.md "Validaciones pre-promote".
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.errors import AgentConfigConflict
from nexus_api.db.models import AgentConfig
from nexus_api.repositories import (
    AgentConfigRepository,
    AuditRepository,
    ToolCatalogRepository,
)


class AgentConfigService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.configs = AgentConfigRepository(session)
        self.audit = AuditRepository(session)
        self.tools = ToolCatalogRepository(session)

    async def list_versions(self) -> list[AgentConfig]:
        return list(await self.configs.list_all())

    async def get_active(self) -> AgentConfig | None:
        return await self.configs.get_active()

    async def stage_new_version(
        self,
        *,
        actor: str,
        system_prompt_rendered: str,
        channels: list[dict[str, Any]],
        tools: list[str],
        policies: dict[str, Any],
        seed_template_ref: str | None = None,
        kg_schema_id: uuid.UUID | None = None,
    ) -> AgentConfig:
        await self._validate_tools(tools)
        config = await self.configs.create_staged(
            system_prompt_rendered=system_prompt_rendered,
            channels=channels,
            tools=tools,
            policies=policies,
            seed_template_ref=seed_template_ref,
            kg_schema_id=kg_schema_id,
            created_by=actor,
        )
        await self.audit.record(
            actor=actor,
            action="agent_config.stage",
            target=str(config.id),
            after={"version": config.version, "status": config.status.value},
        )
        return config

    async def promote(self, version: int, *, actor: str) -> AgentConfig:
        before = await self.configs.get_active()
        config = await self.configs.promote(version, promoted_by=actor)
        await self.audit.record(
            actor=actor,
            action="agent_config.promote",
            target=str(config.id),
            before={"version": before.version} if before else None,
            after={"version": config.version},
        )
        return config

    async def rollback(self, target_version: int, *, actor: str) -> AgentConfig:
        before = await self.configs.get_active()
        if before is not None and before.version == target_version:
            raise AgentConfigConflict(f"version {target_version} is already active")
        config = await self.configs.rollback(target_version, promoted_by=actor)
        await self.audit.record(
            actor=actor,
            action="agent_config.rollback",
            target=str(config.id),
            before={"version": before.version} if before else None,
            after={"version": config.version},
        )
        return config

    async def _validate_tools(self, tools: list[str]) -> None:
        if not tools:
            return
        catalog = {t.name for t in await self.tools.list_all(include_deprecated=True)}
        unknown = [t for t in tools if t not in catalog]
        if unknown:
            raise AgentConfigConflict("Tools not in catalog: " + ", ".join(unknown))
