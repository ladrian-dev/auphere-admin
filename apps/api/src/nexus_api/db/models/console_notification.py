"""In-app notifications of the partner console (migration 0086 —
PLAN-CONSOLE-V1 CP-29 notification centre, CP-24 usage alerts).

PLATFORM table (not tenant-scoped, no RLS — same trust model as
``partners``): a notification belongs to a partner, optionally to one
member (``recipient_user_id`` = Better Auth user id, text, no FK — see
``partner_membership.py`` for why) and optionally refers to a client by
``external_client_ref`` — the partner's own identifier. No internal
``tenant_id`` is stored: this is a partner table (no per-tenant RLS, no
FK to ``tenants``), so the structural suites ``test_21``/``test_22`` do
not apply to it, and the API never has to translate ids.

``kind`` is a closed vocabulary (:class:`NotificationKind`) and the UI
renders it from ``payload`` in the viewer's language: no localized text is
stored, and — decision C8 — no customer message content ever goes into
``payload``.

``dedupe_key`` (unique, nullable) makes emitters idempotent
("partner:<id>:usage:80:2026-08"). Read state: ``read_at`` when the row is
addressed to one member; ``console_notification_reads`` (per user) when it
is addressed to everyone.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base


class NotificationKind(str, enum.Enum):
    """Closed vocabulary — extend here, render in the console's i18n."""

    USAGE_THRESHOLD = "usage.threshold"  # payload: {percent, cap, used, period}
    USAGE_CAP_REACHED = "usage.cap_reached"  # payload: {cap, used, period}
    QA_CAP_REACHED = "qa.cap_reached"  # payload: {period}
    CLIENT_ACTIVATED = "client.activated"  # payload: {external_client_ref}
    CHANNEL_DEGRADED = "channel.degraded"  # payload: {external_client_ref, channel_status}
    TEMPLATE_REJECTED = "template.rejected"  # payload: {external_client_ref, template_name}
    MEMBER_JOINED = "member.joined"  # payload: {email, role}
    ONBOARDING_STEP = "onboarding.step"  # payload: {step}


class NotificationSeverity(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ConsoleNotification(Base):
    __tablename__ = "console_notifications"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name="ck_console_notifications_severity",
        ),
        Index(
            "uq_console_notifications_dedupe",
            "dedupe_key",
            unique=True,
            postgresql_where=text("dedupe_key IS NOT NULL"),
        ),
        Index("ix_console_notifications_partner_created", "partner_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("partners.id", ondelete="CASCADE"), nullable=False
    )
    recipient_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_client_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    kind: Mapped[str] = mapped_column(String(60), nullable=False)
    severity: Mapped[str] = mapped_column(
        String(10), nullable=False, default="info", server_default="info"
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    dedupe_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class ConsoleNotificationRead(Base):
    __tablename__ = "console_notification_reads"

    notification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("console_notifications.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


__all__ = [
    "ConsoleNotification",
    "ConsoleNotificationRead",
    "NotificationKind",
    "NotificationSeverity",
]
