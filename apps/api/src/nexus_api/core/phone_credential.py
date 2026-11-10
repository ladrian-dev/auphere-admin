"""Las credenciales del teléfono — spec 031, R2 y research D3/D4.

Dos piezas, cada una con un trabajo:

* **El acceso**: un JWT HS256 de una hora con ``{svc, sub, gen}``. ``sub`` es
  el teléfono (``client_phones.id``) y ``gen`` su generación. **No lleva
  tenant ni partner**: salen de la fila del teléfono, que se lee como identidad
  en cada petición (D3). Un token así no se puede revocar por sí solo; lo que
  lo hace revocable es que la fila se vuelve a mirar siempre.
* **La renovación**: 32 bytes aleatorios, opacos, de los que la base solo
  guarda el SHA-256. Rota en cada uso y caduca tras 90 días sin uso (D4).

**Secreto propio.** ``customers_app_token_secret`` y no el de las máquinas del
escritorio: comprometer uno no abre el otro, y el servicio va firmado, así que
un token de máquina no vale como teléfono aunque alguien los mezcle.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import structlog

from nexus_api.config import get_settings

log = structlog.get_logger(__name__)

ALGORITHM = "HS256"
SERVICE_CLAIM = "customers_phone"
_DEV_SECRET = "dev-customers-app-secret-change-me-32+"

#: Vida del acceso. La app lo renueva un minuto antes de que caduque o al
#: recibir un 401, y nunca dos veces a la vez (``apps/mobile/src/api/client.ts``).
ACCESS_TTL = timedelta(hours=1)
#: La renovación anterior sigue valiendo este tiempo tras rotar: lo que tarda un
#: fallo de red entre «el servidor rotó» y «el teléfono guardó» en resolverse.
REFRESH_GRACE = timedelta(seconds=60)
#: Sin usarse este tiempo, el teléfono tiene que volver a entrar (R2.2).
ABANDON_AFTER = timedelta(days=90)


class PhoneCredentialError(RuntimeError):
    """El token no vale: firma, forma, caducidad o servicio equivocado."""


@dataclass(frozen=True)
class PhoneClaims:
    phone_id: uuid.UUID
    generation: int


def _secret() -> str:
    return get_settings().customers_app_token_secret


def _assert_secret_is_real() -> None:
    s = get_settings()
    secret = s.customers_app_token_secret
    if not s.is_prod and secret == _DEV_SECRET:
        return
    if secret == _DEV_SECRET or "change-me" in secret or len(secret) < 32:
        raise PhoneCredentialError(
            "el secreto de las credenciales del teléfono es el de fábrica fuera de dev"
        )


def issue_access_token(*, phone_id: uuid.UUID, generation: int, ttl: timedelta = ACCESS_TTL) -> str:
    _assert_secret_is_real()
    s = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "svc": SERVICE_CLAIM,
        "sub": str(phone_id),
        "gen": int(generation),
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
        "iss": s.console_jwt_issuer,
        "aud": s.console_jwt_audience,
    }
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def verify_access_token(token: str) -> PhoneClaims:
    """Firma y forma. El estado de la fila lo comprueba ``client_auth``."""
    _assert_secret_is_real()
    if not token:
        raise PhoneCredentialError("no se presentó credencial")
    s = get_settings()
    try:
        payload = jwt.decode(
            token,
            _secret(),
            algorithms=[ALGORITHM],
            audience=s.console_jwt_audience,
            issuer=s.console_jwt_issuer,
            leeway=s.console_jwt_leeway_seconds,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise PhoneCredentialError(f"credencial de teléfono inválida: {exc}") from exc
    if payload.get("svc") != SERVICE_CLAIM:
        raise PhoneCredentialError("la credencial no es de un teléfono")
    try:
        return PhoneClaims(phone_id=uuid.UUID(str(payload["sub"])), generation=int(payload["gen"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise PhoneCredentialError("la credencial no nombra teléfono y generación") from exc


def looks_like_phone_token(token: str) -> bool:
    """¿Es un token de teléfono (HS256) y no el de la BFF (EdDSA)?

    Solo elige qué verificación aplicar; **no verifica nada**. Las dos ramas
    verifican entero después, así que un token que mienta en su cabecera
    falla en la rama que elija.
    """
    try:
        return jwt.get_unverified_header(token).get("alg") == ALGORITHM
    except jwt.PyJWTError:
        return False


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()


def is_abandoned(last_seen_at: datetime | None, *, now: datetime | None = None) -> bool:
    if last_seen_at is None:
        return False
    reference = now or datetime.now(UTC)
    seen = last_seen_at if last_seen_at.tzinfo else last_seen_at.replace(tzinfo=UTC)
    return reference - seen > ABANDON_AFTER


__all__ = [
    "ABANDON_AFTER",
    "ACCESS_TTL",
    "ALGORITHM",
    "REFRESH_GRACE",
    "SERVICE_CLAIM",
    "PhoneClaims",
    "PhoneCredentialError",
    "hash_refresh_token",
    "is_abandoned",
    "issue_access_token",
    "looks_like_phone_token",
    "new_refresh_token",
    "verify_access_token",
]
