from __future__ import annotations

import decimal
import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    FetchedValue,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._enum import pg_enum
from nexus_api.db.models._mixins import TenantScopedMixin, TimestampMixin, UUIDPrimaryKey


class AgentConfigStatus(str, enum.Enum):
    STAGED = "staged"
    ACTIVE = "active"
    ARCHIVED = "archived"


class AgentStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


#: The name the backfill and the default-agent trigger give the first agent.
PRINCIPAL_AGENT_NAME = "Agente principal"


class Agent(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    """One agent of a client (spec 030, iteration 3). A client may have several;
    each WhatsApp number answers with one (``channels.agent_id``) and each
    agent has its own versions in ``agent_configs``.

    The *principal* agent is the oldest active one — not a column. It answers
    on numbers without an agent and it is what every caller that does not name
    an agent (the Companion, the admin, the crons) acts on. Deleting does not
    exist (constitution §IV): an agent is archived.
    """

    __tablename__ = "agents"

    name: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AgentStatus.ACTIVE.value
    )
    # Spec 047 (migración 0178): the revision of the agent's one draft, for
    # ``If-Match``. A stale write answers 412 with what the other person changed.
    draft_revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # Spec 047 (migración 0183): the services this agent offers. ``True`` =
    # every service «Para todos los agentes»; ``False`` = only its
    # ``agent_services`` rows (requisito 11.2, garantía 9).
    serves_all_services: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    # Spec 047 (migración 0190): the agent's life — ``draft``, ``published``,
    # ``paused`` (with its reason) or ``archived`` — and what resuming returns.
    lifecycle: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", server_default="draft"
    )
    pause_reason: Mapped[str | None] = mapped_column(String(16), nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_by_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    paused_by_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    paused_origin: Mapped[str | None] = mapped_column(String(16), nullable=True)
    before_pause: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    #: Exactly one per client among the non-archived (requisito 26.2).
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    is_reception: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    #: The monthly cap, in the currency of the client's bag (requisito 44.1).
    monthly_cap_micros: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class AgentConfig(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    """Versioned configuration for a tenant's agent.

    Each PUT creates a new row with status=staged. Promote flips one row to active
    and the previous active to archived. Rollback re-promotes a previously archived
    version. UNIQUE(tenant_id, version) enforces strict monotonic versioning.
    """

    __tablename__ = "agent_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "version", name="uq_agent_configs_tenant_version"),
    )
    # ``agent_id`` may be filled by the database (the default-agent trigger,
    # 0153): fetch it back on INSERT instead of lazily on first access, which
    # would be an implicit IO in async code.
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012 - SQLAlchemy reads it as a class attribute

    # Spec 030: whose version this is. Required in the database; a row
    # inserted without one lands on the tenant's principal agent (trigger).
    # The database key is ``(tenant_id, agent_id)`` (0155): never another
    # client's agent.
    # Version numbers stay unique per tenant (data-model.md, decision).
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        server_default=FetchedValue(),
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    # Spec 047 (migración 0178): «v{n} de {agente}», numbered per agent. The
    # database fills it on INSERT (trigger); ``version`` stays per client.
    agent_version_number: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=FetchedValue()
    )
    #: The version this draft started from (composite FK, same client).
    base_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[AgentConfigStatus] = mapped_column(
        pg_enum(AgentConfigStatus, name="agent_config_status"),
        nullable=False,
        default=AgentConfigStatus.STAGED,
        index=True,
    )

    system_prompt_rendered: Mapped[str] = mapped_column(Text, nullable=False)
    channels: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    tools: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    policies: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    seed_template_ref: Mapped[str | None] = mapped_column(String(80), nullable=True)

    kg_schema_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("kg_schemas.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    promoted_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Fase D — Anthropic Skills attached to this config. Shape: list of
    # ``{"skill_id": str, "version": str | "latest"}``. NULL = no skills,
    # the runtime then skips the ``container`` arg + code_execution tool.
    runtime_skills: Mapped[list[dict[str, str]] | None] = mapped_column(JSONB, nullable=True)

    # Fase E — Anthropic MCP connector servers attached to this config.
    # Shape: list of ``{name, url, allowed_tools[], credential_key}``.
    # NULL = "no MCP servers", the runtime skips ``mcp_servers`` +
    # ``mcp-client-2025-11-20`` beta header entirely.
    runtime_mcp_servers: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)

    # Runtime feature flags (migration 0035). These travel with the
    # config through the STAGED → ACTIVE flow — activating a feature
    # for a tenant is a config promotion, not an env var edit. Default
    # ``false`` on every existing row keeps pre-Fase-B/C/E behaviour for
    # any tenant whose active config predates the runtime features.
    runtime_memory_tool: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    runtime_outcome_grader: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # WP-21 — CUÁNDO corre el grader, cuando está activo. ``sync`` en
    # todos los turnos (lo de antes), ``off`` en ninguno, ``sampled`` solo
    # en los de riesgo (reserva, escalado, herramienta que escribe) más
    # una muestra del resto; los no muestreados se gradúan después, fuera
    # del camino crítico, y su veredicto no reescribe la respuesta.
    grader_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="sampled", server_default="sampled"
    )
    grader_sample_rate: Mapped[decimal.Decimal] = mapped_column(
        Numeric(4, 3), nullable=False, default=decimal.Decimal("0.100"), server_default="0.100"
    )
    # The mcp_connector boolean is the kill switch for the entire
    # MCP-connector module. ``runtime_mcp_servers`` lists WHICH servers
    # to attach; this flag toggles whether the module runs at all. Both
    # have to be true (and the server list non-empty) for the runtime
    # to actually call MCP — defence in depth.
    runtime_mcp_connector: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Spec 047 (migración 0187): the version's AgentSpec v1 (requisito 16.1),
    # the gate's verdict, the owner/admin reason to skip it, and the undo window.
    spec: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    gate: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    undo_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentService(Base):
    """Spec 047 (0183): which services an agent offers when it does not serve
    them all (``Agent.serves_all_services``; requisito 11.4, garantía 9)."""

    __tablename__ = "agent_services"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "agent_id"],
            ["agents.tenant_id", "agents.id"],
            name="fk_agent_services_agent",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "service_id"],
            ["reservation_services.tenant_id", "reservation_services.id"],
            name="fk_agent_services_service",
            ondelete="CASCADE",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    service_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)


class AgentVersionCompilation(UUIDPrimaryKey, Base):
    """Spec 047 (0183, research D4): the history of compilations — which prompt
    answered each turn, by its ``sha256``. The runtime does not read it: it reads
    ``AgentConfig.system_prompt_rendered``, which each new compilation of the
    active version rewrites in the same transaction."""

    __tablename__ = "agent_version_compilations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_agent_version_compilations_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "agent_config_id"],
            ["agent_configs.tenant_id", "agent_configs.id"],
            name="fk_agent_version_compilations_version",
            ondelete="CASCADE",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_config_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    business_rev: Mapped[int] = mapped_column(BigInteger, nullable=False)
    knowledge_rev: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    tools_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    family_variant: Mapped[str | None] = mapped_column(String(40), nullable=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
