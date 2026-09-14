"""El ``state`` firmado de cualquier redirect OAuth (spec 006, R5.4).

**Por qué existe, y no es refactor por gusto.** Ya había dos copias de este
patrón —``tiktok_oauth_state`` y ``connectors/consent_token``— y Google iba a
ser la tercera. Tres copias de una firma divergen, y la que se queda sin la
corrección es siempre la que menos se toca.

El riesgo que cubre es el mismo en los tres casos: el callback de un proveedor
no tiene sesión, así que el ``state`` es lo único que dice **de quién** era esta
autorización. Sin firma, cualquiera que alcance el callback puede devolver un
código con el ``state`` de otro e injertar su cuenta en la de un tercero.

Propiedades, y cada una tapa un fallo concreto:

- **A prueba de manipulación** — HMAC-SHA256 sobre JSON canónico, comparado con
  ``compare_digest``. La firma se verifica **antes** de parsear: así nadie
  puede sondear el parseo con entrada sin firmar.
- **Con nonce** — dos autorizaciones del mismo sujeto producen states
  distintos, y por tanto distinguibles en los registros.
- **Corto de vida** — una ida y vuelta de OAuth dura segundos; una ventana
  larga sólo sirve para que una pestaña olvidada valga mañana.

**Lo que este módulo NO hace: un solo uso.** Una firma no puede impedir que el
mismo state se presente dos veces — no hay dónde apuntarlo. El uso único vive
en Redis, junto al ``code_verifier`` de PKCE, y se consume de forma atómica
(``services/google_oidc.consume_pkce``).

**El formato en el cable es el que ya había** —
``base64url(payload).base64url(firma)`` con ``{"n": nonce, "e": epoch, …}`` —
porque cambiarlo rompería las autorizaciones de TikTok que estuvieran a medio
camino en el momento de desplegar.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

#: Treinta minutos. La ida y vuelta real tarda segundos; el resto es margen
#: para una red lenta y una persona que lee la pantalla del proveedor.
DEFAULT_TTL = timedelta(minutes=30)

#: Claves reservadas del sobre. Un ``claim`` no puede llamarse así.
_NONCE = "n"
_EXPIRES = "e"


class OAuthStateInvalid(ValueError):
    """Malformado, manipulado, o firmado con otro secreto."""


class OAuthStateExpired(ValueError):
    """La caducidad ya pasó."""


@dataclass(frozen=True)
class StatePayload:
    claims: dict[str, str]
    nonce: str
    expires_at: datetime


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def sign_state(
    *,
    claims: Mapping[str, str],
    secret: str,
    ttl: timedelta = DEFAULT_TTL,
    now: datetime | None = None,
) -> tuple[str, StatePayload]:
    """Acuña un state firmado. Devuelve ``(state, payload)``."""
    if not secret:
        raise ValueError("oauth state secret must be non-empty")
    reservados = {_NONCE, _EXPIRES} & set(claims)
    if reservados:
        raise ValueError(f"reserved claim names: {sorted(reservados)}")

    issued = now if now is not None else datetime.now(UTC)
    payload = StatePayload(
        claims=dict(claims),
        nonce=secrets.token_urlsafe(16),
        expires_at=issued + ttl,
    )
    envelope: dict[str, str | int] = dict(payload.claims)
    envelope[_NONCE] = payload.nonce
    envelope[_EXPIRES] = int(payload.expires_at.timestamp())
    raw = json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()
    return f"{_b64url_encode(raw)}.{_b64url_encode(signature)}", payload


def verify_state(
    *,
    state: str,
    secret: str,
    now: datetime | None = None,
) -> StatePayload:
    """Verifica y devuelve el payload. Lanza en cualquier modo de fallo."""
    if not secret:
        raise ValueError("oauth state secret must be non-empty")
    if not state or "." not in state:
        raise OAuthStateInvalid("malformed state (missing separator)")
    raw_b64, sig_b64 = state.split(".", 1)
    try:
        raw = _b64url_decode(raw_b64)
        signature = _b64url_decode(sig_b64)
    except (ValueError, binascii.Error) as exc:
        raise OAuthStateInvalid("base64 decode failed") from exc

    expected = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()
    # Antes de parsear, a propósito: un atacante no debe poder sondear el
    # manejo del payload con entrada sin firmar.
    if not hmac.compare_digest(expected, signature):
        raise OAuthStateInvalid("HMAC mismatch")

    try:
        parsed = json.loads(raw.decode("utf-8"))
        nonce = str(parsed[_NONCE])
        expires_at = datetime.fromtimestamp(int(parsed[_EXPIRES]), tz=UTC)
        claims = {k: str(v) for k, v in parsed.items() if k not in (_NONCE, _EXPIRES)}
    except (KeyError, ValueError, TypeError) as exc:
        raise OAuthStateInvalid(f"payload parse failed: {exc}") from exc

    current = now if now is not None else datetime.now(UTC)
    if expires_at <= current:
        raise OAuthStateExpired("state has expired")
    return StatePayload(claims=claims, nonce=nonce, expires_at=expires_at)
