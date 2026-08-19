"""Primitivas de identidad compartidas: contraseñas, sesiones y bloqueo.

Este módulo nace de partir ``services/console_identity.py`` en dos
(ADR-034, Fase 0). Ese fichero implementaba scrypt, el token de sesión, el
bloqueo por intentos y el hash señuelo, y hasta el 2026-08-19 era el único
sitio que los necesitaba. Deja de serlo: el panel de operador se muda al
mismo modelo —identidad en la API, cookie opaca en el BFF— porque Vercel
no alcanza la Aurora privada.

**No se duplica.** Duplicar esto significa que el día que suban los
parámetros de scrypt, o que aparezca un fallo en la comparación en tiempo
constante, uno de los dos se arregla y el otro no. Lo que aquí vive es
exactamente lo que NO depende de quién es el usuario:

- ``hash_password`` / ``verify_password`` / ``needs_rehash`` / política;
- el hash del token de sesión y la normalización del correo;
- :class:`IdentityStore`, el ciclo de vida completo de cuentas y sesiones,
  parametrizado por los dos modelos de cada esquema.

Lo que NO vive aquí es la **autorización**: qué significa tener acceso lo
decide cada dominio. La consola lo resuelve contra
``public.partner_memberships`` (``console_identity.load_principal_view``) y
el panel de operador contra su propio rol. Esa frontera es la que impide
que un principal de partner se convierta en operador por un error de
etiquetado.

Contraseñas
-----------
``hashlib.scrypt`` de la biblioteca estándar — cero dependencias nuevas.
Parámetros ``n=2**16, r=8, p=1, dklen=32`` con sal aleatoria de 16 bytes,
~64 MiB y ~100 ms por verificación. El formato almacenado lleva los
parámetros::

    scrypt$65536$8$1$<salt_b64>$<hash_b64>

de modo que subirlos mañana no invalida las filas de hoy: se comparan con
los que trae cada fila y :func:`needs_rehash` dice cuáles conviene volver a
calcular en el siguiente login correcto.

El cálculo es caro y **síncrono**, así que las funciones públicas lo mandan
a un hilo (``asyncio.to_thread``): un login no puede parar el bucle de
eventos de la API durante 100 ms.

Sesiones
--------
Token opaco de 32 bytes (``secrets.token_urlsafe``); en la base solo vive
su SHA-256, igual que ``api_keys.key_hash``. TTL **absoluto de 7 días**: no
se renueva por uso, así que una cookie robada caduca sí o sí. Para no
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
from typing import Any, Protocol

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

# ── política ──────────────────────────────────────────────────────────

#: Mínimo desde el día uno (better-auth usaba 12). Bajarlo sería una
#: regresión de seguridad silenciosa para las cuentas ya creadas.
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


def decoy_hash() -> str:
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


# ── sesiones y correo ─────────────────────────────────────────────────


def hash_session_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def now() -> datetime:
    return datetime.now(UTC)


def aware(value: datetime) -> datetime:
    """asyncpg devuelve ``timestamptz`` con tzinfo, pero una fila recién
    escrita en la misma transacción puede llevar el ``datetime`` naive que
    puso el propio código. Comparar los dos revienta."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


# ── el almacén, parametrizado por los modelos de cada esquema ──────────


class _AccountModel(Protocol):
    """Forma mínima que :class:`IdentityStore` necesita de una cuenta.

    No se declara con genéricos de SQLAlchemy a propósito: los dos modelos
    reales (``console_auth.principals`` y ``operator_auth.principals``) son
    columna a columna idénticos, y un Protocol documenta ese contrato sin
    arrastrar la maquinaria de tipos del ORM a cada llamada.
    """

    id: Any
    email: Any
    password_hash: Any
    display_name: Any
    locale: Any
    updated_at: Any
    last_login_at: Any
    failed_attempts: Any
    locked_until: Any


