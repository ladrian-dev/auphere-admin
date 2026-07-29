from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Mirror of ``ChannelType`` enum values. Hardcoded here to keep this
# schemas module free of db.models imports (the schemas layer is meant
# to be importable from the admin frontend codegen).
_KNOWN_CHANNELS: frozenset[str] = frozenset(
    {"whatsapp", "instagram", "telegram", "email", "web", "tiktok"}
)


class SkillRef(BaseModel):
    """One entry of ``agent_config.runtime_skills``.

    ``channels`` (optional) gates skill injection to specific channels.
    Empty / unset = the skill loads for every channel (back-compat).
    When set, the runtime injects the skill ONLY when
    ``state.channel_type`` is in the list. This matters because some
    skills (e.g. ``whatsapp-24h-window``, ``whatsapp-native-components``)
    are noise — or actively wrong — in canals like the QA Playground
    web channel.
    """

    skill_id: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=64, default="latest")
    channels: list[str] | None = Field(default=None)

    @field_validator("channels")
    @classmethod
    def _validate_channels(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        unknown = [c for c in value if c not in _KNOWN_CHANNELS]
        if unknown:
            raise ValueError(f"unknown channel(s) {unknown}; allowed: {sorted(_KNOWN_CHANNELS)}")
        return value


class McpServerRef(BaseModel):
    """One entry of ``agent_config.runtime_mcp_servers``."""

    name: str = Field(min_length=1, max_length=64)
    url: str = Field(min_length=1, max_length=512)
    allowed_tools: list[str] = Field(default_factory=list)
    credential_key: str = Field(default="", max_length=128)


class AgentConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    version: int
    status: str
    system_prompt_rendered: str
    channels: list[dict[str, Any]]
    tools: list[str]
    policies: dict[str, Any]
    seed_template_ref: str | None
    kg_schema_id: uuid.UUID | None
    created_by: str | None
    promoted_at: datetime | None
    promoted_by: str | None
    created_at: datetime
    updated_at: datetime
    # Runtime feature flags (migration 0035) — exposed so the admin UI
    # can render the toggle state of an existing config.
    runtime_memory_tool: bool = False
    runtime_outcome_grader: bool = False
    runtime_mcp_connector: bool = False
    runtime_skills: list[SkillRef] | None = None
    runtime_mcp_servers: list[McpServerRef] | None = None


class AgentConfigStageIn(BaseModel):
    """Body for PUT /admin/tenants/:id/agent-config — creates a new staged version."""

    system_prompt_rendered: str = Field(min_length=1, max_length=200_000)
    channels: list[dict[str, Any]] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    policies: dict[str, Any] = Field(default_factory=dict)
    seed_template_ref: str | None = None
    kg_schema_id: uuid.UUID | None = None


class RuntimeCapabilitiesIn(BaseModel):
    """Body for PATCH /admin/tenants/:id/agent-config/:version/runtime.

    Refactor 0035 — all runtime feature flags travel with the agent_config.
    The endpoint refuses to mutate an ACTIVE or ARCHIVED row: capability
    changes are versioned through STAGED → ACTIVE like any other config
    change, so rollback is atomic and the audit trail is preserved.
    """

    runtime_memory_tool: bool
    runtime_outcome_grader: bool
    runtime_mcp_connector: bool
    runtime_skills: list[SkillRef] = Field(default_factory=list)
    runtime_mcp_servers: list[McpServerRef] = Field(default_factory=list)


class AvailableSkillOut(BaseModel):
    """One entry returned by GET /admin/skills/available.

    Combines the local SKILL.md frontmatter (name, description) with the
    ``uploaded.json`` manifest (skill_id, latest version). A skill that
    has not been uploaded yet returns ``skill_id=None`` — the UI can
    show it as "needs upload first".
    """

    name: str
    description: str
    local_version: str
    skill_id: str | None = None
    uploaded_version: str | None = None


class AgentConfigBundle(BaseModel):
    """Active version + all versions, in one payload — what the panel needs to render."""

    active: AgentConfigOut | None
    versions: list[AgentConfigOut]
