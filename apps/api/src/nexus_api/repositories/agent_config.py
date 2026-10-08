"""AgentConfig repository — versioned. Tenant scope enforced by RLS via
`SET LOCAL app.tenant_id`. Methods do NOT accept tenant_id; the active session
must already be tenant-scoped (architecture/agent-isolation.md tabla "Capas").

Spec 030 (iteration 3): a client may have several agents, each with its own
active version. Every method takes an optional ``agent_id``; without one it
acts on the **principal agent** (the oldest active one), which is what a
single-agent client — every client before spec 030 — always meant. Version
numbers stay unique per tenant, so ``get_by_version`` needs no agent.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.errors import AgentConfigConflict, UnknownAgent
from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import Agent, AgentConfig, AgentConfigStatus, AgentStatus


class AgentConfigRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def principal_agent_id(self) -> uuid.UUID | None:
        """The oldest active agent of the tenant, or ``None`` if it has none."""
        require_current_tenant()
        found: uuid.UUID | None = await self._session.scalar(
            select(Agent.id)
            .where(Agent.status == AgentStatus.ACTIVE.value)
            .order_by(Agent.created_at, Agent.id)
            .limit(1)
        )
        return found

    async def _agent_or_principal(self, agent_id: uuid.UUID | None) -> uuid.UUID | None:
        return agent_id if agent_id is not None else await self.principal_agent_id()

    async def list_all(self, *, agent_id: uuid.UUID | None = None) -> Sequence[AgentConfig]:
        """Versions of one agent (the principal when not named), newest first."""
        require_current_tenant()
        agent = await self._agent_or_principal(agent_id)
        if agent is None:
            return []
        stmt = (
            select(AgentConfig)
            .where(AgentConfig.agent_id == agent)
            .order_by(desc(AgentConfig.version))
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get(self, config_id: uuid.UUID) -> AgentConfig | None:
        require_current_tenant()
        return await self._session.get(AgentConfig, config_id)

    async def get_active(self, *, agent_id: uuid.UUID | None = None) -> AgentConfig | None:
        """The active version of one agent (the principal when not named).
        At most one: the database enforces it (``uq_agent_configs_agent_active``)."""
        require_current_tenant()
        agent = await self._agent_or_principal(agent_id)
        if agent is None:
            return None
        stmt = select(AgentConfig).where(
            AgentConfig.agent_id == agent, AgentConfig.status == AgentConfigStatus.ACTIVE
        )
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
        agent_id: uuid.UUID | None = None,
    ) -> AgentConfig:
        """A new draft of ``agent_id`` — or, without one, of the principal
        agent (the database assigns it, creating it the first time).

        ``agent_id`` must be an active agent of THIS tenant (``UnknownAgent``
        otherwise). The admin takes it from the URL; the composite foreign
        key of 0155 refuses another tenant's agent too, this says it first
        and in words."""
        tenant_id = require_current_tenant()
        if agent_id is not None:
            mine = await self._session.scalar(
                select(Agent.id).where(
                    Agent.id == agent_id,
                    Agent.tenant_id == tenant_id,
                    Agent.status == AgentStatus.ACTIVE.value,
                )
            )
            if mine is None:
                raise UnknownAgent(f"agent {agent_id} is not an active agent of this tenant")
        version = await self._next_version()
        config = AgentConfig(
            tenant_id=tenant_id,
            agent_id=agent_id,
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

        # Demote this agent's current active version.
        await self._session.execute(
            update(AgentConfig)
            .where(
                AgentConfig.status == AgentConfigStatus.ACTIVE,
                # Spec 030: only this agent's active version — archiving the
                # tenant's would silence every other agent of the client.
                AgentConfig.agent_id == target.agent_id,
            )
            .values(status=AgentConfigStatus.ARCHIVED)
        )
        # Make the archived row's new state visible before the target turns
        # active: the unique «one active per agent» index checks each UPDATE.
        await self._session.flush()
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
            .where(
                AgentConfig.status == AgentConfigStatus.ACTIVE,
                # Spec 030: only this agent's active version — archiving the
                # tenant's would silence every other agent of the client.
                AgentConfig.agent_id == target.agent_id,
            )
            .values(status=AgentConfigStatus.ARCHIVED)
        )
        # Make the archived row's new state visible before the target turns
        # active: the unique «one active per agent» index checks each UPDATE.
        await self._session.flush()
        target.status = AgentConfigStatus.ACTIVE
        target.promoted_at = datetime.now(UTC)
        target.promoted_by = promoted_by
        await self._session.flush()
        await self._session.refresh(target)
        return target
