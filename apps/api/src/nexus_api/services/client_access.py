"""El acceso de un cliente a su consola — spec 030 (Requisito 1).

Lo usa el admin (``api/admin/client_access.py``) para encender la consola
lite de un cliente, elegir sus módulos e invitar o revocar personas, y la
consola (``api/console/invitations.py``) para aceptar una invitación.

Tres reglas que viven aquí y en ningún otro sitio:

* **Quién es elegible.** Un cliente que está en un partner (``partner_tenants``)
  y no está archivado. Los clientes directos de Auphere cuelgan de Auphere
  Internal Partner, así que también lo están.
* **Qué módulos.** Al menos uno con el acceso encendido; la Bandeja, solo con un
  WhatsApp conectado **al elegirla** (si luego se desconecta, la Bandeja sigue
  dejando leer: R6.2).
* **Una cuenta, una casa.** Una cuenta de consola es de un partner o de un
  cliente, nunca de los dos ni de dos clientes. No se puede declarar entre dos
  tablas, así que se comprueba al invitar y al aceptar bajo un bloqueo
  consultivo por correo: dos aceptaciones simultáneas se ordenan ahí.

Ninguna función hace commit: el llamante abre la transacción.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import (
    CLIENT_INVITATION_TTL,
    CLIENT_MODULES,
    AuditLog,
    Channel,
    ChannelStatus,
    ChannelType,
    ClientAccess,
    ClientInvitation,
    ClientInvitationStatus,
    ClientMembership,
    ClientMemberStatus,
    ClientModule,
    ConsoleAccount,
    Partner,
    PartnerMembership,
    PartnerTenant,
    Tenant,
    TenantStatus,
)
from nexus_api.repositories.partner_membership import hash_invitation_token
from nexus_api.services import console_identity, inbox_lifecycle

log = structlog.get_logger(__name__)


class ClientAccessError(Exception):
    """Un no con nombre. ``code`` es vocabulario cerrado; ``status`` el HTTP."""

    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class MemberRow:
    id: uuid.UUID
    kind: str  # "member" | "invitation"
    email: str
    name: str | None
    status: str
    since: datetime | None = None
    expires_at: datetime | None = None


@dataclass(frozen=True)
class AccessView:
    eligible: bool
    ineligible_reason: str | None
    partner: Partner | None
    whatsapp_connected: bool
    enabled: bool
    modules: tuple[str, ...]
    members: list[MemberRow] = field(default_factory=list)


def _now() -> datetime:
    return datetime.now(UTC)


def _ordered(modules: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    have = set(modules)
    return tuple(m for m in CLIENT_MODULES if m in have)


async def _partner_of(session: AsyncSession, tenant: Tenant) -> Partner | None:
    """El partner del cliente: el de ``tenants.partner_id`` si está mapeado, y
    si no, el de su mapeo en ``partner_tenants``."""
    stmt = sa.select(PartnerTenant.partner_id).where(PartnerTenant.tenant_id == tenant.id)
    partner_ids = list((await session.execute(stmt)).scalars().all())
    if not partner_ids:
        return None
    chosen = tenant.partner_id if tenant.partner_id in partner_ids else partner_ids[0]
    return await session.get(Partner, chosen)


async def _whatsapp_connected(session: AsyncSession, tenant_id: uuid.UUID) -> bool:
    found = await session.scalar(
        sa.select(sa.func.count())
        .select_from(Channel)
        .where(
            Channel.tenant_id == tenant_id,
            Channel.type == ChannelType.WHATSAPP,
            Channel.status == ChannelStatus.ACTIVE,
        )
    )
    return bool(found)


async def _tenant(session: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise ClientAccessError("unknown_tenant", 404)
    return tenant


async def _members(session: AsyncSession, tenant_id: uuid.UUID) -> list[MemberRow]:
    now = _now()
    people = (
        await session.execute(
            sa.select(ClientMembership)
            .where(ClientMembership.tenant_id == tenant_id)
            .order_by(ClientMembership.created_at)
        )
    ).scalars()
    rows = [
        MemberRow(
            id=m.id,
            kind="member",
            email=m.email,
            name=m.display_name,
            status=m.status,
            since=m.accepted_at or m.created_at,
        )
        for m in people
    ]
    invitations = (
        await session.execute(
            sa.select(ClientInvitation)
            .where(
                ClientInvitation.tenant_id == tenant_id,
                ClientInvitation.status != ClientInvitationStatus.ACCEPTED.value,
            )
            .order_by(ClientInvitation.created_at)
        )
    ).scalars()
    for inv in invitations:
        status = inv.status
        if status == ClientInvitationStatus.PENDING.value and inv.expires_at <= now:
            status = ClientInvitationStatus.EXPIRED.value
        rows.append(
            MemberRow(
                id=inv.id,
                kind="invitation",
                email=inv.email,
                name=inv.display_name,
                status=status,
                expires_at=inv.expires_at,
            )
        )
    return rows


async def read_access(session: AsyncSession, tenant_id: uuid.UUID) -> AccessView:
    tenant = await _tenant(session, tenant_id)
    partner = await _partner_of(session, tenant)
    reason: str | None = None
    if tenant.status == TenantStatus.ARCHIVED:
        reason = "archived"
    elif partner is None:
        reason = "no_partner"
    access = await session.get(ClientAccess, tenant_id)
    return AccessView(
        eligible=reason is None,
        ineligible_reason=reason,
        partner=partner,
        whatsapp_connected=await _whatsapp_connected(session, tenant_id),
        enabled=bool(access and access.enabled),
        modules=access.ordered_modules() if access else (),
        members=await _members(session, tenant_id),
    )


def _audit(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor: str,
    action: str,
    after: dict[str, Any],
) -> None:
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor=actor,
            action=action,
            target=f"tenant:{tenant_id}",
            after_json=after,
        )
    )


async def _end_sessions(session: AsyncSession, user_ids: list[str]) -> int:
    closed = 0
    for raw in user_ids:
        try:
            principal_id = uuid.UUID(raw)
        except ValueError:  # pragma: no cover - las cuentas siempre son uuid
            continue
        closed += await console_identity.end_all_sessions(session, principal_id)
    return closed


async def set_access(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    enabled: bool,
    modules: list[str],
    actor: str,
) -> AccessView:
    """Enciende, apaga o cambia los módulos. Apagar cierra las sesiones de
    todas las personas del cliente (R1.7)."""
    tenant = await _tenant(session, tenant_id)
    partner = await _partner_of(session, tenant)
    if partner is None:
        raise ClientAccessError("no_partner", 409)
    if tenant.status == TenantStatus.ARCHIVED:
        raise ClientAccessError("archived", 409)
    unknown = set(modules) - set(CLIENT_MODULES)
    if unknown:
        raise ClientAccessError("unknown_module", 422)
    ordered = _ordered(modules)
    if enabled and not ordered:
        raise ClientAccessError("no_modules", 422)
    access = await session.get(ClientAccess, tenant_id)
    had_inbox = bool(access and ClientModule.INBOX.value in (access.modules or []))
    wants_inbox = ClientModule.INBOX.value in ordered
    if wants_inbox and not had_inbox and not await _whatsapp_connected(session, tenant_id):
        raise ClientAccessError("inbox_requires_whatsapp", 422)

    if access is None:
        access = ClientAccess(tenant_id=tenant_id, partner_id=partner.id)
        session.add(access)
    was_enabled = access.enabled
    access.partner_id = partner.id
    access.enabled = enabled
    access.modules = list(ordered)
    access.updated_by = actor
    access.updated_at = _now()
    await session.flush()

    if was_enabled and not enabled:
        active = (
            await session.execute(
                sa.select(ClientMembership.user_id).where(
                    ClientMembership.tenant_id == tenant_id,
                    ClientMembership.status == ClientMemberStatus.ACTIVE.value,
                )
            )
        ).scalars()
        await _end_sessions(session, list(active))

    # Sin Bandeja nadie atendería las conversaciones que un escalado dejó con
    # el agente callado: vuelven al agente (R11.5).
    if had_inbox and (not enabled or not wants_inbox):
        await inbox_lifecycle.release_escalated_for_tenant(session, tenant_id, actor=actor)

    _audit(
        session,
        tenant_id=tenant_id,
        actor=actor,
        action="client_access.updated",
        after={"enabled": enabled, "modules": list(ordered)},
    )
    await session.flush()
    return await read_access(session, tenant_id)


async def _lock_email(session: AsyncSession, email: str) -> None:
    await session.execute(
        sa.text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"console-email:{email}"}
    )


async def _home_of(session: AsyncSession, user_id: str) -> str | None:
    """Dónde vive ya una cuenta: ``partner``, ``client:<tenant>`` o ``None``."""
    if await session.scalar(
        sa.select(PartnerMembership.id).where(PartnerMembership.user_id == user_id)
    ):
        return "partner"
    tenant_id = await session.scalar(
        sa.select(ClientMembership.tenant_id).where(ClientMembership.user_id == user_id)
    )
    return f"client:{tenant_id}" if tenant_id else None


async def invite(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    email: str,
    name: str | None,
    actor: str,
) -> tuple[ClientInvitation, str]:
    """Una invitación pendiente. Devuelve ``(fila, token en claro)``; el token
    solo viaja en el correo y en la respuesta, nunca se guarda."""
    email = email.strip().lower()
    tenant = await _tenant(session, tenant_id)
    access = await session.get(ClientAccess, tenant_id)
    if access is None or not access.enabled:
        raise ClientAccessError("access_disabled", 409)
    await _lock_email(session, email)
    account = await console_identity.get_by_email(session, email)
    if account is not None:
        home = await _home_of(session, str(account.id))
        if home == "partner":
            raise ClientAccessError("account_is_partner_member", 409)
        if home == f"client:{tenant_id}":
            raise ClientAccessError("already_member", 409)
        if home is not None:
            raise ClientAccessError("account_is_other_client", 409)
    # Una invitación viva por correo y cliente: la anterior se retira.
    await session.execute(
        sa.update(ClientInvitation)
        .where(
            ClientInvitation.tenant_id == tenant_id,
            ClientInvitation.email == email,
            ClientInvitation.status == ClientInvitationStatus.PENDING.value,
        )
        .values(status=ClientInvitationStatus.REVOKED.value)
    )
    plaintext = secrets.token_urlsafe(32)
    invitation = ClientInvitation(
        id=uuid.uuid4(),
        partner_id=access.partner_id,
        tenant_id=tenant.id,
        email=email,
        display_name=(name or "").strip() or None,
        token_hash=hash_invitation_token(plaintext),
        status=ClientInvitationStatus.PENDING.value,
        invited_by=actor,
        expires_at=_now() + CLIENT_INVITATION_TTL,
    )
    session.add(invitation)
    _audit(
        session,
        tenant_id=tenant_id,
        actor=actor,
        action="client_member.invited",
        # El correo de la persona invitada no es secreto, y la Auditoría del
        # partner lo necesita para saber a quién se invitó.
        after={"email": email},
    )
    await session.flush()
    return invitation, plaintext


async def resend(
    session: AsyncSession, tenant_id: uuid.UUID, invitation_id: uuid.UUID, *, actor: str
) -> tuple[ClientInvitation, str]:
    """Otro enlace para la misma persona; el anterior deja de servir (R1.6)."""
    previous = await session.get(ClientInvitation, invitation_id)
    if previous is None or previous.tenant_id != tenant_id:
        if await _member(session, tenant_id, invitation_id) is not None:
            raise ClientAccessError("not_an_invitation", 409)
        raise ClientAccessError("unknown_member", 404)
    if previous.status == ClientInvitationStatus.ACCEPTED.value:
        raise ClientAccessError("not_an_invitation", 409)
    invitation, plaintext = await invite(
        session, tenant_id, email=previous.email, name=previous.display_name, actor=actor
    )
    _audit(
        session,
        tenant_id=tenant_id,
        actor=actor,
        action="client_member.resent",
        after={"email": previous.email},
    )
    await session.flush()
    return invitation, plaintext


async def _member(
    session: AsyncSession, tenant_id: uuid.UUID, member_id: uuid.UUID
) -> ClientMembership | None:
    member = await session.get(ClientMembership, member_id)
    return member if member is not None and member.tenant_id == tenant_id else None


async def revoke(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID, *, actor: str
) -> None:
    """Retira una invitación o a una persona. Idempotente. A una persona se le
    cierran todas las sesiones en la misma transacción (R1.7)."""
    member = await _member(session, tenant_id, item_id)
    if member is not None:
        if member.status != ClientMemberStatus.REVOKED.value:
            member.status = ClientMemberStatus.REVOKED.value
            member.updated_at = _now()
            await _end_sessions(session, [member.user_id])
            _audit(
                session,
                tenant_id=tenant_id,
                actor=actor,
                action="client_member.revoked",
                after={"email": member.email},
            )
            await session.flush()
        return
    invitation = await session.get(ClientInvitation, item_id)
    if invitation is None or invitation.tenant_id != tenant_id:
        raise ClientAccessError("unknown_member", 404)
    if invitation.status == ClientInvitationStatus.PENDING.value:
        invitation.status = ClientInvitationStatus.REVOKED.value
        _audit(
            session,
            tenant_id=tenant_id,
            actor=actor,
            action="client_member.revoked",
            after={"email": invitation.email},
        )
        await session.flush()


async def pending_invitation(session: AsyncSession, token: str) -> ClientInvitation | None:
    """La invitación de cliente viva detrás de un token, o ``None``."""
    invitation = await session.scalar(
        sa.select(ClientInvitation).where(
            ClientInvitation.token_hash == hash_invitation_token(token)
        )
    )
    if invitation is None or invitation.status != ClientInvitationStatus.PENDING.value:
        return None
    if invitation.expires_at <= _now():
        invitation.status = ClientInvitationStatus.EXPIRED.value
        await session.flush()
        return None
    access = await session.get(ClientAccess, invitation.tenant_id)
    if access is None or not access.enabled:
        return None
    return invitation


async def client_name(session: AsyncSession, invitation: ClientInvitation) -> str:
    mapping = await session.scalar(
        sa.select(PartnerTenant).where(
            PartnerTenant.partner_id == invitation.partner_id,
            PartnerTenant.tenant_id == invitation.tenant_id,
        )
    )
    if mapping is not None and mapping.client_name:
        return mapping.client_name
    tenant = await session.get(Tenant, invitation.tenant_id)
    return tenant.name if tenant else "—"


async def accept_invitation(
    session: AsyncSession,
    invitation: ClientInvitation,
    *,
    account: ConsoleAccount,
    display_name: str | None,
) -> ClientMembership:
    """Convierte la invitación en membresía. ``already_member`` si la cuenta ya
    es de un partner o de un cliente (la invariante entre tablas)."""
    if account.email.strip().lower() != invitation.email:
        raise ClientAccessError("email_mismatch", 409)
    await _lock_email(session, invitation.email)
    if await _home_of(session, str(account.id)) is not None:
        raise ClientAccessError("already_member", 409)
    now = _now()
    member = ClientMembership(
        id=uuid.uuid4(),
        partner_id=invitation.partner_id,
        tenant_id=invitation.tenant_id,
        user_id=str(account.id),
        email=invitation.email,
        display_name=display_name or invitation.display_name or account.display_name,
        status=ClientMemberStatus.ACTIVE.value,
        invited_by=invitation.invited_by,
        accepted_at=now,
    )
    session.add(member)
    await session.flush()
    invitation.status = ClientInvitationStatus.ACCEPTED.value
    invitation.accepted_at = now
    invitation.accepted_membership_id = member.id
    _audit(
        session,
        tenant_id=invitation.tenant_id,
        actor=f"client:{member.email}",
        action="client_member.joined",
        after={"email": member.email},
    )
    await session.flush()
    return member


__all__ = [
    "AccessView",
    "ClientAccessError",
    "MemberRow",
    "accept_invitation",
    "client_name",
    "invite",
    "pending_invitation",
    "read_access",
    "resend",
    "revoke",
    "set_access",
]
