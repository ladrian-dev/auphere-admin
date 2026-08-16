"""Identidad de la consola de partners: contraseñas, sesiones y bloqueo.

Este módulo es la mitad de servidor de la decisión "la consola deja de
tener base de datos" (supersede parcialmente ADR-030 D2). El BFF de
``apps/console`` ya no habla con Postgres: llama a ``/console/auth/*`` con
su token de servicio y guarda en la cookie un **token opaco** que solo
significa algo aquí.

Contraseñas
-----------
``hashlib.scrypt`` de la biblioteca estándar — cero dependencias nuevas
(regla del plan: cada dependencia se justifica). Parámetros
``n=2**16, r=8, p=1, dklen=32`` con sal aleatoria de 16 bytes, ~64 MiB y
~100 ms por verificación en el hardware de la API. El formato almacenado
lleva los parámetros::

    scrypt$65536$8$1$<salt_b64>$<hash_b64>

de modo que subirlos mañana no invalida las filas de hoy: se comparan con
los que trae cada fila y :func:`needs_rehash` dice cuáles conviene volver
a calcular en el siguiente login correcto.

El cálculo es caro y **síncrono**, así que las funciones públicas del
módulo lo mandan a un hilo (``asyncio.to_thread``): un login no puede
parar el bucle de eventos de la API durante 100 ms.

Sesiones
--------
Token opaco de 32 bytes (``secrets.token_urlsafe``); en la base solo vive
su SHA-256, igual que ``api_keys.key_hash``. TTL **absoluto de 7 días**:
no se renueva por uso, así que una cookie robada caduca sí o sí. Para no
escribir en cada petición, ``last_used_at`` se refresca como mucho una vez
cada 5 minutos.

Bloqueo
-------
Diez fallos consecutivos → 15 minutos bloqueado. La respuesta durante el
bloqueo es **idéntica** al 401 de contraseña incorrecta: el atacante no
aprende que existe la cuenta ni que la bloqueó. El contador se pone a cero
al acertar.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

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

log = structlog.get_logger(__name__)

# ── política ──────────────────────────────────────────────────────────

#: Mínimo de la consola desde el día uno (better-auth usaba 12). Bajarlo
#: sería una regresión de seguridad silenciosa para las cuentas ya creadas.
PASSWORD_MIN_LENGTH = 12
#: Tope para que nadie pague 4 KiB de scrypt por petición.
PASSWORD_MAX_LENGTH = 256

SESSION_TTL = timedelta(days=7)
#: Ventana bajo la cual NO se reescribe ``last_used_at``.
SESSION_TOUCH_INTERVAL = timedelta(minutes=5)

MAX_FAILED_ATTEMPTS = 10
LOCKOUT_DURATION = timedelta(minutes=15)

# ── scrypt ────────────────────────────────────────────────────────────

_SCHEME = "scrypt"
_N = 2**16
_R = 8
_P = 1
_DKLEN = 32
_SALT_BYTES = 16
#: OpenSSL rechaza el cálculo si no cabe en ``maxmem``. scrypt necesita
#: ~128 * N * r bytes (64 MiB con estos parámetros); se pide el doble para
#: no quedarse al borde si mañana sube ``r``.
_MAXMEM = 128 * _N * _R * 2


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _derive(password: str, salt: bytes, *, n: int, r: int, p: int, dklen: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=dklen, maxmem=_MAXMEM
    )


def hash_password(password: str) -> str:
    """``scrypt$n$r$p$<salt_b64>$<hash_b64>``. Función pura y CARA: los
    llamantes async la mandan a un hilo."""
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = _derive(password, salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"{_SCHEME}${_N}${_R}${_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    """Comparación en tiempo constante contra el formato almacenado. Un
    hash mal formado es ``False``, nunca una excepción: una fila corrupta
    no debe convertirse en un 500 que distinga esa cuenta del resto."""
    try:
        scheme, raw_n, raw_r, raw_p, salt_b64, hash_b64 = stored.split("$")
        if scheme != _SCHEME:
            return False
        expected = base64.b64decode(hash_b64)
        digest = _derive(
            password,
            base64.b64decode(salt_b64),
            n=int(raw_n),
            r=int(raw_r),
            p=int(raw_p),
            dklen=len(expected),
        )
    except (ValueError, TypeError, MemoryError):
        return False
    return hmac.compare_digest(digest, expected)


def needs_rehash(stored: str) -> bool:
    """True si la fila se calculó con parámetros más flojos que los de hoy."""
    try:
        scheme, raw_n, raw_r, raw_p, _salt, _hash = stored.split("$")
    except ValueError:
        return True
    if scheme != _SCHEME:
        return True
    try:
        return (int(raw_n), int(raw_r), int(raw_p)) != (_N, _R, _P)
    except ValueError:
        return True


_dummy_hash: str | None = None


def _decoy_hash() -> str:
    """Hash de una contraseña que no existe. Se verifica contra él cuando
    el correo no está en la base para que "no existe" y "contraseña mala"
    cuesten lo mismo en tiempo — la respuesta ya es idéntica, el reloj
    también tiene que serlo. Perezoso: calcularlo al importar añadiría
    ~100 ms y 64 MiB al arranque de la API."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password(secrets.token_urlsafe(32))
    return _dummy_hash


class PasswordPolicyError(ValueError):
    """La contraseña propuesta no cumple la política. Se traduce a 422."""


def validate_password(password: str) -> None:
    if not (PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH):
        raise PasswordPolicyError(
            f"password must be between {PASSWORD_MIN_LENGTH} and {PASSWORD_MAX_LENGTH} characters"
        )


# ── sesiones ──────────────────────────────────────────────────────────


