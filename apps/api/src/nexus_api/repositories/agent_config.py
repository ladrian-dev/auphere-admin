"""AgentConfig repository — versioned. Tenant scope enforced by RLS via
`SET LOCAL app.tenant_id`. Methods do NOT accept tenant_id; the active session
must already be tenant-scoped (architecture/agent-isolation.md tabla "Capas").

Spec 030 (iteration 3): a client may have several agents, each with its own
active version. Every method takes an optional ``agent_id``; without one it
acts on the **principal agent** (the oldest active one), which is what a
single-agent client — every client before spec 030 — always meant. Version
numbers stay unique per tenant, so ``get_by_version`` needs no agent.

Spec 047 (requisito 3): an agent has **at most one draft** — the database
says so (``uq_agent_configs_one_draft``, 0178) and :meth:`create_staged`
says it first, in words. ``agents.draft_revision`` is the draft's revision
for ``If-Match``: :meth:`lock_draft_revision` queues the writers of one
agent and :meth:`bump_draft_revision` moves it. The service decides when.
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

    async def agent_or_principal(self, agent_id: uuid.UUID | None) -> uuid.UUID | None:
        """``agent_id``, or the principal agent when it is ``None``."""
        require_current_tenant()
        return await self._agent_or_principal(agent_id)

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

    # ── spec 047: the one draft ─────────────────────────────────────────

    async def get_draft(self, *, agent_id: uuid.UUID | None = None) -> AgentConfig | None:
        """The agent's one draft (the principal's when not named), or ``None``."""
        require_current_tenant()
        agent = await self._agent_or_principal(agent_id)
        if agent is None:
            return None
        found: AgentConfig | None = await self._session.scalar(
            select(AgentConfig).where(
                AgentConfig.agent_id == agent, AgentConfig.status == AgentConfigStatus.STAGED
            )
        )
        return found

    async def latest_saved(self, *, agent_id: uuid.UUID) -> AgentConfig | None:
        """The newest version of the agent that was ever published.

        Where a draft starts when the agent has nothing active (R3.2). A
        discarded draft was never saved: it is archived with no
        ``promoted_at`` and does not count."""
        require_current_tenant()
        found: AgentConfig | None = await self._session.scalar(
            select(AgentConfig)
            .where(
                AgentConfig.agent_id == agent_id,
                AgentConfig.status != AgentConfigStatus.STAGED,
                AgentConfig.promoted_at.is_not(None),
            )
            .order_by(desc(AgentConfig.version))
            .limit(1)
        )
        return found

    async def draft_base(self, *, agent_id: uuid.UUID | None) -> AgentConfig | None:
        """What a new draft of ``agent_id`` copies: the active version, or the
        last saved one when nothing is active (R3.2)."""
        if agent_id is None:
            return None
        active = await self.get_active(agent_id=agent_id)
        return active if active is not None else await self.latest_saved(agent_id=agent_id)

    async def draft_revision(self, agent_id: uuid.UUID) -> int | None:
        """``agents.draft_revision``, or ``None`` when the agent is not here."""
        require_current_tenant()
        found: int | None = await self._session.scalar(
            select(Agent.draft_revision).where(Agent.id == agent_id)
        )
        return found

    async def lock_draft_revision(self, agent_id: uuid.UUID) -> int | None:
        """The draft's revision, with the agent row locked until the end of the
        transaction (``FOR UPDATE``). Two writers of one agent queue here and
        the second reads the revision the first left. ``None``: no such agent."""
        require_current_tenant()
        found: int | None = await self._session.scalar(
            select(Agent.draft_revision).where(Agent.id == agent_id).with_for_update()
        )
        return found

    async def bump_draft_revision(self, agent_id: uuid.UUID) -> int:
        """One more revision of the agent's draft; returns the new number."""
        require_current_tenant()
        bumped: int | None = await self._session.scalar(
            update(Agent)
            .where(Agent.id == agent_id)
            .values(draft_revision=Agent.draft_revision + 1)
            .returning(Agent.draft_revision)
            .execution_options(synchronize_session=False)
        )
        if bumped is None:
            raise UnknownAgent(f"agent {agent_id} is not an agent of this tenant")
        return bumped

    async def archive_draft(self, draft: AgentConfig) -> AgentConfig:
        """Discard a draft: archived, never deleted (§IV). It keeps no
        ``promoted_at``, so the history can tell it was never published."""
        require_current_tenant()
        if draft.status is not AgentConfigStatus.STAGED:
            raise AgentConfigConflict(f"version {draft.version} is not a draft")
        draft.status = AgentConfigStatus.ARCHIVED
        await self._session.flush()
        return draft

    async def publish_copy(
        self, source: AgentConfig, *, policies: dict[str, Any], published_by: str | None
    ) -> AgentConfig:
        """A new ACTIVE version of ``source``'s agent, equal to ``source`` but
        for ``policies``, without going through the draft.

        For a change that applies at once and must not publish — nor wait
        for, nor overwrite — a draft someone has pending (the admins set from
        the partner API). The current active is archived first, as a
        promotion does."""
        tenant_id = require_current_tenant()
        await self._session.execute(
            update(AgentConfig)
            .where(
                AgentConfig.status == AgentConfigStatus.ACTIVE,
                AgentConfig.agent_id == source.agent_id,
            )
            .values(status=AgentConfigStatus.ARCHIVED)
        )
        # The unique «one active per agent» index checks each statement.
        await self._session.flush()
        now = datetime.now(UTC)
        config = AgentConfig(
            tenant_id=tenant_id,
            agent_id=source.agent_id,
            version=await self._next_version(),
            status=AgentConfigStatus.ACTIVE,
            base_version_id=source.id,
            system_prompt_rendered=source.system_prompt_rendered,
            channels=list(source.channels or []),
            tools=list(source.tools or []),
            policies=policies,
            seed_template_ref=source.seed_template_ref,
            kg_schema_id=source.kg_schema_id,
            created_by=published_by,
            promoted_at=now,
            promoted_by=published_by,
        )
        copy_runtime_fields(source, config)
        self._session.add(config)
        await self._session.flush()
        await self._session.refresh(config)
        return config

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
        note: str | None = None,
    ) -> AgentConfig:
        """A new draft of ``agent_id`` — or, without one, of the principal
        agent (the database assigns it, creating it the first time).

        ``agent_id`` must be an active agent of THIS tenant (``UnknownAgent``
        otherwise). The admin takes it from the URL; the composite foreign
        key of 0155 refuses another tenant's agent too, this says it first
        and in words.

        Spec 047: an agent that already has a draft gets
        ``AgentConfigConflict`` (R3.1) — writing into that draft is the
        service's job (``AgentConfigService.stage_new_version``). The new
        draft starts from the active version or the last saved one (R3.2):
        it records it (``base_version_id``) and copies its runtime
        capabilities, which no caller passes."""
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
        agent = await self._agent_or_principal(agent_id)
        existing = await self.get_draft(agent_id=agent) if agent is not None else None
        if existing is not None:
            raise AgentConfigConflict(
                f"agent {agent} already has a draft (version {existing.version})"
            )
        base = await self.draft_base(agent_id=agent)
        version = await self._next_version()
        config = AgentConfig(
            tenant_id=tenant_id,
            # ``None`` only when the client has no agent yet: the database
            # creates the principal one (0153).
            agent_id=agent,
            version=version,
            status=AgentConfigStatus.STAGED,
            base_version_id=base.id if base is not None else None,
            note=note,
            system_prompt_rendered=system_prompt_rendered,
            channels=channels,
            tools=tools,
            policies=policies,
            seed_template_ref=seed_template_ref,
            kg_schema_id=kg_schema_id,
            created_by=created_by,
        )
        copy_runtime_fields(base, config)
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


def copy_runtime_fields(src: AgentConfig | None, dst: AgentConfig) -> None:
    """The runtime capabilities of ``src`` onto ``dst`` — skills, memory,
    grader, MCP wiring. They are part of a version's identity and no caller
    of ``create_staged`` passes them: a draft that dropped them would switch
    them off at the next publish without anyone deciding it."""
    if src is None:
        return
    dst.runtime_skills = [dict(s) for s in src.runtime_skills] if src.runtime_skills else None
    dst.runtime_mcp_servers = (
        [dict(s) for s in src.runtime_mcp_servers] if src.runtime_mcp_servers else None
    )
    dst.runtime_memory_tool = src.runtime_memory_tool
    dst.runtime_outcome_grader = src.runtime_outcome_grader
    dst.runtime_mcp_connector = src.runtime_mcp_connector
    dst.grader_mode = src.grader_mode
    dst.grader_sample_rate = src.grader_sample_rate
