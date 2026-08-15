"""CP-02 — ``partner_memberships`` + ``partner_invitations`` repositories.

What is pinned here:

- a user belongs to exactly one partner (``UNIQUE (user_id)``);
- an invitation expires 21 days after creation and a dead link is
  indistinguishable from a wrong one;
- the last active owner of a partner can neither be demoted, suspended
  nor removed (``LastOwnerError`` — the console maps it to 409).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from nexus_api.db.models import (
    INVITATION_TTL,
    InvitationStatus,
    MembershipStatus,
    Partner,
    PartnerInvitation,
    PartnerMembership,
    PartnerRole,
)
from nexus_api.repositories.partner_membership import (
    InvitationError,
    LastOwnerError,
    PartnerInvitationRepository,
    PartnerMembershipRepository,
    hash_invitation_token,
)

pytestmark = pytest.mark.asyncio


async def _partner(db_session, slug: str) -> uuid.UUID:
    partner_id = uuid.uuid4()
    db_session.add(Partner(id=partner_id, name=f"Partner {slug}", slug=slug))
    await db_session.commit()
    return partner_id


def _member(partner_id: uuid.UUID, *, role: str, user_id: str | None = None) -> PartnerMembership:
    uid = user_id or f"user_{uuid.uuid4().hex[:12]}"
    return PartnerMembership(
        id=uuid.uuid4(),
        partner_id=partner_id,
        user_id=uid,
        email=f"{uid}@example.com",
        display_name=uid,
        role=role,
        status=MembershipStatus.ACTIVE.value,
        accepted_at=datetime.now(UTC),
    )


# ── memberships ────────────────────────────────────────────────────────


async def test_user_belongs_to_exactly_one_partner(db_session) -> None:
    a = await _partner(db_session, f"pa-{uuid.uuid4().hex[:6]}")
    b = await _partner(db_session, f"pb-{uuid.uuid4().hex[:6]}")
    repo = PartnerMembershipRepository(db_session)
    first = await repo.create(_member(a, role="owner", user_id="user_shared"))
    await db_session.commit()

    db_session.add(_member(b, role="admin", user_id="user_shared"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    resolved = await repo.get_by_user("user_shared")
    assert resolved is not None
    assert resolved.id == first.id
    assert resolved.partner_id == a


async def test_get_active_is_bounded_by_partner_and_status(db_session) -> None:
    a = await _partner(db_session, f"pa-{uuid.uuid4().hex[:6]}")
    b = await _partner(db_session, f"pb-{uuid.uuid4().hex[:6]}")
    repo = PartnerMembershipRepository(db_session)
    member = await repo.create(_member(a, role="builder"))
    await db_session.commit()

    assert await repo.get_active(a, member.user_id) is not None
    # Same user, other partner: nothing — the backend never learns why.
    assert await repo.get_active(b, member.user_id) is None

    await repo.set_status(a, member.id, MembershipStatus.SUSPENDED.value)
    await db_session.commit()
    assert await repo.get_active(a, member.user_id) is None


async def test_last_owner_cannot_be_demoted(db_session) -> None:
    a = await _partner(db_session, f"pa-{uuid.uuid4().hex[:6]}")
    repo = PartnerMembershipRepository(db_session)
    owner = await repo.create(_member(a, role="owner"))
    await db_session.commit()
    owner_id = owner.id

    with pytest.raises(LastOwnerError):
        await repo.change_role(a, owner_id, PartnerRole.ADMIN.value)
    await db_session.rollback()

    refreshed = await repo.get(a, owner_id)
    assert refreshed is not None
    assert refreshed.role == "owner"


async def test_last_owner_cannot_be_removed_or_suspended(db_session) -> None:
    a = await _partner(db_session, f"pa-{uuid.uuid4().hex[:6]}")
    repo = PartnerMembershipRepository(db_session)
    owner = await repo.create(_member(a, role="owner"))
    await db_session.commit()
    owner_id = owner.id

    with pytest.raises(LastOwnerError):
        await repo.remove(a, owner_id)
    await db_session.rollback()
    with pytest.raises(LastOwnerError):
        await repo.set_status(a, owner_id, MembershipStatus.SUSPENDED.value)
    await db_session.rollback()

    assert await repo.count_active_owners(a) == 1


async def test_owner_can_step_down_when_another_owner_exists(db_session) -> None:
    a = await _partner(db_session, f"pa-{uuid.uuid4().hex[:6]}")
    repo = PartnerMembershipRepository(db_session)
    first = await repo.create(_member(a, role="owner"))
    second = await repo.create(_member(a, role="owner"))
    await db_session.commit()
    first_id, second_id = first.id, second.id

    changed = await repo.change_role(a, first_id, PartnerRole.ANALYST.value)
    await db_session.commit()
    assert changed is not None and changed.role == "analyst"
    assert await repo.count_active_owners(a) == 1

    # Now ``second`` is the last one and is protected.
    with pytest.raises(LastOwnerError):
        await repo.remove(a, second_id)
    await db_session.rollback()


async def test_non_owner_operations_never_touch_owner_guard(db_session) -> None:
    a = await _partner(db_session, f"pa-{uuid.uuid4().hex[:6]}")
    repo = PartnerMembershipRepository(db_session)
    await repo.create(_member(a, role="owner"))
    builder = await repo.create(_member(a, role="builder"))
    await db_session.commit()

    assert (await repo.change_role(a, builder.id, "analyst")) is not None
    assert await repo.remove(a, builder.id) is True
    await db_session.commit()
    assert await repo.get(a, builder.id) is None


async def test_membership_operations_are_partner_bounded(db_session) -> None:
    a = await _partner(db_session, f"pa-{uuid.uuid4().hex[:6]}")
    b = await _partner(db_session, f"pb-{uuid.uuid4().hex[:6]}")
    repo = PartnerMembershipRepository(db_session)
    await repo.create(_member(a, role="owner"))
    member_a = await repo.create(_member(a, role="builder"))
    await db_session.commit()

    # Partner B addressing A's member by id: not found, nothing changes.
    assert await repo.get(b, member_a.id) is None
    assert await repo.change_role(b, member_a.id, "admin") is None
    assert await repo.remove(b, member_a.id) is False
    assert (await repo.get(a, member_a.id)).role == "builder"  # type: ignore[union-attr]


async def test_change_role_rejects_unknown_role(db_session) -> None:
    a = await _partner(db_session, f"pa-{uuid.uuid4().hex[:6]}")
    repo = PartnerMembershipRepository(db_session)
    owner = await repo.create(_member(a, role="owner"))
    await db_session.commit()
    with pytest.raises(ValueError):
        await repo.change_role(a, owner.id, "superuser")


# ── invitations ────────────────────────────────────────────────────────


async def test_invitation_expires_after_21_days(db_session) -> None:
    a = await _partner(db_session, f"pa-{uuid.uuid4().hex[:6]}")
    invitations = PartnerInvitationRepository(db_session)
    before = datetime.now(UTC)
    invitation, token = await invitations.create(
        partner_id=a, email="Maria@Example.com", role="builder", invited_by=None
    )
    await db_session.commit()

    assert timedelta(days=21) == INVITATION_TTL
    assert invitation.email == "maria@example.com"
    assert invitation.token_hash == hash_invitation_token(token)
    assert (
        timedelta(days=20, hours=23)
        < invitation.expires_at - before
        <= timedelta(days=21, minutes=1)
    )
    assert await invitations.get_pending_by_token(token) is not None

    # Fast-forward: an expired link resolves to nothing and flips the row.
    await db_session.execute(
        sa.update(PartnerInvitation)
        .where(PartnerInvitation.id == invitation.id)
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    await db_session.commit()
    assert await invitations.get_pending_by_token(token) is None
    await db_session.commit()
    await db_session.refresh(invitation)
    assert invitation.status == InvitationStatus.EXPIRED.value


async def test_wrong_and_revoked_tokens_resolve_to_nothing(db_session) -> None:
    a = await _partner(db_session, f"pa-{uuid.uuid4().hex[:6]}")
    invitations = PartnerInvitationRepository(db_session)
    invitation, token = await invitations.create(
        partner_id=a, email="x@example.com", role="analyst", invited_by=None
    )
    await db_session.commit()

    assert await invitations.get_pending_by_token(token + "x") is None
    assert await invitations.revoke(a, invitation.id) is True
    await db_session.commit()
    assert await invitations.get_pending_by_token(token) is None


async def test_accept_creates_membership_and_closes_invitation(db_session) -> None:
    a = await _partner(db_session, f"pa-{uuid.uuid4().hex[:6]}")
    invitations = PartnerInvitationRepository(db_session)
    invitation, token = await invitations.create(
        partner_id=a, email="new@example.com", role="admin", invited_by=None
    )
    await db_session.commit()

    pending = await invitations.get_pending_by_token(token)
    assert pending is not None
    membership = await invitations.accept(
        pending, user_id="user_new", email="NEW@example.com", display_name="New Person"
    )
    await db_session.commit()

    assert membership.partner_id == a
    assert membership.role == "admin"
    assert membership.status == "active"
    assert membership.accepted_at is not None
    await db_session.refresh(invitation)
    assert invitation.status == InvitationStatus.ACCEPTED.value
    assert invitation.accepted_membership_id == membership.id
    # The link is now dead.
    assert await invitations.get_pending_by_token(token) is None


async def test_accept_rejects_other_email_and_existing_members(db_session) -> None:
    a = await _partner(db_session, f"pa-{uuid.uuid4().hex[:6]}")
    b = await _partner(db_session, f"pb-{uuid.uuid4().hex[:6]}")
    invitations = PartnerInvitationRepository(db_session)
    memberships = PartnerMembershipRepository(db_session)
    invitation, _ = await invitations.create(
        partner_id=a, email="invited@example.com", role="builder", invited_by=None
    )
    await memberships.create(_member(b, role="owner", user_id="user_elsewhere"))
    await db_session.commit()
    await db_session.refresh(invitation)

    with pytest.raises(InvitationError) as exc:
        await invitations.accept(
            invitation, user_id="user_x", email="someone-else@example.com", display_name=None
        )
    assert exc.value.reason == "email_mismatch"

    with pytest.raises(InvitationError) as exc:
        await invitations.accept(
            invitation, user_id="user_elsewhere", email="invited@example.com", display_name=None
        )
    assert exc.value.reason == "already_member"

    await db_session.refresh(invitation)
    assert invitation.status == InvitationStatus.PENDING.value


async def test_one_pending_invitation_per_email_and_partner(db_session) -> None:
    a = await _partner(db_session, f"pa-{uuid.uuid4().hex[:6]}")
    invitations = PartnerInvitationRepository(db_session)
    first, _ = await invitations.create(
        partner_id=a, email="dup@example.com", role="builder", invited_by=None
    )
    await db_session.commit()
    first_id = first.id

    with pytest.raises(IntegrityError):
        await invitations.create(
            partner_id=a, email="DUP@example.com", role="analyst", invited_by=None
        )
    await db_session.rollback()

    # After revoking, the same e-mail can be invited again.
    assert await invitations.revoke(a, first_id)
    await db_session.commit()
    again, _ = await invitations.create(
        partner_id=a, email="dup@example.com", role="analyst", invited_by=None
    )
    await db_session.commit()
    assert again.id != first_id
    assert [i.id for i in await invitations.list_pending(a)] == [again.id]
