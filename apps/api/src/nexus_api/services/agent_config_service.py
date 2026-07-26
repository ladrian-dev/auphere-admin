"""AgentConfigService — orchestrates AgentConfigRepository + AuditRepository
+ ToolCatalogRepository, applying validation rules from
architecture/agent-assembly.md "Validaciones pre-promote".
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.errors import AgentConfigConflict
from nexus_api.db.models import AgentConfig, ToolStatus
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

    async def set_admin_access(
        self,
        *,
        actor: str,
        admin_phones: list[str],
        admins: list[dict[str, Any]] | None = None,
    ) -> AgentConfig:
        """Update the admin whitelist of the ACTIVE config and promote it.

        The whitelist (``policies.admin_access.admin_phones``) is the binary
        access model: a phone on the list can do everything the admin agent
        exposes; one off it gets no reply. Registering/editing admins from
        the partner app therefore clones the active config, swaps only
        ``admin_access``, and promotes — so the change travels through the
        normal STAGED → ACTIVE flow (audit + rollback) without touching the
        prompt/tools identity.

        Deliberately NOT gated by ``Tenant.eval_required``: changing who may
        talk to the agent is not a prompt/behaviour change, so it must not be
        blocked by (or require) an eval run. ``admins`` is optional metadata
        (e.g. ``[{"phone", "name"}]``) kept alongside the list for traceability;
        the runtime gate only ever reads ``admin_phones``.
        """
        active = await self.get_active()
        if active is None:
            raise AgentConfigConflict("tenant has no active agent config to update")

        policies = dict(active.policies or {})
        access = dict(policies.get("admin_access") or {})
        access["admin_only"] = True
        access["admin_phones"] = list(admin_phones)
        if admins is not None:
            access["admins"] = admins
        policies["admin_access"] = access

        staged = await self.stage_new_version(
            actor=actor,
            system_prompt_rendered=active.system_prompt_rendered,
            channels=list(active.channels or []),
            tools=list(active.tools or []),
            policies=policies,
            seed_template_ref=active.seed_template_ref,
            kg_schema_id=active.kg_schema_id,
        )
        return await self.promote(staged.version, actor=actor)

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
        catalog_rows = await self.tools.list_all(include_deprecated=True, include_internal=True)
        catalog = {t.name: t for t in catalog_rows}
        unknown = [t for t in tools if t not in catalog]
        if unknown:
            raise AgentConfigConflict("Tools not in catalog: " + ", ".join(unknown))
        # Bloque E: las tools internas (ej. ``agendapro.*``) NO pueden
        # entrar en la whitelist de un agent_config — solo se invocan vía
        # ``MCPRegistry.dispatch_internal`` desde otros servers. Defense
        # in depth: aunque el operator panel no las ofrezca, este check
        # captura un intento manual.
        internal = [t for t in tools if catalog[t].status == ToolStatus.INTERNAL]
        if internal:
            raise AgentConfigConflict(
                "Internal tools cannot be whitelisted for an agent: " + ", ".join(internal)
            )
