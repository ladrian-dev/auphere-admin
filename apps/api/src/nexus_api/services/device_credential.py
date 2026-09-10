"""La credencial de dispositivo, versión 2 — spec 002, Requisitos 4.2 y 10.

**Nombra partner, máquina y generación; nunca tenant.** El tenant lo fija cada
trabajo y cada vínculo, por un ``client_ref`` que la plataforma resuelve dentro del
partner de la firma (§I: el tenant nunca llega del llamante).

**Es apátrida en la firma y con estado en la fila.** Un JWT HS256 no se puede
revocar ni rotar por sí solo; lo que lo hace revocable es que ``require_device``
carga la fila en cada petición y compara ``gen`` con ``credential_generation``.
Eso es lo que convierte en verdad el «revocable por sí sola» que la 001 escribió y
no cubrió.

**Simétrico a propósito con la consola.** Los tokens de consola son EdDSA porque
los acuña la consola y la API solo verifica; aquí la API es emisora y verificadora,
así que un secreto compartido evita distribuir una clave privada más.

**La guarda del secreto de fábrica se conserva**: fuera de ``dev`` con el valor
por defecto no se emite ni se verifica nada.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import structlog

from nexus_api.config import get_settings

log = structlog.get_logger(__name__)

ALGORITHM = "HS256"
_SERVICE_CLAIM = "device"
_DEV_SECRET = "dev-device-secret-change-me-min-32-chars"

#: Vida de una credencial. La máquina la renueva cuando le queda menos de RENEW_BEFORE.
DEFAULT_TTL = timedelta(hours=12)
RENEW_BEFORE = timedelta(hours=6)
#: La generación anterior sigue valiendo este tiempo tras rotar: lo que tarda un
#: fallo de red entre «el servidor rotó» y «la máquina guardó» en resolverse.
GENERATION_GRACE = timedelta(seconds=60)
#: Sin latir este tiempo, hay que volver a emparejar (Requisito 10.2).
ABANDON_AFTER = timedelta(days=30)


def _secret() -> str:
    return get_settings().device_token_secret


def _assert_secret_is_real() -> None:
    s = get_settings()
    if not s.is_prod and s.device_token_secret == _DEV_SECRET:
        log.warning("device_credential.dev_secret_in_use", environment=s.environment)
        return
    if s.device_token_secret == _DEV_SECRET or "change-me" in s.device_token_secret:
        raise DeviceCredentialError(
            "el secreto de las credenciales de dispositivo es el de fábrica fuera de dev"
        )


class DeviceCredentialError(RuntimeError):
    """El token no vale: firma, forma, caducidad o servicio equivocado."""


@dataclass(frozen=True)
class DeviceClaims:
    device_id: uuid.UUID
    partner_id: uuid.UUID
    generation: int


def issue_device_token(
    *,
    device_id: uuid.UUID,
    partner_id: uuid.UUID,
    generation: int,
    ttl: timedelta = DEFAULT_TTL,
) -> str:
    """Emite la credencial. Partner y generación quedan dentro de la firma."""
    _assert_secret_is_real()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "svc": _SERVICE_CLAIM,
        "sub": str(device_id),
        "pid": str(partner_id),
        "gen": int(generation),
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
        "iss": get_settings().console_jwt_issuer,
        "aud": get_settings().console_jwt_audience,
    }
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def verify_device_token(token: str) -> DeviceClaims:
    """Verifica firma y forma. El estado de la fila lo comprueba ``require_device``."""
    _assert_secret_is_real()
    if not token:
        raise DeviceCredentialError("no se presentó credencial de dispositivo")
    try:
        payload = jwt.decode(
            token,
            _secret(),
            algorithms=[ALGORITHM],
            audience=get_settings().console_jwt_audience,
            issuer=get_settings().console_jwt_issuer,
            leeway=get_settings().console_jwt_leeway_seconds,
        )
    except jwt.PyJWTError as exc:
        raise DeviceCredentialError(f"credencial de dispositivo inválida: {exc}") from exc

    # Un token de consola no vale aquí, y al revés tampoco: el servicio va firmado.
    if payload.get("svc") != _SERVICE_CLAIM:
        raise DeviceCredentialError("la credencial no es de un dispositivo")
    try:
        return DeviceClaims(
            device_id=uuid.UUID(str(payload["sub"])),
            partner_id=uuid.UUID(str(payload["pid"])),
            generation=int(payload["gen"]),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise DeviceCredentialError(
            "la credencial no nombra dispositivo, partner y generación"
        ) from exc


def generation_is_acceptable(
    claimed: int,
    *,
    current: int,
    rotated_at: datetime | None,
    now: datetime | None = None,
) -> bool:
    """La generación actual, o la anterior dentro de la gracia. Nada más."""
    if claimed == current:
        return True
    if claimed != current - 1 or rotated_at is None:
        return False
    reference = now or datetime.now(UTC)
    rotated = rotated_at if rotated_at.tzinfo else rotated_at.replace(tzinfo=UTC)
    return reference - rotated <= GENERATION_GRACE


def is_abandoned(last_heartbeat_at: datetime | None, *, now: datetime | None = None) -> bool:
    """Treinta días sin latir. ``None`` —nunca latió— no es abandono: es recién emparejada."""
    if last_heartbeat_at is None:
        return False
    reference = now or datetime.now(UTC)
    beat = last_heartbeat_at if last_heartbeat_at.tzinfo else last_heartbeat_at.replace(tzinfo=UTC)
    return reference - beat > ABANDON_AFTER


__all__ = [
    "ABANDON_AFTER",
    "ALGORITHM",
    "DEFAULT_TTL",
    "GENERATION_GRACE",
    "RENEW_BEFORE",
    "DeviceClaims",
    "DeviceCredentialError",
    "generation_is_acceptable",
    "is_abandoned",
    "issue_device_token",
    "verify_device_token",
]
