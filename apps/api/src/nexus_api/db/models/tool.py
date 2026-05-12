from __future__ import annotations

import enum
import uuid
from typing import Any

from sqlalchemy import ARRAY, Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._enum import pg_enum
from nexus_api.db.models._mixins import TimestampMixin, UUIDPrimaryKey


class ToolStatus(str, enum.Enum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    EXPERIMENTAL = "experimental"
    # ``internal`` tools no aparecen en MCPRegistry.dispatch (LLM-facing) ni
    # se whitelistean en agent_config.tools. Solo invocables vía
    # MCPRegistry.dispatch_internal desde otros servers (ver Bloque E).
    INTERNAL = "internal"


class ToolCatalog(UUIDPrimaryKey, TimestampMixin, Base):
    """Global catalog of tools. Not tenant-scoped — agents reference tools via whitelist."""

    __tablename__ = "tool_catalog"

    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    mcp_server: Mapped[str] = mapped_column(String(80), nullable=False)
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    output_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    side_effects: Mapped[list[str]] = mapped_column(ARRAY(String(40)), nullable=False, default=list)
    capability_tags: Mapped[list[str]] = mapped_column(
        ARRAY(String(40)), nullable=False, default=list
    )
    cost_estimate: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[ToolStatus] = mapped_column(
        pg_enum(ToolStatus, name="tool_status"),
        nullable=False,
        default=ToolStatus.ACTIVE,
    )
    # Block L additions — see migration 0013 + connector model + ADR-011.
    connector_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("connectors.id", ondelete="SET NULL"),
        nullable=True,
    )
    read_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    destructive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # default_mode in {"always", "blocked", "needs_approval"}. The runtime
    # gating in Phase 1 only honors always vs blocked; needs_approval is
    # treated as blocked + dedicated counter. See connector.py for the
    # ConnectorToolMode enum and resolver.
    default_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="always")
