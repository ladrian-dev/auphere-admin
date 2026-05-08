from __future__ import annotations

import enum
from typing import Any

from sqlalchemy import ARRAY, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._enum import pg_enum
from nexus_api.db.models._mixins import TimestampMixin, UUIDPrimaryKey


class ToolStatus(str, enum.Enum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    EXPERIMENTAL = "experimental"


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
