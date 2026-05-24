from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import TimestampMixin, UUIDPrimaryKey


class AuditLog(UUIDPrimaryKey, TimestampMixin, Base):
    """Append-only operational audit log. Every mutation should write a row.

    ``actor`` is the operator (e.g. an admin user) when an admin endpoint
    is called, or ``system:<component>`` for runtime-driven actions.

    ``tenant_id`` is **nullable** (migration 0039) so platform-level
    actions (creating an Auphere channel, publishing a global skill,
    feature flags) can be audited without faking a tenant uuid.
    Tenant-scoped queries via ``tenant_scoped_session`` only see rows
    where ``tenant_id = app.tenant_id`` — NULL rows are returned only
    by direct (unscoped) sessions, matching the platform-audit
    surface pattern.
    """

    __tablename__ = "audit_log"

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    target: Mapped[str] = mapped_column(String(255), nullable=False)
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
