"""``/console/invitations/{token}`` — the two pre-membership calls.

The person holding an invitation link has no partner yet, so there is no
principal. The BFF authenticates itself with a **service token**
(``svc: "console"``, same signature/expiry/replay rules) and the backend
does the rest: resolve the pending invitation by token, and — after the
BFF has authenticated the person — turn it into a membership. The e-mail
of the authenticated account must match the invitation; the BFF says
which e-mail it is, the backend checks it against the row.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.console_auth import ConsoleService, require_console_service
from nexus_api.db.models import AuditLog, Partner
from nexus_api.repositories.partner_membership import (
    InvitationError,
    PartnerInvitationRepository,
)

from .schemas import InvitationAcceptIn, InvitationAcceptOut, InvitationLookupOut, PartnerBrief

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
        409: {"description": "E-mail mismatch or the user already belongs to a partner."},
    },
)
async def accept_invitation(
    body: InvitationAcceptIn,
    token: str = Token,
    _svc: ConsoleService = Depends(require_console_service()),
    session: AsyncSession = Depends(get_db_session),
) -> InvitationAcceptOut:
    async with session.begin():
        repo = PartnerInvitationRepository(session)
        invitation = await repo.get_pending_by_token(token)
        if invitation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="invitation not found or expired"
            )
        try:
            membership = await repo.accept(
                invitation,
                user_id=body.user_id,
                email=str(body.email),
                display_name=body.display_name,
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
        out = InvitationAcceptOut(
            membership_id=membership.id,
            partner=PartnerBrief(slug=partner.slug, name=partner.name, status=partner.status),
            role=membership.role,
        )
    return out
