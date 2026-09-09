"""La credencial de un dispositivo — Requisitos 6.3 y 6.4.

**Qué es y qué no es.** El Requisito 15.2 prohíbe que la cáscara guarde una
credencial de **backend** —una llave de la cuenta, que abre todo—. Ésta es otra
cosa: abre exactamente cuatro operaciones (latir, sondear, devolver resultado,
darse de baja) de **una máquina concreta** de **un tenant concreto**. Sin ella el
dispositivo tendría que llevar la credencial de la persona, que es peor: esa sí
abre todo, y encima viviría en un portátil.

**Simétrico, y a propósito.** Los tokens de consola son EdDSA porque los **acuña la
consola** y la API solo los verifica: por eso la API tiene la clave pública y no la
privada. Aquí la API es emisora y verificadora, así que un secreto compartido basta
y evita distribuir una clave privada más.

**Con guardia de arranque, y la que ya existía.** `config.py` tiene un validador que
**se niega a arrancar en producción** con placeholders de desarrollo. El secreto de
este módulo se añadió a esa lista en vez de escribir un guardia paralelo: dos
mecanismos con semántica distinta es un sitio más donde equivocarse.

Se fuerza en **producción**, no en staging, que es la convención deliberada del repo
—el terraform lo dice: *«el guard de secretos solo fuerza en "production"»*—. En
staging se puede probar con el valor de fábrica, y aquí queda un aviso ruidoso para
que nadie confunda «funciona en staging» con «está configurado».

**El `tenant_id` viaja firmado, no lo pone el llamante.** Es la misma regla de §I
aplicada a un canal nuevo: quien pide trabajo no declara de qué tenant es — lo
dice la firma, y la RLS decide después.
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

#: Corta porque el dispositivo la renueva solo en cada latido. Una credencial de
#: máquina que dura meses es una llave olvidada en un cajón.
DEFAULT_TTL = timedelta(hours=12)


#: El valor que trae `config.py` por defecto. Sirve en desarrollo y en ningún sitio más.
_DEV_SECRET = "dev-device-secret-change-me-min-32-chars"


def _secret() -> str:
    return get_settings().device_token_secret


def _assert_secret_is_real() -> None:
    """Fuera de desarrollo, el secreto de fábrica no vale.

    Es la guarda que el resto de los `…-change-me` del repo no tienen. Un secreto
    por defecto en producción no es una configuración pendiente: es una puerta
    abierta, y firma credenciales que dan acceso a la máquina de un partner.
    """
    s = get_settings()
    if s.is_prod and s.device_token_secret == _DEV_SECRET:
        # Red de seguridad: el validador de `config.py` ya impide arrancar así,
        # pero si alguien recarga los ajustes en caliente, esto lo para igual.
        raise DeviceCredentialError(
            "device_token_secret sigue en su valor de desarrollo en producción; "
            "no se emiten ni verifican credenciales de dispositivo con él"
        )
    if not s.is_prod and s.device_token_secret == _DEV_SECRET:
        log.warning("device_credential.dev_secret_in_use", environment=s.environment)


class DeviceCredentialError(RuntimeError):
    """El token no vale: firma, forma, caducidad o servicio equivocado."""


@dataclass(frozen=True)
class DeviceClaims:
    device_id: uuid.UUID
    tenant_id: uuid.UUID


def issue_device_token(
    *, device_id: uuid.UUID, tenant_id: uuid.UUID, ttl: timedelta = DEFAULT_TTL
) -> str:
    """Emite la credencial en el alta. El `tenant_id` queda dentro de la firma."""
    _assert_secret_is_real()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "svc": _SERVICE_CLAIM,
        "sub": str(device_id),
        "tid": str(tenant_id),
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
        "iss": get_settings().console_jwt_issuer,
        "aud": get_settings().console_jwt_audience,
    }
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def verify_device_token(token: str) -> DeviceClaims:
    """Verifica y devuelve a quién autoriza. Falla cerrado ante cualquier duda."""
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
            device_id=uuid.UUID(str(payload["sub"])), tenant_id=uuid.UUID(str(payload["tid"]))
        )
    except (KeyError, ValueError) as exc:
        raise DeviceCredentialError("la credencial no nombra dispositivo y tenant") from exc


__all__ = [
    "ALGORITHM",
    "DEFAULT_TTL",
    "DeviceClaims",
    "DeviceCredentialError",
    "issue_device_token",
    "verify_device_token",
]
