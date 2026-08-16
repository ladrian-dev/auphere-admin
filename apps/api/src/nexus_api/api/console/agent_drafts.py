"""Draft handling shared by the agent lanes of the console (CP-11/13/14).

The console never edits an ACTIVE version in place: every structured
editor (settings, tools, skills) writes onto ONE staged draft — created
on first write as a full copy of the active version (prompt, channels,
tools, policies, runtime capabilities), reused on subsequent writes —
and publishing (CP-12) is what makes it live. That keeps the partner's
mental model at "edit → one draft → publish", and the runtime's
guarantees (one ACTIVE, atomic rollback, audit rows) untouched.

"The draft" = the newest STAGED version that is newer than the active
one (or the newest STAGED at all when nothing is active). Older staged
versions are leftovers of previous edits and are ignored.
"""

from __future__ import annotations

from dataclasses import dataclass

from nexus_api.db.models import AgentConfig, AgentConfigStatus
from nexus_api.services.agent_config_service import AgentConfigService
from nexus_api.services.agent_console_policy import with_disclosure_default

from .deps import ClientScope


@dataclass(frozen=True)
class DraftView:
    """What the editors show: the version being edited + the active one."""

    target: AgentConfig | None
    active: AgentConfig | None
    draft: AgentConfig | None

    @property
    def has_draft(self) -> bool:
        return self.draft is not None


async def load_view(scope: ClientScope) -> DraftView:
    service = AgentConfigService(scope.session)
    versions = await service.list_versions()  # newest first
    active = next((v for v in versions if v.status is AgentConfigStatus.ACTIVE), None)
    draft = _current_draft(versions, active)
    return DraftView(target=draft or active, active=active, draft=draft)


def _current_draft(versions: list[AgentConfig], active: AgentConfig | None) -> AgentConfig | None:
    for v in versions:
        if v.status is not AgentConfigStatus.STAGED:
            continue
        if active is None or v.version > active.version:
            return v
    return None


def copy_runtime_fields(src: AgentConfig | None, dst: AgentConfig) -> None:
    """Fields ``AgentConfigRepository.create_staged`` does not take: the
    runtime capabilities. Copied so a console draft never silently drops
    skills / memory / grader / MCP wiring the backoffice turned on."""
    if src is None:
        return
    dst.runtime_skills = list(src.runtime_skills) if src.runtime_skills else None
    dst.runtime_mcp_servers = list(src.runtime_mcp_servers) if src.runtime_mcp_servers else None
    dst.runtime_memory_tool = src.runtime_memory_tool
    dst.runtime_outcome_grader = src.runtime_outcome_grader
    dst.runtime_mcp_connector = src.runtime_mcp_connector
    dst.grader_mode = src.grader_mode
    dst.grader_sample_rate = src.grader_sample_rate


async def ensure_draft(scope: ClientScope) -> tuple[AgentConfig, bool]:
    """Return ``(draft, created)``. Stages a copy of the active version
    (or an empty scaffold when there is none) if no current draft exists.
    Raises ``AgentConfigConflict`` only if the copied tool list is invalid
    (cannot happen for a copy of a promoted version)."""
    view = await load_view(scope)
    if view.draft is not None:
        return view.draft, False
    service = AgentConfigService(scope.session)
    base = view.active
    actor = scope.principal.actor
    cfg = await service.stage_new_version(
        actor=actor,
        system_prompt_rendered=base.system_prompt_rendered if base else "",
        channels=list(base.channels) if base else [],
        tools=list(base.tools) if base else [],
        policies=with_disclosure_default(dict(base.policies) if base else {}, actor=actor),
        seed_template_ref=base.seed_template_ref if base else None,
        kg_schema_id=base.kg_schema_id if base else None,
    )
    copy_runtime_fields(base, cfg)
    await scope.session.flush()
    return cfg, True


__all__ = ["DraftView", "copy_runtime_fields", "ensure_draft", "load_view"]