def hash_session_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    """asyncpg devuelve ``timestamptz`` con tzinfo, pero una fila recién
    escrita en la misma transacción puede llevar el ``datetime`` naive que
    puso el propio código. Comparar los dos revienta."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


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
    membership, partner = row
    if (
        membership.status != MembershipStatus.ACTIVE.value
        or partner.status != PartnerStatus.ACTIVE.value
    ):
        return PrincipalView(
            account=account, access=ACCESS_SUSPENDED, membership=membership, partner=partner
        )
    if not partner.console_enabled:
        return PrincipalView(
            account=account, access=ACCESS_DISABLED, membership=membership, partner=partner
        )
    return PrincipalView(account=account, access=ACCESS_OK, membership=membership, partner=partner)


# ── cuentas ───────────────────────────────────────────────────────────


async def get_by_email(session: AsyncSession, email: str) -> ConsoleAccount | None:
    account: ConsoleAccount | None = await session.scalar(
        sa.select(ConsoleAccount)
        .where(sa.func.lower(ConsoleAccount.email) == normalize_email(email))
        .limit(1)
    )
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
    """Crea la cuenta. Valida la política ANTES de gastar los 100 ms."""
    validate_password(password)
    password_hash = await asyncio.to_thread(hash_password, password)
    account = ConsoleAccount(
        id=account_id or uuid.uuid4(),
        email=normalize_email(email),
        password_hash=password_hash,
        display_name=display_name,
        locale=locale if locale in {"es", "en"} else "es",
    )
    session.add(account)
    await session.flush()
    return account


async def set_password(session: AsyncSession, account: ConsoleAccount, password: str) -> None:
    validate_password(password)
    account.password_hash = await asyncio.to_thread(hash_password, password)
    account.updated_at = _now()
    account.failed_attempts = 0
    account.locked_until = None
    await session.flush()


async def authenticate(
    session: AsyncSession, *, email: str, password: str
) -> ConsoleAccount | None:
    """``None`` para cualquier fallo: cuenta inexistente, contraseña mala o
    cuenta bloqueada. El llamante responde lo mismo en los tres casos.

    Efectos: incrementa el contador de fallos (y bloquea al décimo), o lo
    pone a cero y sella ``last_login_at`` al acertar. Si el hash se calculó
    con parámetros viejos, se recalcula aprovechando que aquí tenemos la
    contraseña en claro.
    """
    account = await get_by_email(session, email)
    now = _now()
    if account is None:
        # Mismo coste de reloj que una cuenta real.
        await asyncio.to_thread(verify_password, password, _decoy_hash())
        return None
    if account.locked_until is not None and _aware(account.locked_until) > now:
        await asyncio.to_thread(verify_password, password, _decoy_hash())
        log.info("console_identity.login_while_locked", account_id=str(account.id))
        return None

    ok = await asyncio.to_thread(verify_password, password, account.password_hash)
    if not ok:
        account.failed_attempts += 1
        if account.failed_attempts >= MAX_FAILED_ATTEMPTS:
            account.locked_until = now + LOCKOUT_DURATION
            log.warning(
                "console_identity.account_locked",
                account_id=str(account.id),
                attempts=account.failed_attempts,
            )
        await session.flush()
        return None

    account.failed_attempts = 0
    account.locked_until = None
    account.last_login_at = now
    if needs_rehash(account.password_hash):
        account.password_hash = await asyncio.to_thread(hash_password, password)
    await session.flush()
    return account


# ── ciclo de vida de la sesión ────────────────────────────────────────


async def _purge_expired(session: AsyncSession) -> None:
    """Barrido oportunista y barato: se apoya en ``ix_console_sessions_expires``
    y solo se llama al crear una sesión, no en cada petición."""
    await session.execute(sa.delete(ConsoleSession).where(ConsoleSession.expires_at <= _now()))


async def start_session(
    session: AsyncSession,
    account: ConsoleAccount,
    *,
    ip: str | None = None,
    user_agent: str | None = None,
) -> tuple[str, datetime]:
    """Devuelve ``(token_en_claro, expires_at)``. El token solo existe aquí
    y en la cookie del navegador; la base guarda su SHA-256."""
    await _purge_expired(session)
    plaintext = secrets.token_urlsafe(32)
    expires_at = _now() + SESSION_TTL
    session.add(
        ConsoleSession(
            token_hash=hash_session_token(plaintext),
            principal_id=account.id,
            expires_at=expires_at,
            last_used_at=_now(),
            ip=ip,
            user_agent=(user_agent or "")[:255] or None,
        )
    )
    await session.flush()
    return plaintext, expires_at


async def resolve_session(session: AsyncSession, token: str) -> ConsoleAccount | None:
    """Cuenta detrás de un token de sesión, o ``None`` si no existe o
    caducó. Refresca ``last_used_at`` como mucho una vez cada 5 minutos."""
    if not token:
        return None
    row = (
        await session.execute(
            sa.select(ConsoleSession, ConsoleAccount)
            .join(ConsoleAccount, ConsoleAccount.id == ConsoleSession.principal_id)
            .where(ConsoleSession.token_hash == hash_session_token(token))
            .limit(1)
        )
    ).first()
    if row is None:
        return None
    console_session: ConsoleSession = row[0]
    account: ConsoleAccount = row[1]
    now = _now()
    if _aware(console_session.expires_at) <= now:
        await session.delete(console_session)
        await session.flush()
        return None
    if now - _aware(console_session.last_used_at) >= SESSION_TOUCH_INTERVAL:
        console_session.last_used_at = now
        await session.flush()
    return account


async def end_session(session: AsyncSession, token: str) -> None:
    """Idempotente: cerrar una sesión que no existe no es un error."""
    if not token:
        return
    await session.execute(
        sa.delete(ConsoleSession).where(ConsoleSession.token_hash == hash_session_token(token))
    )


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
