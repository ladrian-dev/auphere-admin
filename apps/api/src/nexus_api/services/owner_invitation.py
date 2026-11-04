"""La invitación de propietario que emite Auphere — spec 052.

Crear un partner desde el panel invita a su propietario, y desde la pestaña
Equipo se invita, se reenvía y se revoca. Aquí viven las reglas y solo aquí. Una
invitación **es de Auphere** si es de rol propietario y no la emitió ninguna
persona del partner (``research.md``, R1).

Dos tiempos, siempre:

1. **Dentro de la transacción de quien llama**: ``issue_for_new_partner``,
   ``invite``, ``resend`` y ``revoke``. Ninguna confirma. Devuelven lo emitido.
2. **Fuera de ella**: ``deliver`` envía y apunta la fecha. Un correo que no sale
   no deshace nada, y nunca lanza: quien está delante tiene que ver el resultado.

Todo se limita al partner de la ruta; el llamante no elige otro, y no se toca
ninguna tabla de tenant (``tests/isolation/test_owner_invitation_scope.py``).
El token solo existe en el correo y en la respuesta: no entra en la auditoría ni
en el registro de este módulo.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Literal

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    ClientMembership,
    InvitationStatus,
    Partner,
    PartnerInvitation,
    PartnerMembership,
    PartnerRole,
)
from nexus_api.repositories import AuditRepository
from nexus_api.repositories.partner_membership import (
    PartnerInvitationRepository,
    PartnerMembershipRepository,
    invitation_is_live_clause,
)
from nexus_api.services import console_identity
from nexus_api.services.email import send_template
from nexus_api.services.email_catalog import (
    ROLE_LABELS,
    EmailKind,
    console_link,
    email_locale,
    format_day,
)

log = structlog.get_logger(__name__)

ACTION_INVITED: Final = "partner.owner_invited"
ACTION_RESENT: Final = "partner.owner_invitation_resent"
ACTION_REVOKED: Final = "partner.owner_invitation_revoked"

ACCEPT_PATH: Final = "/invite/{token}"
INVITER: Final = "Auphere"

#: CE-002: el resultado en menos de 30 segundos también sin respuesta del
#: proveedor. El ``timeout`` de ``send_template`` es por fase de ``httpx``, y
#: conexión, escritura y lectura pueden sumar 60 s: esto limita el total.
SEND_DEADLINE_S: float = 25.0


class OwnerInvitationError(Exception):
    """Una negativa con nombre. ``code`` es vocabulario cerrado que el panel
    traduce; ``status``, el HTTP."""

    def __init__(self, code: str, status: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class Issued:
    """Lo emitido, con lo que hace falta para enviarlo una vez confirmado."""

    invitation: PartnerInvitation
    token: str
    locale: str
    partner_id: uuid.UUID
    partner_name: str


@dataclass(frozen=True)
class Delivered:
    """El resultado de un envío. Es lo único que lleva el enlace."""

    id: uuid.UUID
    email: str
    role: str
    status: str
    expires_at: datetime
    created_at: datetime
    last_sent_at: datetime | None
    email_sent: bool
    accept_url: str


@dataclass(frozen=True)
class Revoked:
    id: uuid.UUID
    email: str
    status: str
    changed: bool


@dataclass(frozen=True)
class OwnerState:
    invitations: list[PartnerInvitation]
    has_active_owner: bool
    can_invite: bool
    can_resend: bool
    block: Literal["suspended", "console_off"] | None
    expired_email: str | None
    expired_at: datetime | None
    suggested_email: str | None


def _now() -> datetime:
    return datetime.now(UTC)


def is_from_auphere(invitation: PartnerInvitation) -> bool:
    return invitation.role == PartnerRole.OWNER.value and invitation.invited_by is None


def _from_auphere_clause() -> sa.ColumnElement[bool]:
    return sa.and_(
        PartnerInvitation.role == PartnerRole.OWNER.value,
        PartnerInvitation.invited_by.is_(None),
    )


def _is_expired(invitation: PartnerInvitation, now: datetime) -> bool:
    if invitation.status == InvitationStatus.EXPIRED.value:
        return True
    return invitation.status == InvitationStatus.PENDING.value and invitation.expires_at <= now


# ── lo que se comprueba ───────────────────────────────────────────────────────


async def _lock_partner(session: AsyncSession, partner_id: uuid.UUID) -> Partner:
    """Serializa las emisiones de un partner: la segunda de dos simultáneas ve
    la fila de la primera (R3.5).

    ``FOR NO KEY UPDATE`` y no ``FOR UPDATE``: aceptar inserta una pertenencia con
    FK a ``partners``, que toma ``FOR KEY SHARE``, y con la otra forma reenviar y
    aceptar a la vez podrían interbloquearse.
    """
    partner = await session.scalar(
        sa.select(Partner)
        .where(Partner.id == partner_id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    if partner is None:
        raise OwnerInvitationError("partner_not_found", 404)
    return partner


async def _lock_invitation(
    session: AsyncSession, partner_id: uuid.UUID, invitation_id: uuid.UUID
) -> PartnerInvitation:
    """La invitación de Auphere de **este** partner. Una de otro, una inexistente
    y una que no es de Auphere dan la misma negativa, byte a byte (R7.2)."""
    invitation = await session.scalar(
        sa.select(PartnerInvitation)
        .where(
            PartnerInvitation.partner_id == partner_id,
            PartnerInvitation.id == invitation_id,
            _from_auphere_clause(),
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if invitation is None:
        raise OwnerInvitationError("invitation_not_found", 404)
    return invitation


async def _has_active_owner(session: AsyncSession, partner_id: uuid.UUID) -> bool:
    return await PartnerMembershipRepository(session).count_active_owners(partner_id) > 0


async def _refuse_unless_open(session: AsyncSession, partner: Partner) -> None:
    """R3.4, R3.6, R3.7, R4.4."""
    if partner.status != "active":
        raise OwnerInvitationError("partner_suspended")
    if not partner.console_enabled:
        raise OwnerInvitationError("console_off")
    if await _has_active_owner(session, partner.id):
        raise OwnerInvitationError("has_active_owner")


async def _check_address(session: AsyncSession, partner_id: uuid.UUID, email: str) -> str:
    """Rechaza una dirección que ya vive en algún sitio y devuelve su idioma.

    ``accept`` mira la cuenta, así que se mira la cuenta. Y también la copia de la
    dirección en la pertenencia, porque hay filas cuyo ``user_id`` no es una cuenta
    de esta base. Da igual si esa persona sigue activa: ``accept`` tampoco lo
    distingue, y por eso esta invitación fallaría al aceptarla (R1.5, R3.8).
    """
    account = await console_identity.get_by_email(session, email)
    user_id = str(account.id) if account is not None else None

    in_partners = [sa.func.lower(PartnerMembership.email) == email]
    in_clients = [sa.func.lower(ClientMembership.email) == email]
    if user_id is not None:
        in_partners.append(PartnerMembership.user_id == user_id)
        in_clients.append(ClientMembership.user_id == user_id)

    homes = set(
        await session.scalars(sa.select(PartnerMembership.partner_id).where(sa.or_(*in_partners)))
    )
    if partner_id in homes:
        raise OwnerInvitationError("already_in_team")
    if homes or await session.scalar(
        sa.select(ClientMembership.id).where(sa.or_(*in_clients)).limit(1)
    ):
        raise OwnerInvitationError("address_has_own_console")
    return email_locale(account.locale) if account is not None else "es"


# ── emitir ────────────────────────────────────────────────────────────────────


async def _issue(
    session: AsyncSession,
    partner: Partner,
    *,
    email: str,
    locale: str,
    actor: str,
    action: str,
    replaces: str | None,
) -> Issued:
    invitation, token = await PartnerInvitationRepository(session).create(
        partner_id=partner.id,
        email=email,
        role=PartnerRole.OWNER.value,
        invited_by=None,
    )
    before: dict[str, str | None] = {}
    after: dict[str, str | None] = {"email": invitation.email, "role": invitation.role}
    # R1.10: el contacto solo sigue a la invitación si estaba vacío o era la
    # dirección que esta sustituye. Uno escrito a mano no se toca.
    contact = (partner.contact_email or "").strip().lower()
    if contact != invitation.email and (not contact or contact == replaces):
        before["contact_email"] = partner.contact_email
        after["contact_email"] = invitation.email
        partner.contact_email = invitation.email
        await session.flush()
    await AuditRepository(session).record(
        actor=actor,
        action=action,
        target=f"partner:{partner.id}",
        before=before or None,
        after=after,
        platform=True,
    )
    return Issued(
        invitation=invitation,
        token=token,
        locale=locale,
        partner_id=partner.id,
        partner_name=partner.name,
    )


async def issue_for_new_partner(
    session: AsyncSession, partner: Partner, *, email: str, actor: str
) -> Issued:
    """La invitación de un partner que acaba de nacer, en su misma transacción."""
    locale = await _check_address(session, partner.id, email)
    return await _issue(
        session,
        partner,
        email=email,
        locale=locale,
        actor=actor,
        action=ACTION_INVITED,
        replaces=None,
    )


async def _replaceable_address(session: AsyncSession, partner_id: uuid.UUID) -> str | None:
    """La dirección a la que sustituye una invitación nueva: la de la última de
    Auphere, si se revocó o caducó. Una aceptada no se sustituye: esa persona ya
    entró, y que hoy no esté no pone su dirección a disposición de nadie."""
    last = await session.scalar(
        sa.select(PartnerInvitation)
        .where(PartnerInvitation.partner_id == partner_id, _from_auphere_clause())
        .order_by(PartnerInvitation.created_at.desc(), PartnerInvitation.id.desc())
        .limit(1)
    )
    if last is None or last.status == InvitationStatus.ACCEPTED.value:
        return None
    return last.email


async def invite(session: AsyncSession, partner_id: uuid.UUID, *, email: str, actor: str) -> Issued:
    """Invita al propietario de un partner que no lo tiene (R3)."""
    partner = await _lock_partner(session, partner_id)
    await _refuse_unless_open(session, partner)
    now = _now()
    if await session.scalar(
        sa.select(PartnerInvitation.id)
        .where(
            PartnerInvitation.partner_id == partner_id,
            _from_auphere_clause(),
            invitation_is_live_clause(now),
        )
        .limit(1)
    ):
        raise OwnerInvitationError("invitation_pending")
    locale = await _check_address(session, partner_id, email)
    if await session.scalar(
        sa.select(PartnerInvitation.id)
        .where(
            PartnerInvitation.partner_id == partner_id,
            PartnerInvitation.email == email,
            invitation_is_live_clause(now),
        )
        .limit(1)
    ):
        # Viva y a esa dirección, pero no es de Auphere: la emitió el partner o
        # la dejó el script con otro rol. No se pisa desde aquí.
        raise OwnerInvitationError("address_already_invited")
    # R3.9: nada marca una vencida hasta que alguien abre su enlace. Se marca
    # antes de crear porque el índice único solo mira ``status = 'pending'`` y
    # una fila vencida impediría reinvitar a esa misma dirección.
    await session.execute(
        sa.update(PartnerInvitation)
        .where(
            PartnerInvitation.partner_id == partner_id,
            PartnerInvitation.status == InvitationStatus.PENDING.value,
            PartnerInvitation.expires_at <= now,
        )
        .values(status=InvitationStatus.EXPIRED.value)
        .execution_options(synchronize_session=False)
    )
    replaces = await _replaceable_address(session, partner_id)
    return await _issue(
        session,
        partner,
        email=email,
        locale=locale,
        actor=actor,
        action=ACTION_INVITED,
        replaces=replaces,
    )


async def resend(
    session: AsyncSession, partner_id: uuid.UUID, invitation_id: uuid.UUID, *, actor: str
) -> Issued:
    """Un enlace nuevo para la misma dirección, con el plazo completo (R4). Solo
    se guarda el hash del token: no hay nada que volver a enviar, así que la fila
    anterior muere y nace otra."""
    partner = await _lock_partner(session, partner_id)
    previous = await _lock_invitation(session, partner_id, invitation_id)
    # Primero qué le pasó a la invitación: si la persona acaba de aceptar, también
    # hay propietario activo, y lo que hay que decir es que aceptó (R4.5).
    if previous.status == InvitationStatus.ACCEPTED.value:
        raise OwnerInvitationError("invitation_accepted")
    if previous.status == InvitationStatus.REVOKED.value:
        raise OwnerInvitationError("invitation_revoked")
    if _is_expired(previous, _now()):
        raise OwnerInvitationError("invitation_expired")
    await _refuse_unless_open(session, partner)
    # La dirección pudo irse a otro sitio mientras la invitación seguía viva, y
    # este enlace fallaría al aceptarlo.
    locale = await _check_address(session, partner_id, previous.email)
    email = previous.email
    previous.status = InvitationStatus.REVOKED.value
    # Antes de crear: el índice único no admite dos pendientes de una dirección.
    await session.flush()
    return await _issue(
        session,
        partner,
        email=email,
        locale=locale,
        actor=actor,
        action=ACTION_RESENT,
        replaces=email,
    )


async def revoke(
    session: AsyncSession, partner_id: uuid.UUID, invitation_id: uuid.UUID, *, actor: str
) -> Revoked:
    """Deja el enlace sin efecto, sea cual sea el estado del partner, y sin avisar
    a nadie (R5). ``changed`` dice si esta llamada hizo algo: revocar una fila
    antigua no dice nada del enlace que la sustituyó."""
    if await session.get(Partner, partner_id) is None:
        raise OwnerInvitationError("partner_not_found", 404)
    invitation = await _lock_invitation(session, partner_id, invitation_id)
    if invitation.status == InvitationStatus.ACCEPTED.value:
        raise OwnerInvitationError("invitation_accepted")
    if _is_expired(invitation, _now()):
        return Revoked(
            invitation.id, invitation.email, InvitationStatus.EXPIRED.value, changed=False
        )
    if invitation.status == InvitationStatus.REVOKED.value:
        return Revoked(invitation.id, invitation.email, invitation.status, changed=False)
    invitation.status = InvitationStatus.REVOKED.value
    await session.flush()
    await AuditRepository(session).record(
        actor=actor,
        action=ACTION_REVOKED,
        target=f"partner:{partner_id}",
        after={"email": invitation.email, "role": invitation.role},
        platform=True,
    )
    return Revoked(invitation.id, invitation.email, invitation.status, changed=True)


# ── enviar, fuera de la transacción ───────────────────────────────────────────


def _subject(partner_name: str, locale: str) -> str:
    # No el de la consola, «{quien} te ha invitado a unirte a {partner} en
    # Auphere»: con Auphere de quien invita se leería dos veces.
    if locale == "en":
        return f"{INVITER} invited you to join {partner_name}"
    return f"{INVITER} te ha invitado a unirte a {partner_name}"


async def _send(issued: Issued, accept_url: str) -> bool:
    invitation = issued.invitation
    try:
        return await asyncio.wait_for(
            send_template(
                EmailKind.TEAM_INVITE,
                to=invitation.email,
                subject=_subject(issued.partner_name, issued.locale),
                variables={
                    "INVITER": INVITER,
                    "PARTNER_NAME": issued.partner_name,
                    "ROLE_LABEL": ROLE_LABELS[issued.locale][invitation.role],
                    "EXPIRES_ON": format_day(invitation.expires_at.date(), issued.locale),
                    "ACCEPT_URL": accept_url,
                },
                locale=issued.locale,
                partner_id=issued.partner_id,
            ),
            timeout=SEND_DEADLINE_S,
        )
    except TimeoutError:
        log.error(
            "owner_invitation.send_timeout",
            partner_id=str(issued.partner_id),
            invitation_id=str(invitation.id),
        )
        return False
    except Exception as exc:  # R2.3: un error interno también es «no salió».
        # Solo el tipo: el texto de una excepción puede llevar el enlace (R6.5).
        log.error(
            "owner_invitation.send_error",
            partner_id=str(issued.partner_id),
            invitation_id=str(invitation.id),
            error_type=type(exc).__name__,
        )
        return False


async def _record_sent(issued: Issued) -> datetime:
    """En su propia sesión: quien llama ya confirmó y, si esto falla, su sesión
    sigue sana para responder."""
    sent_at = _now()
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(
            sa.update(PartnerInvitation)
            .where(
                PartnerInvitation.id == issued.invitation.id,
                PartnerInvitation.partner_id == issued.partner_id,
            )
            .values(last_sent_at=sent_at)
        )
    return sent_at


async def deliver(issued: Issued) -> Delivered:
    """Envía y dice qué pasó. Nunca lanza: el partner y la invitación ya existen,
    y este resultado es la única vez que el enlace se puede enseñar."""
    invitation = issued.invitation
    accept_url = console_link(ACCEPT_PATH.format(token=issued.token))
    sent = await _send(issued, accept_url)
    sent_at: datetime | None = None
    if sent:
        try:
            sent_at = await _record_sent(issued)
        except Exception as exc:
            # El correo salió. Perder el enlace por no poder apuntarlo sería peor
            # que el «no consta» que dirá la ficha.
            log.error(
                "owner_invitation.sent_at_not_recorded",
                partner_id=str(issued.partner_id),
                invitation_id=str(invitation.id),
                error_type=type(exc).__name__,
            )
    return Delivered(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        status=invitation.status,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
        last_sent_at=sent_at,
        email_sent=sent,
        accept_url=accept_url,
    )


# ── lo que se pinta ───────────────────────────────────────────────────────────


async def read_state(session: AsyncSession, partner: Partner) -> OwnerState:
    """Las invitaciones vivas del partner y qué se puede hacer (R2.6, R3).

    Lectura pura: no marca ni envía nada. Una vencida no es viva aunque nadie
    haya abierto su enlace (R3.9).
    """
    now = _now()
    invitations = list(
        await session.scalars(
            sa.select(PartnerInvitation)
            .where(PartnerInvitation.partner_id == partner.id, invitation_is_live_clause(now))
            .order_by(PartnerInvitation.created_at)
        )
    )
    has_owner = await _has_active_owner(session, partner.id)
    block: Literal["suspended", "console_off"] | None = None
    if partner.status != "active":
        block = "suspended"
    elif not partner.console_enabled:
        block = "console_off"

    can_resend = not has_owner and block is None
    can_invite = can_resend and not any(is_from_auphere(i) for i in invitations)

    expired_email: str | None = None
    expired_at: datetime | None = None
    if not has_owner:
        last = await session.scalar(
            sa.select(PartnerInvitation)
            .where(PartnerInvitation.partner_id == partner.id, _from_auphere_clause())
            .order_by(PartnerInvitation.created_at.desc(), PartnerInvitation.id.desc())
            .limit(1)
        )
        if last is not None and _is_expired(last, now):
            expired_email, expired_at = last.email, last.expires_at

    suggested = (expired_email or partner.contact_email) if can_invite else None
    return OwnerState(
        invitations=invitations,
        has_active_owner=has_owner,
        can_invite=can_invite,
        can_resend=can_resend,
        block=block,
        expired_email=expired_email,
        expired_at=expired_at,
        suggested_email=suggested,
    )


__all__ = [
    "ACCEPT_PATH",
    "ACTION_INVITED",
    "ACTION_RESENT",
    "ACTION_REVOKED",
    "Delivered",
    "Issued",
    "OwnerInvitationError",
    "OwnerState",
    "Revoked",
    "deliver",
    "invite",
    "is_from_auphere",
    "issue_for_new_partner",
    "read_state",
    "resend",
    "revoke",
]
