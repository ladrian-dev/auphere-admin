"""``/console/team`` — members, invitations and roles (CP-26 backend, on
top of the CP-02 repositories).

Rules the endpoints enforce (each has a test):

- the last active owner cannot be demoted, suspended or removed → 409;
- one pending invitation per e-mail → 409;
- you cannot change your own role or remove yourself (ask another
  owner/admin) → 409 — prevents the "locked myself out" ticket;
- ``team:manage`` (owner, admin) for every write; ``team:read`` for the
  list.

Invitation delivery: the accept link is e-mailed when e-mail is
configured and ALWAYS returned once to the inviter (``accept_path``) so
it can be shared by hand — the pilot partners are two, and a broken SMTP
must not block onboarding.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.db.models import (
    AuditLog,
    PartnerInvitation,
    PartnerLocalExecPolicy,
    PartnerMembership,
)
from nexus_api.repositories.partner_membership import (
    LastOwnerError,
    PartnerInvitationRepository,
    PartnerMembershipRepository,
)
from nexus_api.services.email import send_email
from nexus_api.services.local_exec_policy import LocalExecPolicyRepository

from .schemas import (
    InvitationCreatedOut,
    InvitationOut,
    InviteIn,
    MemberOut,
    MemberRoleIn,
    MemberStatusIn,
    TeamOut,
)
from .schemas_workstation import LocalExecCeilingIn, LocalExecCeilingOut

router = APIRouter(prefix="/team")

INVITE_ACCEPT_PATH = "/invite/{token}"


def _member_out(m: PartnerMembership, *, me: uuid.UUID) -> MemberOut:
    return MemberOut(
        id=m.id,
        email=m.email,
        display_name=m.display_name,
        role=m.role,
        status=m.status,
        accepted_at=m.accepted_at,
        created_at=m.created_at,
        is_you=m.id == me,
    )


def _invitation_out(i: PartnerInvitation) -> InvitationOut:
    return InvitationOut(
        id=i.id,
        email=i.email,
        role=i.role,
        status=i.status,
        expires_at=i.expires_at,
        created_at=i.created_at,
    )


def _platform_audit(principal: ConsolePrincipal, action: str, **after: object) -> AuditLog:
    return AuditLog(
        tenant_id=None,
        actor=principal.actor,
        action=action,
        target=f"partner:{principal.partner.id}",
        before_json=None,
        after_json=dict(after),
    )


def _last_owner() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="a partner must keep at least one active owner",
    )


def _self_change() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="you cannot change your own membership; ask another owner or admin",
    )


@router.get("", response_model=TeamOut)
async def get_team(
    principal: ConsolePrincipal = Depends(require_console_principal("team:read")),
    session: AsyncSession = Depends(get_db_session),
) -> TeamOut:
    async with session.begin():
        members = await PartnerMembershipRepository(session).list_for_partner(principal.partner.id)
        invitations = await PartnerInvitationRepository(session).list_pending(principal.partner.id)
    me = principal.membership.id
    return TeamOut(
        members=[_member_out(m, me=me) for m in members],
        invitations=[_invitation_out(i) for i in invitations],
    )


@router.post(
    "/invitations",
    response_model=InvitationCreatedOut,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "Already a member or already invited."}},
)
async def invite(
    body: InviteIn,
    principal: ConsolePrincipal = Depends(require_console_principal("team:manage")),
    session: AsyncSession = Depends(get_db_session),
) -> InvitationCreatedOut:
    email = str(body.email).strip().lower()
    async with session.begin():
        members = PartnerMembershipRepository(session)
        if any(
            (m.email or "").lower() == email
            for m in await members.list_for_partner(principal.partner.id)
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="already a member of this partner"
            )
        try:
            invitation, token = await PartnerInvitationRepository(session).create(
                partner_id=principal.partner.id,
                email=email,
                role=body.role,
                invited_by=principal.membership.id,
            )
        except IntegrityError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="an invitation for this e-mail is already pending",
            ) from None
        session.add(
            _platform_audit(principal, "console.member.invite", email=email, role=body.role)
        )

    accept_path = INVITE_ACCEPT_PATH.format(token=token)
    sent = await send_email(
        to=email,
        subject=f"{principal.partner.name} te invita a la consola de Auphere",
        html=(
            f"<p>{principal.membership.email} te ha invitado a la consola de "
            f"<strong>{principal.partner.name}</strong> con el rol <strong>{body.role}</strong>.</p>"
            f"<p>La invitación caduca el {invitation.expires_at:%Y-%m-%d}.</p>"
            f"<p>Ruta de aceptación: <code>{accept_path}</code></p>"
        ),
    )
    return InvitationCreatedOut(
        **_invitation_out(invitation).model_dump(), accept_path=accept_path, email_sent=sent
    )


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invitation(
    invitation_id: uuid.UUID,
    principal: ConsolePrincipal = Depends(require_console_principal("team:manage")),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    async with session.begin():
        repo = PartnerInvitationRepository(session)
        invitation = await repo.get(principal.partner.id, invitation_id)
        if invitation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown invitation")
        await repo.revoke(principal.partner.id, invitation_id)
        session.add(_platform_audit(principal, "console.invitation.revoke", email=invitation.email))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/members/{membership_id}/role",
    response_model=MemberOut,
    responses={409: {"description": "Last owner, or your own membership."}},
)
async def change_role(
    membership_id: uuid.UUID,
    body: MemberRoleIn,
    principal: ConsolePrincipal = Depends(require_console_principal("team:manage")),
    session: AsyncSession = Depends(get_db_session),
) -> MemberOut:
    if membership_id == principal.membership.id:
        raise _self_change()
    async with session.begin():
        repo = PartnerMembershipRepository(session)
        try:
            member = await repo.change_role(principal.partner.id, membership_id, body.role)
        except LastOwnerError:
            raise _last_owner() from None
        if member is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown member")
        session.add(
            _platform_audit(principal, "console.member.role", email=member.email, role=body.role)
        )
        out = _member_out(member, me=principal.membership.id)
    return out


@router.patch(
    "/members/{membership_id}/status",
    response_model=MemberOut,
    responses={409: {"description": "Last owner, or your own membership."}},
)
async def change_status(
    membership_id: uuid.UUID,
    body: MemberStatusIn,
    principal: ConsolePrincipal = Depends(require_console_principal("team:manage")),
    session: AsyncSession = Depends(get_db_session),
) -> MemberOut:
    if membership_id == principal.membership.id:
        raise _self_change()
    async with session.begin():
        repo = PartnerMembershipRepository(session)
        try:
            member = await repo.set_status(principal.partner.id, membership_id, body.status)
        except LastOwnerError:
            raise _last_owner() from None
        if member is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown member")
        session.add(
            _platform_audit(
                principal, "console.member.status", email=member.email, status=body.status
            )
        )
        out = _member_out(member, me=principal.membership.id)
    return out


@router.delete(
    "/members/{membership_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={409: {"description": "Last owner, or your own membership."}},
)
async def remove_member(
    membership_id: uuid.UUID,
    principal: ConsolePrincipal = Depends(require_console_principal("team:manage")),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    if membership_id == principal.membership.id:
        raise _self_change()
    async with session.begin():
        repo = PartnerMembershipRepository(session)
        member = await repo.get(principal.partner.id, membership_id)
        if member is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown member")
        email = member.email
        try:
            await repo.remove(principal.partner.id, membership_id)
        except LastOwnerError:
            raise _last_owner() from None
        session.add(_platform_audit(principal, "console.member.remove", email=email))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── el techo de ejecución local del partner (spec 003, Requisito 10.1) ──
#
# Vive aquí y no en `/console/teammates/*` a propósito: es una decisión de
# seguridad del **equipo**, no una preferencia de quien opera. Por eso la
# escribe `teammates:policy` (owner y admin) y la lee cualquiera que ya vea el
# equipo — saber qué techo hay puesto no es un secreto, y esconderlo solo
# haría que la gente no entendiera por qué se le sigue preguntando.


@router.get("/local-exec-ceiling", response_model=LocalExecCeilingOut)
async def get_local_exec_ceiling(
    principal: ConsolePrincipal = Depends(require_console_principal("team:read")),
    session: AsyncSession = Depends(get_db_session),
) -> LocalExecCeilingOut:
    async with session.begin():
        await apply_partner_to_session(
            session, principal.partner.id, principal_id=principal.user_id
        )
        row = await session.get(PartnerLocalExecPolicy, principal.partner.id)
        return LocalExecCeilingOut(
            # Sin fila no hay restricción: cada persona decide dentro de la
            # lista blanca de su cliente.
            ceiling=(row.ceiling if row is not None else "always"),
            updated_by=(row.updated_by if row is not None else None),
        )


@router.put("/local-exec-ceiling", response_model=LocalExecCeilingOut)
async def put_local_exec_ceiling(
    body: LocalExecCeilingIn,
    principal: ConsolePrincipal = Depends(require_console_principal("teammates:policy")),
    session: AsyncSession = Depends(get_db_session),
) -> LocalExecCeilingOut:
    """Pone el techo. Bajarlo tiene efecto **en la siguiente invocación**: no
    revoca permisos de argumentos ya concedidos, que se revocan uno a uno desde
    el puesto de trabajo del cliente."""
    async with session.begin():
        await apply_partner_to_session(
            session, principal.partner.id, principal_id=principal.user_id
        )
        await LocalExecPolicyRepository(session).set_ceiling(
            principal.partner.id, ceiling=body.ceiling, by=principal.user_id
        )
        session.add(
            AuditLog(
                tenant_id=None,
                actor=principal.actor,
                action="local_policy.ceiling_changed",
                target=f"partner:{principal.partner.id}",
                after_json={"ceiling": body.ceiling},
            )
        )
    return LocalExecCeilingOut(ceiling=body.ceiling, updated_by=principal.user_id)
