"""Schemas of lane ``agent-tools`` (CP-11 · CP-13 · CP-14 · CP-15 · CP-31).

Same two rules as ``schemas.py`` (no internal tenant ids, no message
bodies). Field names avoid the forbidden set of
``tests/isolation/test_console_scope.py`` (``content``, ``text``, ``body``,
``notes``, ``reason``…) — extracted knowledge text is NEVER an output.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from nexus_api.services.agent_console_policy import ConsolePolicy

# ── CP-11 · structured agent settings ──────────────────────────────────


class AgentSettingsOut(BaseModel):
    """``policies.console`` of a version + where it lives. ``version`` is
    the STAGED draft when one exists (what a PUT edits), else the active
    version, else ``None`` (no agent yet)."""

    version: int | None
    version_status: Literal["staged", "active", "archived"] | None
    active_version: int | None
    has_draft: bool
    settings: ConsolePolicy


class AgentSettingsIn(BaseModel):
    """Full replacement of ``policies.console`` on the draft."""

    model_config = ConfigDict(extra="forbid")

    settings: ConsolePolicy


class AgentSettingsSaved(AgentSettingsOut):
    draft_created: bool


# ── CP-13 · tools + connectors ─────────────────────────────────────────

ToolMode = Literal["always", "blocked", "needs_approval"]


class ToolOut(BaseModel):
    name: str
    description: str
    capability_tags: list[str] = Field(default_factory=list)
    read_only: bool
    destructive: bool
    status: str
    enabled: bool = Field(description="In the whitelist of the version being edited.")
    enabled_in_active: bool
    connector_slug: str | None
    connector_display_name: str | None
    connector_status: str | None = Field(
        default=None, description="tenant_connectors.status or null when not installed."
    )
    connector_required: bool
    usable: bool = Field(description="Enabled AND (no connector or connector connected).")
    default_mode: ToolMode
    override_mode: ToolMode | None
    effective_mode: ToolMode


class ToolCatalogOut(BaseModel):
    version: int | None
    version_status: Literal["staged", "active", "archived"] | None
    active_version: int | None
    has_draft: bool
    tools: list[ToolOut]


class ToolsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tools: list[str] = Field(max_length=200)


class ToolsSaved(ToolCatalogOut):
    draft_created: bool


class ToolModeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: ToolMode


class ToolModeOut(BaseModel):
    tool_name: str
    mode: ToolMode
    set_by: str
    updated_at: datetime


class ConnectorOut(BaseModel):
    """A connector as the partner sees it. Never ``credentials_ref``,
    never a consent token."""

    slug: str
    display_name: str
    vendor: str
    category: str
    auth_kind: str
    logo_url: str | None
    capabilities: list[str] = Field(default_factory=list)
    installed: bool
    status: str | None = None
    scopes_granted: list[str] = Field(default_factory=list)
    connected_at: datetime | None = None
    last_synced_at: datetime | None = None
    last_health_check_at: datetime | None = None
    consent_expires_at: datetime | None = None
    credentials_form: list[dict[str, Any]] = Field(
        default_factory=list, description="For auth_kind=api_key: fields the UI renders."
    )
    tools_total: int
    tools_enabled: int


class ConsentOut(BaseModel):
    """Returned ONCE to the caller that asked. Not persisted server-side in
    clear; not listed anywhere else."""

    slug: str
    signed_consent_url: str
    expires_at: datetime


class ConnectorSyncOut(BaseModel):
    slug: str
    added: list[str]
    deprecated: list[str]
    unchanged_count: int


class ConnectApiKeyIn(BaseModel):
    """``secrets`` are input-only: encrypted into ``tenant_credentials``,
    never echoed."""

    model_config = ConfigDict(extra="forbid")

    secrets: dict[str, str] = Field(min_length=1, max_length=20)
    endpoint_meta: dict[str, Any] = Field(default_factory=dict, max_length=20)


# ── CP-14 · vertical skills ────────────────────────────────────────────


class SkillOut(BaseModel):
    name: str
    description: str = Field(description="What the skill adds — the preview.")
    version: str
    activatable: bool
    enabled: bool
    enabled_in_active: bool


class SkillsOut(BaseModel):
    version: int | None
    version_status: Literal["staged", "active", "archived"] | None
    active_version: int | None
    has_draft: bool
    skills: list[SkillOut]


class SkillsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skills: list[str] = Field(max_length=50, description="Skill names to enable.")


class SkillsSaved(SkillsOut):
    draft_created: bool


# ── CP-15 · knowledge ──────────────────────────────────────────────────

KnowledgeKind = Literal["file", "url"]
KnowledgeStatus = Literal["pending", "indexed", "failed"]
KnowledgeErrorCodeLit = Literal["fetch_failed", "unsupported_type", "too_large", "empty"]


class KnowledgeDocumentOut(BaseModel):
    """Metadata only. The extracted text is NOT here and never will be."""

    id: uuid.UUID
    kind: KnowledgeKind
    title: str
    source_url: str | None
    mime: str
    size_bytes: int
    status: KnowledgeStatus
    error_code: KnowledgeErrorCodeLit | None
    chunk_count: int
    created_by: str | None
    created_at: datetime
    updated_at: datetime
    indexed_at: datetime | None


class KnowledgeListOut(BaseModel):
    items: list[KnowledgeDocumentOut]
    total: int
    indexed_chars: int = Field(description="Sum of extracted characters over indexed docs.")
    prompt_char_cap: int = Field(description="What the runtime injects at most.")


class KnowledgeUrlIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=8, max_length=2048, pattern=r"^https?://")
    title: str | None = Field(default=None, max_length=255)


__all__ = [
    "AgentSettingsIn",
    "AgentSettingsOut",
    "AgentSettingsSaved",
    "ConnectApiKeyIn",
    "ConnectorOut",
    "ConnectorSyncOut",
    "ConsentOut",
    "KnowledgeDocumentOut",
    "KnowledgeListOut",
    "KnowledgeUrlIn",
    "SkillOut",
    "SkillsIn",
    "SkillsOut",
    "SkillsSaved",
    "ToolCatalogOut",
    "ToolModeIn",
    "ToolModeOut",
    "ToolOut",
    "ToolsIn",
    "ToolsSaved",
]
