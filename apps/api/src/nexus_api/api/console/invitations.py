"""``/console/invitations/{token}`` — the two pre-membership calls.

The person holding an invitation link has no partner yet, so there is no
principal. The BFF authenticates itself with a **service token**
(``svc: "console"``, same signature/expiry/replay rules) and the backend
does the rest.

Since the console lost its database, accepting an invitation is also
**where the account is born**: the caller sends a password, the API
creates the principal in ``console_auth.principals``, turns the invitation
into a membership and returns a session token (auto-login). The e-mail is
NOT in the body any more — it comes from the invitation row, which is the
only thing that knows who was invited.

Edge case with a rule: if a principal already exists for that e-mail (the
person was a member somewhere before and the membership was removed), the
password sent must be **their existing one**. Right password → the
membership is attached to the account they already have; wrong password →
409 ``account_exists``. It is not a way to reset a password: holding an
invitation link never rewrites credentials.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.core.console_auth import ConsoleService, require_console_service
from nexus_api.db.models import AuditLog, NotificationKind, Partner
from nexus_api.repositories.partner_membership import (
    InvitationError,
    PartnerInvitationRepository,
)
from nexus_api.services import console_identity
from nexus_api.services.console_notifications import emit as emit_notification

from .auth import check_login_rate_limit
from .schemas import InvitationAcceptOut, InvitationLookupOut, PartnerBrief
from .schemas_auth import InvitationAcceptWithPasswordIn

router = APIRouter(prefix="/invitations")

Token = Path(..., min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


@router.get("/{token}", response_model=InvitationLookupOut)
async def lookup_invitation(
    token: str = Token,
    _svc: ConsoleService = Depends(require_console_service()),
    session: AsyncSession = Depends(get_db_session),
) -> InvitationLookupOut:
    async with session.begin():
        invitation = await PartnerInvitationRepository(session).get_pending_by_token(token)
        if invitation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="invitation not found or expired"
            )
        partner = await session.get(Partner, invitation.partner_id)
        name = partner.name if partner else "—"
        out = InvitationLookupOut(
            partner_name=name,
            email=invitation.email,
            role=invitation.role,
            expires_at=invitation.expires_at,
        )
    return out


@router.post(
    "/{token}/accept",
    response_model=InvitationAcceptOut,
    responses={
        404: {"description": "Not found or expired."},
        409: {
            "description": (
                "The user already belongs to a partner, or an account already "
                "exists for that e-mail and the password does not match."
            )
        },
        429: {"description": "Too many attempts; see Retry-After."},
    },
)
async def accept_invitation(
    body: InvitationAcceptWithPasswordIn,
    request: Request,
    token: str = Token,
    _svc: ConsoleService = Depends(require_console_service()),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> InvitationAcceptOut:
    ip = request.client.host if request.client else None

    # First transaction: resolve the invitation and settle WHO is accepting.
    # It is separate from the write below for the same reason the login
    # endpoint splits its two: when the address already has an account and
    # the password is wrong, the failed-attempt counter must survive the
    # 409 — inside a single transaction the rollback would erase it and the
    # lockout would never trigger on this path.
    async with session.begin():
        invitation = await PartnerInvitationRepository(session).get_pending_by_token(token)
        if invitation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="invitation not found or expired"
            )
        invited_email = invitation.email
        # Same bucket as the login: the branch below checks a password, so
        # it must not be a cheaper oracle than ``/console/auth/login``.
        await check_login_rate_limit(redis, email=invited_email, ip=ip)
        existing = await console_identity.get_by_email(session, invited_email)
        authenticated = (
            await console_identity.authenticate(
                session, email=invited_email, password=body.password
            )
            if existing is not None
            else None
        )
    if existing is not None and authenticated is None:
        # An account already exists for the invited address: the only way in
        # is its own password. Accepting an invitation never rewrites
        # credentials (that would make any invitation link a password reset
        # for the address it names).
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="account_exists: sign in with your existing password to accept",
        )

    async with session.begin():
        repo = PartnerInvitationRepository(session)
        invitation = await repo.get_pending_by_token(token)
        if invitation is None:  # pragma: no cover - revoked between the two reads
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="invitation not found or expired"
            )
        account = (
            authenticated
            if authenticated is not None
            else await console_identity.create_account(
                session,
                email=invited_email,
                password=body.password,
                display_name=body.display_name,
            )
        )

        try:
            membership = await repo.accept(
                invitation,
                user_id=str(account.id),
                email=invited_email,
                display_name=body.display_name or account.display_name,
            )
        except InvitationError as exc:
            code = (
                status.HTTP_404_NOT_FOUND
                if exc.reason in {"expired", "not_pending"}
                else status.HTTP_409_CONFLICT
            )
            raise HTTPException(status_code=code, detail=f"{exc.reason}: {exc.detail}") from exc
        partner = await session.get(Partner, membership.partner_id)
        if partner is None:  # pragma: no cover - FK
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="partner missing")
        session.add(
            AuditLog(
                tenant_id=None,
                actor=f"console:{membership.email}",
                action="console.invitation.accept",
                target=f"partner:{partner.id}",
                after_json={"email": membership.email, "role": membership.role},
            )
        )
        # CP-29: tell the rest of the team (broadcast; the newcomer sees it too).
        await emit_notification(
            session,
            partner_id=partner.id,
            kind=NotificationKind.MEMBER_JOINED,
            data={"email": membership.email, "role": membership.role},
            dedupe_key=f"partner:{partner.id}:member.joined:{membership.id}",
        )
        # Auto-login: the person just chose a password on a link only they
        # received. Sending them to /login to type it again buys nothing.
        session_token, expires_at = await console_identity.start_session(
            session,
            account,
            ip=ip,
            user_agent=request.headers.get("user-agent"),
        )
        out = InvitationAcceptOut(
            membership_id=membership.id,
            partner=PartnerBrief(slug=partner.slug, name=partner.name, status=partner.status),
            role=membership.role,
            token=session_token,
            expires_at=expires_at,
        )
    return out
