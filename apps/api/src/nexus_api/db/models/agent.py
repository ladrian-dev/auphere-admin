from __future__ import annotations

import decimal
import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    FetchedValue,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
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
