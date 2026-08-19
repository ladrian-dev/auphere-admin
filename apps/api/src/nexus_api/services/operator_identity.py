"""Identidad del panel de operador: quién entra y si sigue teniendo acceso.

Mitad de servidor de ADR-034. El BFF de ``apps/admin`` deja de hablar con
Postgres —no puede: la Aurora de producción es privada y él vive en
Vercel— y pasa a llamar a ``/admin/auth/*`` con su token de servicio,
guardando en la cookie un **token opaco** que solo significa algo aquí.

Las primitivas (scrypt, token de sesión, bloqueo por intentos, hash
señuelo) vienen de :mod:`nexus_api.services.identity`, compartidas con la
consola. Lo propio de este módulo es corto a propósito, porque la
autorización del panel también lo es:

**No hay roles.** ADR-009 define el panel como god-mode del equipo de
Auphere: quien entra puede todo. La única distinción que existe es si la
cuenta sigue habilitada (``disabled_at``), que es lo que hace falta cuando
alguien deja el equipo. Inventar una rejilla de permisos sin un caso que
la pida sería complejidad especulativa — y la Fase 2 de ADR-009, cuando
llegue, es sobre cómo viaja la autorización, no sobre inventar roles.

Y una frontera que conviene no borrar: este módulo NUNCA consulta
``console_auth``. Un principal de partner no puede resolver aquí porque
son dos esquemas distintos, no dos filas con un flag.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import OperatorAccount, OperatorSession
from nexus_api.services.identity import (
    LOCKOUT_DURATION,
    MAX_FAILED_ATTEMPTS,
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    SESSION_TTL,
    IdentityStore,
    PasswordPolicyError,
    aware,
    hash_password,
    hash_session_token,
    needs_rehash,
    normalize_email,
    now,
    validate_password,
    verify_password,
)

log = structlog.get_logger(__name__)

_STORE = IdentityStore(
    account_model=OperatorAccount,
    session_model=OperatorSession,
    log_prefix="operator_identity",
)

#: Estados que el panel sabe pintar. Deliberadamente dos: el panel no tiene
#: pertenencia que resolver, así que "puede entrar" y "no puede" agotan el
#: caso. El tipo se declara aquí y lo importa el esquema de la API para que
#: añadir un estado sea un cambio en UN sitio.
OperatorAccess = Literal["ok", "disabled"]
ACCESS_OK: OperatorAccess = "ok"
ACCESS_DISABLED: OperatorAccess = "disabled"


@dataclass(frozen=True)
class OperatorView:
    """Quién es y si puede entrar.

    Igual que en la consola, **el login funciona aunque el acceso no sea
    ``ok``**: lo que cambia es que el panel enseña la página "sin acceso"
    en vez del contenido. Distinguirlo en el login permitiría enumerar
    cuentas deshabilitadas.
    """

    account: OperatorAccount
    access: OperatorAccess

    @property
    def ok(self) -> bool:
        return self.access == ACCESS_OK


def load_operator_view(account: OperatorAccount) -> OperatorView:
    """Clasifica el acceso. Sin consulta: todo lo que hace falta está en la
    propia fila, a diferencia de la consola, que tiene que mirar la
    pertenencia al partner."""
    if account.disabled_at is not None and aware(account.disabled_at) <= now():
        return OperatorView(account=account, access=ACCESS_DISABLED)
    return OperatorView(account=account, access=ACCESS_OK)


# ── cuentas y sesiones (delegan en el almacén) ────────────────────────


async def get_by_email(session: AsyncSession, email: str) -> OperatorAccount | None:
    account: OperatorAccount | None = await _STORE.get_by_email(session, email)
    return account


async def create_account(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    display_name: str | None = None,
    locale: str = "es",
    account_id: uuid.UUID | None = None,
) -> OperatorAccount:
    account: OperatorAccount = await _STORE.create_account(
        session,
        email=email,
        password=password,
        display_name=display_name,
        locale=locale,
        account_id=account_id,
    )
    return account


async def set_password(session: AsyncSession, account: OperatorAccount, password: str) -> None:
    await _STORE.set_password(session, account, password)


async def authenticate(
    session: AsyncSession, *, email: str, password: str
) -> OperatorAccount | None:
    account: OperatorAccount | None = await _STORE.authenticate(
        session, email=email, password=password
    )
    return account


async def start_session(
    session: AsyncSession,
    account: OperatorAccount,
    *,
    ip: str | None = None,
    user_agent: str | None = None,
) -> tuple[str, datetime]:
    return await _STORE.start_session(session, account, ip=ip, user_agent=user_agent)


async def resolve_session(session: AsyncSession, token: str) -> OperatorAccount | None:
    account: OperatorAccount | None = await _STORE.resolve_session(session, token)
    return account


async def end_session(session: AsyncSession, token: str) -> None:
    await _STORE.end_session(session, token)


__all__ = [
    "ACCESS_DISABLED",
    "ACCESS_OK",
    "LOCKOUT_DURATION",
    "MAX_FAILED_ATTEMPTS",
    "PASSWORD_MAX_LENGTH",
    "PASSWORD_MIN_LENGTH",
    "SESSION_TTL",
    "OperatorAccess",
    "OperatorView",
    "PasswordPolicyError",
    "authenticate",
    "create_account",
    "end_session",
    "get_by_email",
    "hash_password",
    "hash_session_token",
    "load_operator_view",
    "needs_rehash",
    "normalize_email",
    "resolve_session",
    "set_password",
    "start_session",
    "validate_password",
    "verify_password",
]
