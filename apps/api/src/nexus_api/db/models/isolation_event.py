from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import TenantScopedMixin, UUIDPrimaryKey


class IsolationEvent(UUIDPrimaryKey, TenantScopedMixin, Base):
    """Append-only ledger of every ``isolation.*`` counter increment.

    Block H persists each metric bump so the operator panel can render
    last_breach_at + 24h counts from a real source (instead of the
    in-memory ``Counters`` of block B). Immutable — no ``updated_at``;
    the row IS the breach record. RLS-forced.
    """

    __tablename__ = "isolation_events"

    metric: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