@dataclass(frozen=True)
class IdentityStore:
    """Ciclo de vida de cuentas y sesiones sobre un par de modelos.

    Un almacén por esquema de identidad. Lo que cambia entre uno y otro son
    las dos clases; el comportamiento —coste constante ante correos
    inexistentes, bloqueo tras diez fallos, rehash oportunista, TTL
    absoluto de sesión— es el mismo por definición, y esa es justamente la
    razón de que viva aquí una sola vez.
    """

    account_model: type[Any]
    session_model: type[Any]
    #: Prefijo de los eventos de log (``console_identity`` / ``operator_identity``).
    log_prefix: str

    # ── cuentas ──────────────────────────────────────────────────────

    async def get_by_email(self, session: AsyncSession, email: str) -> Any | None:
        model = self.account_model
        account = await session.scalar(
            sa.select(model).where(sa.func.lower(model.email) == normalize_email(email)).limit(1)
        )
        return account

    async def create_account(
        self,
        session: AsyncSession,
        *,
        email: str,
        password: str,
        display_name: str | None = None,
        locale: str = "es",
        account_id: uuid.UUID | None = None,
        **extra: Any,
    ) -> Any:
        """Crea la cuenta. Valida la política ANTES de gastar los 100 ms.

        ``extra`` deja que cada esquema añada sus columnas propias (el rol
        del operador, por ejemplo) sin que este módulo las conozca.
        """
        validate_password(password)
        password_hash = await asyncio.to_thread(hash_password, password)
        account = self.account_model(
            id=account_id or uuid.uuid4(),
            email=normalize_email(email),
            password_hash=password_hash,
            display_name=display_name,
            locale=locale if locale in {"es", "en"} else "es",
            **extra,
        )
        session.add(account)
        await session.flush()
        return account

    async def set_password(
        self, session: AsyncSession, account: _AccountModel, password: str
    ) -> None:
        validate_password(password)
        account.password_hash = await asyncio.to_thread(hash_password, password)
        account.updated_at = now()
        account.failed_attempts = 0
        account.locked_until = None
        await session.flush()

    async def authenticate(self, session: AsyncSession, *, email: str, password: str) -> Any | None:
        """``None`` para cualquier fallo: cuenta inexistente, contraseña mala
        o cuenta bloqueada. El llamante responde lo mismo en los tres casos.

        Efectos: incrementa el contador de fallos (y bloquea al décimo), o lo
        pone a cero y sella ``last_login_at`` al acertar. Si el hash se
        calculó con parámetros viejos, se recalcula aprovechando que aquí
        tenemos la contraseña en claro.
        """
        account = await self.get_by_email(session, email)
        current = now()
        if account is None:
            # Mismo coste de reloj que una cuenta real.
            await asyncio.to_thread(verify_password, password, decoy_hash())
            return None
        if account.locked_until is not None and aware(account.locked_until) > current:
            await asyncio.to_thread(verify_password, password, decoy_hash())
            log.info(f"{self.log_prefix}.login_while_locked", account_id=str(account.id))
            return None

        ok = await asyncio.to_thread(verify_password, password, account.password_hash)
        if not ok:
            account.failed_attempts += 1
            if account.failed_attempts >= MAX_FAILED_ATTEMPTS:
                account.locked_until = current + LOCKOUT_DURATION
                log.warning(
                    f"{self.log_prefix}.account_locked",
                    account_id=str(account.id),
                    attempts=account.failed_attempts,
                )
            await session.flush()
            return None

        account.failed_attempts = 0
        account.locked_until = None
        account.last_login_at = current
        if needs_rehash(account.password_hash):
            account.password_hash = await asyncio.to_thread(hash_password, password)
        await session.flush()
        return account

    # ── ciclo de vida de la sesión ───────────────────────────────────

    async def _purge_expired(self, session: AsyncSession) -> None:
        """Barrido oportunista y barato: se apoya en el índice de
        ``expires_at`` y solo se llama al crear una sesión, no en cada
        petición."""
        model = self.session_model
        await session.execute(sa.delete(model).where(model.expires_at <= now()))

    async def start_session(
        self,
        session: AsyncSession,
        account: _AccountModel,
        *,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[str, datetime]:
        """Devuelve ``(token_en_claro, expires_at)``. El token solo existe
        aquí y en la cookie del navegador; la base guarda su SHA-256."""
        await self._purge_expired(session)
        plaintext = secrets.token_urlsafe(32)
        expires_at = now() + SESSION_TTL
        session.add(
            self.session_model(
                token_hash=hash_session_token(plaintext),
                principal_id=account.id,
                expires_at=expires_at,
                last_used_at=now(),
                ip=ip,
                user_agent=(user_agent or "")[:255] or None,
            )
        )
        await session.flush()
        return plaintext, expires_at

    async def resolve_session(self, session: AsyncSession, token: str) -> Any | None:
        """Cuenta detrás de un token de sesión, o ``None`` si no existe o
        caducó. Refresca ``last_used_at`` como mucho una vez cada 5 minutos."""
        if not token:
            return None
        acc_model, ses_model = self.account_model, self.session_model
        row = (
            await session.execute(
                sa.select(ses_model, acc_model)
                .join(acc_model, acc_model.id == ses_model.principal_id)
                .where(ses_model.token_hash == hash_session_token(token))
                .limit(1)
            )
        ).first()
        if row is None:
            return None
        stored_session, account = row[0], row[1]
        current = now()
        if aware(stored_session.expires_at) <= current:
            await session.delete(stored_session)
            await session.flush()
            return None
        if current - aware(stored_session.last_used_at) >= SESSION_TOUCH_INTERVAL:
            stored_session.last_used_at = current
            await session.flush()
        return account

    async def end_session(self, session: AsyncSession, token: str) -> None:
        """Idempotente: cerrar una sesión que no existe no es un error."""
        if not token:
            return
        model = self.session_model
        await session.execute(sa.delete(model).where(model.token_hash == hash_session_token(token)))


__all__ = [
    "LOCKOUT_DURATION",
    "MAX_FAILED_ATTEMPTS",
    "PASSWORD_MAX_LENGTH",
    "PASSWORD_MIN_LENGTH",
    "SESSION_TOUCH_INTERVAL",
    "SESSION_TTL",
    "IdentityStore",
    "PasswordPolicyError",
    "aware",
    "decoy_hash",
    "hash_password",
    "hash_session_token",
    "needs_rehash",
    "normalize_email",
    "now",
    "validate_password",
    "verify_password",
]
