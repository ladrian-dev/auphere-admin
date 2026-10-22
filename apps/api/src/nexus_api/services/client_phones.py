"""El teléfono de una persona de cliente — spec 031, R1, R2, R7 y research D3/D4.

**Identidad, no datos del cliente.** Entrar, renovar y registrar el destino
leen y escriben ``client_phones`` en transacciones de identidad, como
``resolve_client_principal`` lee las membresías: con el usuario de conexión y
sin el rol ``nexus_app``. Es lo que permite las dos reglas que cruzan
clientes —una sola sesión activa por instalación, y un solo dueño por destino
de avisos— sin tocar la RLS de los datos del cliente.

**Nada se borra.** Cerrar un teléfono lo marca revocado, con motivo y con quién
lo cerró, y le quita el destino de avisos: ningún aviso posterior sale hacia él
(R7.2). La fila se queda como constancia (constitución §IV).
"""

from __future__ import annotations

import hmac
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core import phone_credential as pc
from nexus_api.db.models import (
    DEFAULT_NOTICE_KINDS,
    AuditLog,
    ClientMembership,
    ClientMemberStatus,
    ClientPhone,
)

log = structlog.get_logger(__name__)

#: ``last_seen_at`` se toca como mucho una vez cada este tiempo (data-model).
TOUCH_INTERVAL = timedelta(minutes=5)


class PhoneClosed(Exception):
    """El teléfono ya no tiene sesión. Lleva el motivo para que la app lo diga."""

    def __init__(self, reason: str | None) -> None:
        super().__init__(f"phone closed: {reason}")
        self.reason = reason


class RefreshRejected(Exception):
    """La renovación no vale. Un solo rechazo, como el canje de códigos."""


@dataclass(frozen=True)
class PhoneTokens:
    phone_id: uuid.UUID
    access_token: str
    expires_in: int
    refresh_token: str


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _clean_name(raw: str) -> str:
    name = " ".join(raw.split())[:80]
    return name or "Teléfono"


def _audit(
    session: AsyncSession,
    *,
    phone: ClientPhone,
    actor: str,
    action: str,
    after: dict[str, Any],
) -> None:
    session.add(
        AuditLog(
            tenant_id=phone.tenant_id,
            actor=actor,
            action=action,
            target=f"client_phone:{phone.id}",
            after_json={"machine": phone.display_name, "platform": phone.platform, **after},
        )
    )


def _tokens(phone: ClientPhone, refresh: str) -> PhoneTokens:
    return PhoneTokens(
        phone_id=phone.id,
        access_token=pc.issue_access_token(
            phone_id=phone.id, generation=phone.credential_generation
        ),
        expires_in=int(pc.ACCESS_TTL.total_seconds()),
        refresh_token=refresh,
    )


async def active_membership(session: AsyncSession, principal_id: str) -> ClientMembership | None:
    """La membresía de cliente activa de una cuenta, o ``None``. Una cuenta es de
    un solo cliente (``uq_client_memberships_user``)."""
    member = await session.scalar(
        sa.select(ClientMembership).where(ClientMembership.user_id == principal_id)
    )
    if member is None or member.status != ClientMemberStatus.ACTIVE.value:
        return None
    return member


async def enroll(
    session: AsyncSession,
    *,
    membership: ClientMembership,
    platform: str,
    display_name: str,
    install_id: str,
    app_version: str,
    locale: str,
    method: str | None = None,
) -> PhoneTokens:
    """Da de alta el teléfono y devuelve sus credenciales (R1.4, R2.4).

    ``method`` (``password`` o ``google``) queda en la auditoría: quién entró y
    por qué puerta (R7.6).

    Antes revoca, **sea de quien sea y de cualquier cliente**, la sesión activa
    que tuviera esta misma instalación: un teléfono, una persona (data-model
    §0158). La persona que entra en una recepción compartida no deja detrás la
    sesión de la anterior.
    """
    previous = (
        await session.scalars(
            sa.select(ClientPhone)
            .where(ClientPhone.install_id == install_id, ClientPhone.revoked_at.is_(None))
            .with_for_update()
        )
    ).all()
    for old in previous:
        revoke(session, old, reason="signed_out", by="system")

    now = _now()
    refresh = pc.new_refresh_token()
    phone = ClientPhone(
        id=uuid.uuid4(),
        tenant_id=membership.tenant_id,
        partner_id=membership.partner_id,
        client_membership_id=membership.id,
        principal_id=membership.user_id,
        platform=platform,
        display_name=_clean_name(display_name),
        install_id=install_id,
        app_version=app_version,
        refresh_hash=pc.hash_refresh_token(refresh),
        refresh_prev_hash=None,
        refresh_rotated_at=now,
        credential_generation=1,
        notice_kinds=list(DEFAULT_NOTICE_KINDS),
        locale=locale if locale in ("es", "en") else "es",
        last_seen_at=now,
        enrolled_at=now,
    )
    session.add(phone)
    await session.flush()
    _audit(
        session,
        phone=phone,
        actor=f"client:{membership.email}",
        action="client_phone.signed_in",
        after={"email": membership.email, **({"method": method} if method else {})},
    )
    return _tokens(phone, refresh)


