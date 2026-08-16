"""Console principals — who, inside a partner, may use the partner console
(migration 0080, PLAN-CONSOLE-V1 CP-02).

Two PLATFORM tables (not tenant-scoped, no RLS — same trust model as
``partners``):

- ``partner_memberships`` — the ``user ↔ partner`` relation with a named
  role. ``user_id`` is the console's Better Auth user id (text, lives in
  the ``console_auth`` Postgres schema that Drizzle owns). There is
  deliberately NO foreign key across the two toolchains: Alembic never
  touches ``console_auth.*`` and Drizzle never touches ``public.*``. The
  join is by value and documented here. ``email``/``display_name`` are a
  snapshot for display and audit, because the backend has no grant on the
  auth schema.
- ``partner_invitations`` — pending invitations, expiring 21 days after
  creation (Anthropic's number; copied on purpose). The invitation token
  is stored as SHA-256 only and shown once.

Roles are NAMED after jobs, not permissions (research §3.1.2): the
permission map that turns a role into capabilities lives in
``core/console_auth.py``. Five roles cover v1; a finer grid can be added
without touching this table.

Invariant enforced by ``repositories/partner_membership.py`` (and by the
409 the console returns): a partner can never be left without an active
``owner``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timedelta

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import TimestampMixin, UUIDPrimaryKey


class PartnerRole(str, enum.Enum):
    """The five console roles (PLAN-CONSOLE-V1 §3)."""

    OWNER = "owner"
    ADMIN = "admin"
    BUILDER = "builder"
    ANALYST = "analyst"
    BILLING = "billing"


PARTNER_ROLES: tuple[str, ...] = tuple(r.value for r in PartnerRole)


class MembershipStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class InvitationStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"
    EXPIRED = "expired"


#: How long an invitation link stays valid.
INVITATION_TTL = timedelta(days=21)

_ROLE_SQL = "('owner', 'admin', 'builder', 'analyst', 'billing')"


class PartnerMembership(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "partner_memberships"
    __table_args__ = (
        CheckConstraint(f"role IN {_ROLE_SQL}", name="ck_partner_memberships_role"),
        CheckConstraint(
            "status IN ('active', 'suspended')",
            name="ck_partner_memberships_status",
        ),
        # v1: a user belongs to exactly one partner. Support access to
        # other partners is impersonation (CP-39), never a second row.
        Index("uq_partner_memberships_user", "user_id", unique=True),
        Index("ix_partner_memberships_partner", "partner_id"),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("partners.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Better Auth user id (``console_auth.user.id``). Text by value — see
    # module docstring for why there is no FK.
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=MembershipStatus.ACTIVE.value,
        server_default="active",
    )
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("partner_memberships.id", ondelete="SET NULL"),
        nullable=True,
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<PartnerMembership {self.email} {self.role}@{self.partner_id}>"


class PartnerInvitation(UUIDPrimaryKey, Base):
    __tablename__ = "partner_invitations"
    __table_args__ = (
        CheckConstraint(f"role IN {_ROLE_SQL}", name="ck_partner_invitations_role"),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'revoked', 'expired')",
            name="ck_partner_invitations_status",
        ),
        # One live invitation per e-mail per partner. Re-inviting means
        # revoking first (or letting the previous one expire).
        Index(
            "uq_partner_invitations_pending_email",
            "partner_id",
            "email",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_partner_invitations_partner", "partner_id"),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("partners.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Always stored lower-cased; compared lower-cased on accept.
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    # SHA-256 hex of the plaintext token. UNIQUE → O(1) lookup on accept.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("partner_memberships.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=InvitationStatus.PENDING.value,
        server_default="pending",
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_membership_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("partner_memberships.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<PartnerInvitation {self.email} {self.role} {self.status}>"
