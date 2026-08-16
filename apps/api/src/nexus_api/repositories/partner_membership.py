"""Repositories for console principals — ``partner_memberships`` and
``partner_invitations`` (migration 0080, PLAN-CONSOLE-V1 CP-02).

Platform tables, no RLS. Every method takes the partner id explicitly and
every query is bounded by it: there is no call here that can list or
mutate another partner's people. The two exceptions are deliberate and
documented: ``get_by_user`` (the BFF resolves *which* partner a session
belongs to — that is the whole point of the table) and
``get_pending_by_token`` (an invitation link is anonymous until accepted).

The one invariant that cannot live in the schema is enforced here: **a
partner is never left without an active owner.** ``change_role`` and
``remove`` lock the partner's owner rows with ``SELECT … FOR UPDATE``
before deciding, so two concurrent demotions cannot both see "there is
another owner" and both go through.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import (
    INVITATION_TTL,
    InvitationStatus,
    MembershipStatus,
    PartnerInvitation,
    PartnerMembership,
    PartnerRole,
)


class LastOwnerError(Exception):
    """Raised when an operation would leave the partner with no active
    owner. Surfaces as HTTP 409 on the console."""


class InvitationError(Exception):
    """Base for invitation acceptance problems. ``reason`` is a stable
    machine-readable code the console maps to copy."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


def hash_invitation_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


class PartnerMembershipRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── reads ────────────────────────────────────────────────────────

    async def get_by_user(self, user_id: str) -> PartnerMembership | None:
        """The membership behind a console user. ``UNIQUE (user_id)`` makes
        this at most one row (v1: one partner per user)."""
        result = await self._session.execute(
            sa.select(PartnerMembership).where(PartnerMembership.user_id == user_id).limit(1)
        )
        return result.scalar_one_or_none()

    async def get_active(self, partner_id: uuid.UUID, user_id: str) -> PartnerMembership | None:
        """The row the backend re-verifies on every console request: the
        user must be an ACTIVE member of exactly the partner named in the
        token. Anything else (unknown user, suspended, other partner) is
        ``None`` — the caller does not learn which."""
        result = await self._session.execute(
            sa.select(PartnerMembership)
            .where(
                PartnerMembership.partner_id == partner_id,
                PartnerMembership.user_id == user_id,
                PartnerMembership.status == MembershipStatus.ACTIVE.value,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get(
        self, partner_id: uuid.UUID, membership_id: uuid.UUID
    ) -> PartnerMembership | None:
        result = await self._session.execute(
            sa.select(PartnerMembership)
            .where(
                PartnerMembership.partner_id == partner_id,
                PartnerMembership.id == membership_id,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_for_partner(self, partner_id: uuid.UUID) -> list[PartnerMembership]:
        result = await self._session.execute(
            sa.select(PartnerMembership)
            .where(PartnerMembership.partner_id == partner_id)
            .order_by(PartnerMembership.created_at, PartnerMembership.id)
        )
        return list(result.scalars())

    async def count_active_owners(self, partner_id: uuid.UUID, *, for_update: bool = False) -> int:
        stmt = sa.select(PartnerMembership.id).where(
            PartnerMembership.partner_id == partner_id,
            PartnerMembership.role == PartnerRole.OWNER.value,
            PartnerMembership.status == MembershipStatus.ACTIVE.value,
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await self._session.execute(stmt)
        return len(result.scalars().all())

    # ── writes ───────────────────────────────────────────────────────

    async def create(self, membership: PartnerMembership) -> PartnerMembership:
        self._session.add(membership)
        await self._session.flush()
        return membership

    async def change_role(
        self, partner_id: uuid.UUID, membership_id: uuid.UUID, new_role: str
    ) -> PartnerMembership | None:
        """Change a member's role. Returns ``None`` if the member does not
        belong to the partner (opaque to the caller). Raises
        :class:`LastOwnerError` if this would demote the last owner."""
        if new_role not in {r.value for r in PartnerRole}:
            raise ValueError(f"unknown role: {new_role!r}")
        member = await self.get(partner_id, membership_id)
        if member is None:
            return None
        if member.role == new_role:
            return member
        if member.role == PartnerRole.OWNER.value:
            await self._assert_not_last_owner(partner_id, leaving=member)
        member.role = new_role
        await self._session.flush()
        return member

    async def set_status(
        self, partner_id: uuid.UUID, membership_id: uuid.UUID, status: str
    ) -> PartnerMembership | None:
        if status not in {s.value for s in MembershipStatus}:
            raise ValueError(f"unknown status: {status!r}")
        member = await self.get(partner_id, membership_id)
        if member is None:
            return None
        if member.status == status:
            return member
        if member.role == PartnerRole.OWNER.value and status == MembershipStatus.SUSPENDED.value:
            await self._assert_not_last_owner(partner_id, leaving=member)
        member.status = status
        await self._session.flush()
        return member

    async def remove(self, partner_id: uuid.UUID, membership_id: uuid.UUID) -> bool:
        """Delete a membership. ``False`` if it is not this partner's.
        Raises :class:`LastOwnerError` if it is the last active owner."""
        member = await self.get(partner_id, membership_id)
        if member is None:
            return False
        if (
            member.role == PartnerRole.OWNER.value
            and member.status == MembershipStatus.ACTIVE.value
        ):
            await self._assert_not_last_owner(partner_id, leaving=member)
        await self._session.delete(member)
        await self._session.flush()
        return True

    async def _assert_not_last_owner(
        self, partner_id: uuid.UUID, *, leaving: PartnerMembership
    ) -> None:
        # Lock every active owner row of the partner. Two concurrent
        # demotions serialise here: the second one re-counts after the
        # first committed and sees the partner would be left empty.
        result = await self._session.execute(
            sa.select(PartnerMembership.id)
            .where(
                PartnerMembership.partner_id == partner_id,
                PartnerMembership.role == PartnerRole.OWNER.value,
                PartnerMembership.status == MembershipStatus.ACTIVE.value,
            )
            .with_for_update()
        )
        owners = set(result.scalars().all())
        owners.discard(leaving.id)
        if not owners:
            raise LastOwnerError("a partner must keep at least one active owner")


class PartnerInvitationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_pending(self, partner_id: uuid.UUID) -> list[PartnerInvitation]:
        result = await self._session.execute(
            sa.select(PartnerInvitation)
            .where(
                PartnerInvitation.partner_id == partner_id,
                PartnerInvitation.status == InvitationStatus.PENDING.value,
            )
            .order_by(PartnerInvitation.created_at.desc())
        )
        return list(result.scalars())

    async def get(
        self, partner_id: uuid.UUID, invitation_id: uuid.UUID
    ) -> PartnerInvitation | None:
        result = await self._session.execute(
            sa.select(PartnerInvitation)
            .where(
                PartnerInvitation.partner_id == partner_id,
                PartnerInvitation.id == invitation_id,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_pending_by_token(self, plaintext_token: str) -> PartnerInvitation | None:
        """The invitation behind a link. Only PENDING and not yet expired
        rows resolve — an expired link is indistinguishable from a wrong
        one on purpose (nothing to enumerate)."""
        result = await self._session.execute(
            sa.select(PartnerInvitation)
            .where(PartnerInvitation.token_hash == hash_invitation_token(plaintext_token))
            .limit(1)
        )
        invitation = result.scalar_one_or_none()
        if invitation is None:
            return None
        if invitation.status != InvitationStatus.PENDING.value:
            return None
        if invitation.expires_at <= _now():
            # Mark it lazily; the partner's list shows it as expired and
            # the e-mail can be re-invited (the partial unique index only
            # blocks a second PENDING row).
            invitation.status = InvitationStatus.EXPIRED.value
            await self._session.flush()
            return None
        return invitation

    async def create(
        self,
        *,
        partner_id: uuid.UUID,
        email: str,
        role: str,
        invited_by: uuid.UUID | None,
    ) -> tuple[PartnerInvitation, str]:
        """Create a pending invitation. Returns ``(row, plaintext_token)``;
        the plaintext is what goes into the e-mail link and is never
        stored. Raises ``ValueError`` on an unknown role."""
        if role not in {r.value for r in PartnerRole}:
            raise ValueError(f"unknown role: {role!r}")
        plaintext = secrets.token_urlsafe(32)
        invitation = PartnerInvitation(
            id=uuid.uuid4(),
            partner_id=partner_id,
            email=email.strip().lower(),
            role=role,
            token_hash=hash_invitation_token(plaintext),
            invited_by=invited_by,
            status=InvitationStatus.PENDING.value,
            expires_at=_now() + INVITATION_TTL,
        )
        self._session.add(invitation)
        await self._session.flush()
        return invitation, plaintext

    async def revoke(self, partner_id: uuid.UUID, invitation_id: uuid.UUID) -> bool:
        invitation = await self.get(partner_id, invitation_id)
        if invitation is None:
            return False
        if invitation.status != InvitationStatus.PENDING.value:
            return True
        invitation.status = InvitationStatus.REVOKED.value
        await self._session.flush()
        return True

    async def accept(
        self,
        invitation: PartnerInvitation,
        *,
        user_id: str,
        email: str,
        display_name: str | None,
    ) -> PartnerMembership:
        """Turn a pending invitation into a membership.

        Rules, each with its own stable ``reason``:

        - ``expired`` / ``not_pending`` — the link is dead.
        - ``email_mismatch`` — the signed-in account's e-mail must equal
          the invited e-mail (case-insensitive). Prevents forwarding an
          invitation to someone else.
        - ``already_member`` — the user already belongs to a partner
          (v1: exactly one). Same partner or another, it is a conflict.
        """
        now = _now()
        if invitation.status != InvitationStatus.PENDING.value:
            raise InvitationError("not_pending", "invitation is no longer pending")
        if invitation.expires_at <= now:
            invitation.status = InvitationStatus.EXPIRED.value
            await self._session.flush()
            raise InvitationError("expired", "invitation has expired")
        if email.strip().lower() != invitation.email:
            raise InvitationError(
                "email_mismatch", "invitation was issued to a different e-mail address"
            )
        existing = await PartnerMembershipRepository(self._session).get_by_user(user_id)
        if existing is not None:
            raise InvitationError("already_member", "user already belongs to a partner")

        membership = PartnerMembership(
            id=uuid.uuid4(),
            partner_id=invitation.partner_id,
            user_id=user_id,
            email=invitation.email,
            display_name=display_name,
            role=invitation.role,
            status=MembershipStatus.ACTIVE.value,
            invited_by=invitation.invited_by,
            accepted_at=now,
        )
        self._session.add(membership)
        await self._session.flush()
        invitation.status = InvitationStatus.ACCEPTED.value
        invitation.accepted_at = now
        invitation.accepted_membership_id = membership.id
        await self._session.flush()
        return membership