async def refresh(
    session: AsyncSession, *, refresh_token: str, app_version: str | None = None
) -> PhoneTokens:
    """Rota la renovación (R2.1). Ver ``contracts/phone-auth.md`` §Renovar.

    * La vigente → rota y devuelve otra.
    * La anterior, dentro de 60 s → rota otra vez (la app que se despertó dos
      veces no pierde la sesión).
    * La anterior fuera de la gracia → alguien guardó una credencial vieja:
      se cierra el teléfono (``refresh_reused``).
    * 90 días sin uso → se cierra (``abandoned``, R2.2).
    """
    digest = pc.hash_refresh_token(refresh_token)
    phone = await session.scalar(
        sa.select(ClientPhone)
        .where(sa.or_(ClientPhone.refresh_hash == digest, ClientPhone.refresh_prev_hash == digest))
        .with_for_update()
    )
    if phone is None:
        raise RefreshRejected
    if phone.revoked_at is not None:
        raise PhoneClosed(phone.revoked_reason)
    now = _now()
    if pc.is_abandoned(phone.last_seen_at, now=now):
        revoke(session, phone, reason="abandoned", by="system")
        raise PhoneClosed("abandoned")

    is_current = hmac.compare_digest(phone.refresh_hash, digest)
    if not is_current:
        within_grace = now - _aware(phone.refresh_rotated_at) <= pc.REFRESH_GRACE
        if not within_grace:
            revoke(session, phone, reason="refresh_reused", by="system")
            log.warning("client_phones.refresh_reused", phone_id=str(phone.id))
            raise PhoneClosed("refresh_reused")

    new_refresh = pc.new_refresh_token()
    phone.refresh_prev_hash = phone.refresh_hash
    phone.refresh_hash = pc.hash_refresh_token(new_refresh)
    phone.refresh_rotated_at = now
    phone.credential_generation += 1
    phone.last_seen_at = now
    if app_version:
        phone.app_version = app_version[:32]
    await session.flush()
    return _tokens(phone, new_refresh)


def revoke(session: AsyncSession, phone: ClientPhone, *, reason: str, by: str) -> bool:
    """Cierra un teléfono. Idempotente: uno ya cerrado no cambia de motivo.

    Quita el destino de avisos en el mismo paso, así el reparto no puede
    enviarle nada aunque lea la fila un instante antes de ver ``revoked_at``.
    """
    if phone.revoked_at is not None:
        return False
    phone.revoked_at = _now()
    phone.revoked_reason = reason
    phone.revoked_by = by
    phone.push_token = None
    phone.push_provider = None
    phone.push_token_updated_at = None
    if reason in ("closed_by_person", "closed_by_auphere"):
        action = "client_phone.closed"
    elif reason == "signed_out" and by != "system":
        action = "client_phone.signed_out"
    else:
        action = "client_phone.revoked"
    member_email = by.removeprefix("client:") if by.startswith("client:") else None
    _audit(
        session,
        phone=phone,
        actor=by,
        action=action,
        after={"reason": reason, **({"email": member_email} if member_email else {})},
    )
    return True


async def revoke_where(
    session: AsyncSession,
    *,
    reason: str,
    by: str,
    tenant_id: uuid.UUID | None = None,
    principal_ids: Iterable[str] | None = None,
) -> int:
    """Cierra los teléfonos activos de un cliente o de unas personas.

    Lo llaman las revocaciones de siempre (R7.2): apagar el acceso, quitar a
    una persona, restablecer la contraseña.
    """
    stmt = sa.select(ClientPhone).where(ClientPhone.revoked_at.is_(None)).with_for_update()
    if tenant_id is not None:
        stmt = stmt.where(ClientPhone.tenant_id == tenant_id)
    if principal_ids is not None:
        ids = [str(p) for p in principal_ids]
        if not ids:
            return 0
        stmt = stmt.where(ClientPhone.principal_id.in_(ids))
    if tenant_id is None and principal_ids is None:  # pragma: no cover - error de programación
        raise ValueError("revoke_where necesita un cliente o unas personas")
    closed = 0
    for phone in (await session.scalars(stmt)).all():
        if revoke(session, phone, reason=reason, by=by):
            closed += 1
    return closed


async def touch(session: AsyncSession, phone: ClientPhone) -> None:
    """Marca el uso, como mucho una vez cada cinco minutos (data-model)."""
    now = _now()
    if now - _aware(phone.last_seen_at) >= TOUCH_INTERVAL:
        await session.execute(
            sa.update(ClientPhone).where(ClientPhone.id == phone.id).values(last_seen_at=now)
        )


async def register_push(
    session: AsyncSession,
    phone: ClientPhone,
    *,
    provider: str,
    token: str,
    apns_environment: str | None,
) -> None:
    """Guarda el destino de avisos de este teléfono (R8.2).

    **Un destino, un dueño** (data-model §0158): si Apple o Google reutilizaron
    el destino, se quita de cualquier otra fila, de cualquier cliente. Corre en
    la transacción de identidad, por eso puede.
    """
    now = _now()
    await session.execute(
        sa.update(ClientPhone)
        .where(ClientPhone.push_token == token, ClientPhone.id != phone.id)
        .values(push_token=None, push_provider=None, push_token_updated_at=None)
    )
    phone.push_provider = provider
    phone.push_token = token
    phone.push_token_updated_at = now
    phone.apns_environment = apns_environment if provider == "apns" else None
    await session.flush()


async def for_membership(
    session: AsyncSession, *, tenant_id: uuid.UUID, membership_id: uuid.UUID, limit: int = 20
) -> list[ClientPhone]:
    """Los teléfonos de una persona, activos primero y luego los cerrados más
    recientes. Para el admin (R7.4): ve lo que hay y lo que hubo."""
    rows = await session.scalars(
        sa.select(ClientPhone)
        .where(
            ClientPhone.tenant_id == tenant_id,
            ClientPhone.client_membership_id == membership_id,
        )
        .order_by(ClientPhone.revoked_at.is_not(None), ClientPhone.last_seen_at.desc())
        .limit(limit)
    )
    return list(rows.all())


__all__ = [
    "PhoneClosed",
    "PhoneTokens",
    "RefreshRejected",
    "active_membership",
    "enroll",
    "for_membership",
    "refresh",
    "register_push",
    "revoke",
    "revoke_where",
    "touch",
]
