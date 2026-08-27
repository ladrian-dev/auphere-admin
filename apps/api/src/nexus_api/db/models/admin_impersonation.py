"""Admin F5 impersonation sessions. Admin-only FORCE RLS via ``app.is_admin``.

Not a partner session: no partner JWT, no console cookie. Rows are keyed
by operator principal + partner and are invisible to ``nexus_app`` unless
``app.is_admin`` is set.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import UUIDPrimaryKey
from nexus_api.db.models.operator_identity import OPERATOR_AUTH_SCHEMA

TTL_MIN_SECONDS = 60
TTL_MAX_SECONDS = 3600
TTL_DEFAULT_SECONDS = 900
REASON_MIN_LEN = 8


class AdminImpersonationSession(UUIDPrimaryKey, Base):
    __tablename__ = "admin_impersonation_sessions"
    __table_args__ = (
        CheckConstraint(
            f"char_length(reason) >= {REASON_MIN_LEN}",
            name="ck_admin_impersonation_reason_len",
        ),
        CheckConstraint(
            f"ttl_seconds BETWEEN {TTL_MIN_SECONDS} AND {TTL_MAX_SECONDS}",
            name="ck_admin_impersonation_ttl",
        ),
    )

    operator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            f"{OPERATOR_AUTH_SCHEMA}.principals.id",
            ondelete="CASCADE",
            name="fk_admin_impersonation_operator",
        ),
        nullable=False,
        index=True,
    )
    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("partners.id", ondelete="CASCADE", name="fk_admin_impersonation_partner"),
        nullable=False,
        index=True,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    ttl_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=TTL_DEFAULT_SECONDS)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


__all__ = [
    "REASON_MIN_LEN",
    "TTL_DEFAULT_SECONDS",
    "TTL_MAX_SECONDS",
    "TTL_MIN_SECONDS",
    "AdminImpersonationSession",
]
