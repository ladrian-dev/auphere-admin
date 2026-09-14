"""``state`` firmado para el redirect de autorización de TikTok.

El flujo de autorización de TikTok es un redirect de navegador: mandamos al
dueño del negocio a TikTok con un ``state``, y TikTok nos lo devuelve al
callback junto al ``auth_code``. El callback no tiene sesión ni otra forma de
saber **de qué tenant** era esta autorización, así que el ``state`` tiene que
llevarlo — y por tanto no puede ser falsificable.

Sin un state firmado, cualquiera que alcance la URL del callback podría
presentar su propio ``auth_code`` con ``state=<tenant de la víctima>`` e
injertar su cuenta de TikTok en el tenant de otro. Eso es una escritura entre
tenants: este módulo está en la frontera de aislamiento, no es una comodidad.

**Desde la spec 006 esto es una fachada.** La firma, el nonce y la caducidad
viven en ``services/oauth_state.py``, que es genérico y lo comparten los tres
usos (TikTok, consentimiento de conectores y Google). Aquí sólo queda lo que es
de TikTok: que el sujeto es un ``tenant_id`` y que viaja en el claim ``t``.

**El formato en el cable no cambió** al extraerlo —
``base64url({"t":…,"n":…,"e":…}).base64url(firma)`` — y hay una prueba que lo
fija (`test_oauth_state.py::test_sigue_siendo_compatible_con_el_state_de_tiktok`),
porque cambiarlo habría roto las autorizaciones que estuvieran a medio camino
en el momento de desplegar.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from nexus_api.services.oauth_state import (
    DEFAULT_TTL,
    OAuthStateExpired,
    OAuthStateInvalid,
    sign_state,
    verify_state,
)

#: El claim que lleva el tenant. Es parte del formato en el cable.
_TENANT_CLAIM = "t"


@dataclass(frozen=True)
class OAuthStatePayload:
    tenant_id: uuid.UUID
    nonce: str
    expires_at: datetime


def sign_oauth_state(
    *,
    tenant_id: uuid.UUID,
    secret: str,
    ttl: timedelta = DEFAULT_TTL,
    now: datetime | None = None,
) -> tuple[str, OAuthStatePayload]:
    """Acuña un state ligado a un tenant. Devuelve ``(state, payload)``."""
    state, payload = sign_state(
        claims={_TENANT_CLAIM: str(tenant_id)}, secret=secret, ttl=ttl, now=now
    )
    return state, OAuthStatePayload(
        tenant_id=tenant_id, nonce=payload.nonce, expires_at=payload.expires_at
    )


def verify_oauth_state(
    *,
    state: str,
    secret: str,
    now: datetime | None = None,
) -> OAuthStatePayload:
    """Verifica y devuelve el payload. Lanza en cualquier modo de fallo."""
    payload = verify_state(state=state, secret=secret, now=now)
    raw = payload.claims.get(_TENANT_CLAIM)
    if raw is None:
        raise OAuthStateInvalid("state carries no tenant claim")
    try:
        tenant_id = uuid.UUID(raw)
    except ValueError as exc:
        raise OAuthStateInvalid(f"tenant claim is not a uuid: {exc}") from exc
    return OAuthStatePayload(
        tenant_id=tenant_id, nonce=payload.nonce, expires_at=payload.expires_at
    )


__all__ = [
    "DEFAULT_TTL",
    "OAuthStateExpired",
    "OAuthStateInvalid",
    "OAuthStatePayload",
    "sign_oauth_state",
    "verify_oauth_state",
]
