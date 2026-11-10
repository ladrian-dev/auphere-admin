"""«He olvidado mi contraseña» con una invitación sin aceptar — spec 055, Requisito 1.

Una cuenta de consola nace al **aceptar** una invitación. Hasta entonces la
dirección no tiene cuenta, y «recuperar» no enviaba nada mientras la pantalla
decía «mira tu correo». Quien se quedaba así no tenía contraseña que restablecer:
lo que le deja entrar es la invitación. Así que se le vuelve a enviar, con un
enlace nuevo, y el anterior deja de valer, como al reenviar desde el panel.

**Nada de esto se ve desde fuera.** :func:`resend_for_forgot` corre en segundo
plano también cuando no hay nada que reenviar, con su propia sesión y sin lanzar
nunca: la respuesta de ``/console/password-reset`` es la misma, y tarda lo mismo,
con cuenta, con invitación y sin nada (R1.6).

Tres invitaciones posibles, y la más reciente de las vivas es la que se reenvía:

- **la del propietario, de Auphere** (``invited_by`` vacío): ``owner_invitation``;
- **la de equipo**, emitida desde la consola por alguien del partner;
- **la de un cliente** a su consola lite (spec 030).

El partner y el cliente salen siempre de la invitación, nunca de la petición
(R1.8), y el reenvío queda auditado con :data:`ACTOR`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Literal

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    ClientInvitation,
    ConsoleAccount,
    InvitationStatus,
    Partner,
    PartnerInvitation,
    PartnerMembership,
)
from nexus_api.repositories import AuditRepository
from nexus_api.repositories.partner_membership import (
    PartnerInvitationRepository,
    invitation_is_live_clause,
)
from nexus_api.services.email_catalog import (
    ROLE_LABELS,
    EmailKind,
    console_link,
    email_locale,
    format_day,
)

log = structlog.get_logger(__name__)

#: Quien reenvía: nadie en concreto, la petición de «recuperar».
ACTOR: Final = "system:password_reset"
ACCEPT_PATH: Final = "/invite/{token}"


@dataclass(frozen=True)
class _Live:
    kind: Literal["partner", "client"]
    id: uuid.UUID
    created_at: datetime


def _now() -> datetime:
    return datetime.now(UTC)


async def send_team_invite(
    *,
    inviter: str,
    partner_id: uuid.UUID,
    partner_name: str,
    to: str,
    role: str,
    locale: str,
    expires_at: datetime,
    accept_path: str,
) -> bool:
    """``team_invite``. Nunca lanza: ``send_template`` responde si salió. Es el
    correo de ``POST /console/team/invitations``, sin depender de quién pulsa."""
    from nexus_api.services.email import send_template

    subject = (
        f"{inviter} invited you to join {partner_name} on Auphere"
        if locale == "en"
        else f"{inviter} te ha invitado a unirte a {partner_name} en Auphere"
    )
    return await send_template(
        EmailKind.TEAM_INVITE,
        to=to,
        subject=subject,
        variables={
            "INVITER": inviter,
            "PARTNER_NAME": partner_name,
            "ROLE_LABEL": ROLE_LABELS[locale].get(role, role),
            "EXPIRES_ON": format_day(expires_at.date(), locale),
            "ACCEPT_URL": console_link(accept_path),
        },
        locale=locale,
        partner_id=partner_id,
    )


async def _latest_live(session: AsyncSession, email: str) -> _Live | None:
    now = _now()
    partner = (
        await session.execute(
            sa.select(PartnerInvitation.id, PartnerInvitation.created_at)
            .where(PartnerInvitation.email == email, invitation_is_live_clause(now))
            .order_by(PartnerInvitation.created_at.desc())
            .limit(1)
        )
    ).first()
    client = (
        await session.execute(
            sa.select(ClientInvitation.id, ClientInvitation.created_at)
            .where(
                ClientInvitation.email == email,
                ClientInvitation.status == InvitationStatus.PENDING.value,
                ClientInvitation.expires_at > now,
            )
            .order_by(ClientInvitation.created_at.desc())
            .limit(1)
        )
    ).first()
    found: list[_Live] = []
    if partner is not None:
        found.append(_Live("partner", partner[0], partner[1]))
    if client is not None:
        found.append(_Live("client", client[0], client[1]))
    return max(found, key=lambda live: live.created_at) if found else None


async def _resend_owner(session: AsyncSession, invitation: PartnerInvitation) -> bool:
    from nexus_api.services import owner_invitation

    async with session.begin():
        issued = await owner_invitation.resend(
            session, invitation.partner_id, invitation.id, actor=ACTOR
        )
    return (await owner_invitation.deliver(issued)).email_sent


async def _inviter_locale(session: AsyncSession, inviter: PartnerMembership | None) -> str:
    """El idioma de quien invitó: es lo que usa la consola cuando la persona
    invitada aún no tiene cuenta (spec 051)."""
    address = (inviter.email if inviter else "") or ""
    locale = await session.scalar(
        sa.select(ConsoleAccount.locale).where(
            sa.func.lower(ConsoleAccount.email) == address.strip().lower()
        )
    )
    return email_locale(locale) if locale else "es"


async def _resend_team(session: AsyncSession, invitation: PartnerInvitation) -> bool:
    async with session.begin():
        partner = await session.get(Partner, invitation.partner_id)
        if partner is None or partner.status != "active" or not partner.console_enabled:
            log.info("invitation_reissue.partner_closed", partner_id=str(invitation.partner_id))
            return False
        inviter = (
            await session.get(PartnerMembership, invitation.invited_by)
            if invitation.invited_by
            else None
        )
        role, invited_by = invitation.role, invitation.invited_by
        invitation.status = InvitationStatus.REVOKED.value
        # Antes de crear: el índice único no admite dos pendientes de una dirección.
        await session.flush()
        fresh, token = await PartnerInvitationRepository(session).create(
            partner_id=partner.id, email=invitation.email, role=role, invited_by=invited_by
        )
        await AuditRepository(session).record(
            actor=ACTOR,
            action="console.member.invite_resent",
            target=f"partner:{partner.id}",
            before=None,
            after={"email": fresh.email, "role": role},
            platform=True,
        )
        locale = await _inviter_locale(session, inviter)
        inviter_name = (inviter.display_name or inviter.email) if inviter else partner.name
        partner_id, partner_name = partner.id, partner.name
    return await send_team_invite(
        inviter=inviter_name or partner_name,
        partner_id=partner_id,
        partner_name=partner_name,
        to=fresh.email,
        role=role,
        locale=locale,
        expires_at=fresh.expires_at,
        accept_path=ACCEPT_PATH.format(token=token),
    )


async def _resend_client(session: AsyncSession, invitation_id: uuid.UUID) -> bool:
    from nexus_api.core.tenant_context import declare_tenant
    from nexus_api.services import client_access
    from nexus_api.services.client_invitation_email import send_client_invitation

    async with session.begin():
        previous = await session.get(ClientInvitation, invitation_id)
        assert previous is not None  # la acabamos de leer viva
        tenant_id = previous.tenant_id
        await declare_tenant(session, tenant_id)
        invitation, token = await client_access.resend(
            session, tenant_id, invitation_id, actor=ACTOR
        )
        client = await client_access.client_name(session, invitation)
        email, expires_at = invitation.email, invitation.expires_at
    return await send_client_invitation(
        email=email,
        client_name=client,
        accept_path=ACCEPT_PATH.format(token=token),
        expires_at=expires_at,
        tenant_id=tenant_id,
    )


async def resend_for_forgot(email: str) -> None:
    """Reenvía la invitación viva más reciente de ``email``, si la hay. Nunca
    lanza: corre después de la respuesta y nadie la espera."""
    try:
        async with get_sessionmaker()() as session:
            async with session.begin():
                live = await _latest_live(session, email)
                invitation = (
                    await session.get(PartnerInvitation, live.id)
                    if live is not None and live.kind == "partner"
                    else None
                )
            if live is None:
                return
            if live.kind == "client":
                sent = await _resend_client(session, live.id)
            elif invitation is not None and invitation.invited_by is None:
                sent = await _resend_owner(session, invitation)
            elif invitation is not None:
                sent = await _resend_team(session, invitation)
            else:  # pragma: no cover - la acabamos de leer viva
                return
    except Exception as exc:
        # El partner apagado, la invitación que se aceptó a la vez, un fallo de
        # base de datos: nadie espera esto, y la respuesta ya salió. Solo el tipo,
        # porque el texto de una excepción puede llevar un enlace.
        log.warning("invitation_reissue.not_resent", error_type=type(exc).__name__)
        return
    if not sent:
        log.error("invitation_reissue.mail_not_sent")


__all__ = ["ACTOR", "resend_for_forgot", "send_team_invite"]
