"""Identidad de la consola de partners: quién entra y con qué acceso.

Este módulo es la mitad de servidor de la decisión "la consola deja de
tener base de datos" (supersede parcialmente ADR-030 D2). El BFF de
``apps/console`` ya no habla con Postgres: llama a ``/console/auth/*`` con
su token de servicio y guarda en la cookie un **token opaco** que solo
significa algo aquí.

Desde ADR-034 (Fase 0) las primitivas —scrypt, token de sesión, bloqueo
por intentos, hash señuelo— viven en :mod:`nexus_api.services.identity`,
porque el panel de operador se muda al mismo modelo y duplicarlas
garantizaría que un día se arregla una y no la otra. Aquí queda **lo que
es propio de la consola**: la pertenencia a un partner y la clasificación
del acceso.

Ese reparto no es estético. Lo genérico —cómo se comprueba una
contraseña— y lo específico —qué te da derecho a entrar— son cosas
distintas, y la consola resuelve lo segundo contra
``public.partner_memberships``, que sigue siendo la única verdad de
pertenencia y se vuelve a comprobar en cada petición real
(``require_console_principal``), sin fiarse del BFF.

Las constantes y funciones de :mod:`~nexus_api.services.identity` se
reexportan tal cual para no tocar ni un llamante.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import (
    ConsoleAccount,
    ConsoleSession,
    MembershipStatus,
    Partner,
    PartnerMembership,
    PartnerStatus,
)
from nexus_api.services.identity import (
    LOCKOUT_DURATION,
    MAX_FAILED_ATTEMPTS,
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    SESSION_TTL,
    IdentityStore,
    PasswordPolicyError,
    hash_password,
    hash_session_token,
    needs_rehash,
    normalize_email,
    validate_password,
    verify_password,
)

log = structlog.get_logger(__name__)

#: El almacén de la consola. Un objeto por esquema de identidad: aquí
#: ``console_auth``, en el panel de operador ``operator_auth``. Que sean
#: instancias distintas del mismo tipo es lo que hace imposible que una
#: cuenta de partner resuelva como operador.
_STORE = IdentityStore(
    account_model=ConsoleAccount,
    session_model=ConsoleSession,
    log_prefix="console_identity",
)

# ── vista del principal ───────────────────────────────────────────────

#: Estados que la consola sabe pintar (``apps/console/src/lib/principal.ts``).
ACCESS_OK = "ok"
ACCESS_NO_MEMBERSHIP = "no_membership"
ACCESS_SUSPENDED = "suspended"
ACCESS_DISABLED = "disabled"


@dataclass(frozen=True)
class PrincipalView:
    """Quién es, dónde y si puede entrar.

    ``access`` replica exactamente los casos que hoy distingue el BFF: sin
    membresía, membresía o partner suspendidos, consola apagada para ese
    partner, o todo bien. **El login funciona en los cuatro**: lo que
    cambia es que la consola enseña la página "sin acceso" en vez del
    panel — que es lo que ya hacía.
    """

    account: ConsoleAccount
    access: str
    membership: PartnerMembership | None = None
    partner: Partner | None = None

    @property
    def ok(self) -> bool:
        return self.access == ACCESS_OK


async def load_principal_view(session: AsyncSession, account: ConsoleAccount) -> PrincipalView:
    """Une la cuenta con ``public.partner_memberships`` (la única verdad de
    pertenencia) y clasifica el acceso. Una consulta indexada."""
    row = (
        await session.execute(
            sa.select(PartnerMembership, Partner)
            .join(Partner, Partner.id == PartnerMembership.partner_id)
            .where(PartnerMembership.user_id == str(account.id))
            .limit(1)
        )
    ).first()
    if row is None:
        return PrincipalView(account=account, access=ACCESS_NO_MEMBERSHIP)
    membership: PartnerMembership = row[0]
    partner: Partner = row[1]
    if membership.status != MembershipStatus.ACTIVE.value:
        return PrincipalView(
            account=account, access=ACCESS_SUSPENDED, membership=membership, partner=partner
        )
    if partner.status != PartnerStatus.ACTIVE.value:
        return PrincipalView(
            account=account, access=ACCESS_SUSPENDED, membership=membership, partner=partner
        )
    if not partner.console_enabled:
        return PrincipalView(
            account=account, access=ACCESS_DISABLED, membership=membership, partner=partner
        )
    return PrincipalView(account=account, access=ACCESS_OK, membership=membership, partner=partner)


# ── cuentas y sesiones (delegan en el almacén) ────────────────────────


async def get_by_email(session: AsyncSession, email: str) -> ConsoleAccount | None:
    account: ConsoleAccount | None = await _STORE.get_by_email(session, email)
    return account


async def create_account(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    display_name: str | None = None,
    locale: str = "es",
    account_id: uuid.UUID | None = None,
) -> ConsoleAccount:
    account: ConsoleAccount = await _STORE.create_account(
        session,
        email=email,
        password=password,
        display_name=display_name,
        locale=locale,
        account_id=account_id,
    )
    return account


async def set_password(session: AsyncSession, account: ConsoleAccount, password: str) -> None:
    await _STORE.set_password(session, account, password)


async def authenticate(
    session: AsyncSession, *, email: str, password: str
) -> ConsoleAccount | None:
    account: ConsoleAccount | None = await _STORE.authenticate(
        session, email=email, password=password
    )
    return account


async def start_session(
    session: AsyncSession,
    account: ConsoleAccount,
    *,
    ip: str | None = None,
    user_agent: str | None = None,
) -> tuple[str, datetime]:
    return await _STORE.start_session(session, account, ip=ip, user_agent=user_agent)


async def resolve_session(session: AsyncSession, token: str) -> ConsoleAccount | None:
    account: ConsoleAccount | None = await _STORE.resolve_session(session, token)
    return account


async def end_session(session: AsyncSession, token: str) -> None:
    await _STORE.end_session(session, token)


__all__ = [
    "ACCESS_DISABLED",
    "ACCESS_NO_MEMBERSHIP",
    "ACCESS_OK",
    "ACCESS_SUSPENDED",
    "LOCKOUT_DURATION",
    "MAX_FAILED_ATTEMPTS",
    "PASSWORD_MAX_LENGTH",
    "PASSWORD_MIN_LENGTH",
    "SESSION_TTL",
    "PasswordPolicyError",
    "PrincipalView",
    "authenticate",
    "create_account",
    "end_session",
    "get_by_email",
    "hash_password",
    "hash_session_token",
    "load_principal_view",
    "needs_rehash",
    "normalize_email",
    "resolve_session",
    "set_password",
    "start_session",
    "validate_password",
    "verify_password",
]
