"""Google como proveedor de identidad — spec 006, Requisito 5.

**Se habla con Google directamente y no con un proveedor de identidad
intermedio** (ADR-038 D5). La razón que decide no es el precio: es que las
próximas integraciones de esta plataforma son leer Calendar o Gmail para un
teammate, y eso pide tokens de Google propios con autorización incremental. El
mismo flujo, ampliado con los ámbitos nuevos sobre la cuenta ya vinculada, sin
rehacer el inicio de sesión.

**No entra ninguna dependencia**: ``pyjwt`` ya estaba (y trae ``PyJWKClient``,
que es el cliente de JWKS con caché) y ``httpx`` también.

## Lo que se comprueba de un `id_token`, y por qué cada cosa

- **`email_verified`** — Google emite un token con un correo para *cualquier*
  cuenta, verificada o no. Sin esta bandera, cualquiera puede registrar una
  cuenta de Google con el correo de otra persona, no verificarlo, y llegar aquí
  con una identidad ajena. Es **el** criterio, no un caso límite.
- **`aud`** — un `id_token` emitido para otra aplicación también lo firma
  Google y también es válido. Sin comprobar la audiencia, serviría para entrar
  aquí.
- **`iss`** — Google usa dos formas (`accounts.google.com` y
  `https://accounts.google.com`) y las dos son legítimas.
- **`exp`** y **firma** — lo de siempre, con `alg` restringido a RS256: un
  verificador que acepte `none` no verifica nada.

## Lo que NO se guarda, y es deliberado

**Ningún token del proveedor.** El `access_token` no se usa —el `id_token` ya
trae `sub` y `email_verified`— y no se pide `refresh_token`, porque hoy no hay
ámbito que refrescar. La columna se añadirá con la spec que los necesite.
Guardarlos ahora sería una credencial almacenada sin lector: exactamente la
figura de ``NEXUS_WEBHOOK_HMAC_SECRET`` en `pendientes-tras-el-go-live` §5.

## PKCE, y dónde vive el verificador

El `code_verifier` **no viaja al navegador** y no cabe en el `state` (que sí
viaja). Se guarda en Redis bajo el nonce del state y se consume de forma
atómica: ahí es donde vive el «un state vale una sola vez», que una firma no
puede garantizar por sí sola.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlencode

import jwt

#: Los extremos de Google. Constantes y no configuración: apuntar esto a otro
#: sitio no es un ajuste de despliegue, es cambiar de proveedor de identidad.
AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
JWKS_URI = "https://www.googleapis.com/oauth2/v3/certs"

#: Las dos formas que Google usa, y las dos son legítimas.
VALID_ISSUERS = frozenset({"accounts.google.com", "https://accounts.google.com"})

#: Lo mínimo para saber quién es. **No se piden ámbitos de datos**: cuando
#: haga falta Calendar o Gmail, se añadirán por autorización incremental sobre
#: esta misma cuenta, que es justo por lo que se eligió este flujo.
SCOPES = ("openid", "email", "profile")

#: Cuánto vive el `code_verifier` en Redis. Una ida y vuelta tarda segundos.
PKCE_TTL_SECONDS = 600


class GoogleIdentityError(ValueError):
    """El `id_token` no es utilizable: emisor, audiencia, caducidad o firma."""


class EmailNotVerified(GoogleIdentityError):
    """Google afirma el correo pero **no** que esté verificado.

    Es su propia clase porque la respuesta es distinta: no es un token
    malformado, es una identidad que el proveedor no respalda.
    """


@dataclass(frozen=True)
class GoogleIdentity:
    #: El `sub`. **Esto es la identidad**: opaco, estable y nunca reasignado.
    subject: str
    email: str
    display_name: str | None


class _KeyResolver(Protocol):
    def __call__(self, token: str) -> Any: ...


def pkce_pair() -> tuple[str, str]:
    """``(code_verifier, code_challenge)`` con el método S256.

    El reto es el SHA-256 del verificador, no el verificador: si fueran lo
    mismo, quien intercepte el redirect tendría los dos y PKCE no protegería
    de nada.
    """
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def authorization_url(
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str,
) -> str:
    """A dónde se manda al navegador."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        # Sin `access_type=offline`: hoy no se pide refresh token porque no hay
        # ámbito que refrescar. Se añadirá con la spec que lo use.
        "prompt": "select_account",
    }
    return f"{AUTH_ENDPOINT}?{urlencode(params)}"


def _default_key_resolver(token: str) -> Any:
    # ``PyJWKClient`` cachea las claves; instanciarlo por llamada sería pedir
    # el JWKS en cada inicio de sesión.
    return _jwks_client().get_signing_key_from_jwt(token).key


_JWKS: jwt.PyJWKClient | None = None


def _jwks_client() -> jwt.PyJWKClient:
    global _JWKS
    if _JWKS is None:
        _JWKS = jwt.PyJWKClient(JWKS_URI, cache_keys=True)
    return _JWKS


def _is_verified(raw: object) -> bool:
    """``email_verified`` puede llegar como booleano o como texto.

    ``"false"`` es una cadena no vacía y sería **verdadera** en una
    comprobación ingenua. De ahí que esto sea una función y no un ``if``.
    """
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() == "true"
    return False


def verify_id_token(
    token: str,
    *,
    client_id: str,
    key_resolver: _KeyResolver | None = None,
    leeway_seconds: int = 30,
) -> GoogleIdentity:
    """Verifica el `id_token` y devuelve quién es. Lanza en cualquier fallo."""
    resolver = key_resolver or _default_key_resolver
    try:
        key = resolver(token)
    except Exception as exc:  # la librería del JWKS lanza lo suyo
        raise GoogleIdentityError(f"no signing key: {exc}") from exc

    try:
        claims = jwt.decode(
            token,
            key=key,
            # Restringido a propósito: un verificador que acepte `none` no
            # verifica nada, y aceptar HS256 con una clave pública conocida es
            # el ataque de confusión de algoritmos.
            algorithms=["RS256"],
            audience=client_id,
            leeway=leeway_seconds,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise GoogleIdentityError(f"id_token rejected: {exc}") from exc

    if claims.get("iss") not in VALID_ISSUERS:
        raise GoogleIdentityError(f"unexpected issuer: {claims.get('iss')!r}")

    email = claims.get("email")
    if not email:
        raise GoogleIdentityError("id_token carries no e-mail")
    if not _is_verified(claims.get("email_verified")):
        raise EmailNotVerified(f"provider does not vouch for {email!r}")

    return GoogleIdentity(
        subject=str(claims["sub"]),
        email=str(email).strip().lower(),
        display_name=(str(claims["name"]) if claims.get("name") else None),
    )


async def exchange_code(
    *,
    code: str,
    code_verifier: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> str:
    """Canjea el código por el `id_token`. Devuelve **sólo** el `id_token`.

    Devolver sólo eso no es pereza: es que lo demás no se quiere. Un
    `access_token` que nadie usa es una credencial que alguien acabará
    guardando.
    """
    import httpx

    async with httpx.AsyncClient(timeout=15.0) as http:
        response = await http.post(
            TOKEN_ENDPOINT,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            },
        )
    if response.status_code != 200:
        raise GoogleIdentityError(f"token exchange failed with {response.status_code}")
    id_token = response.json().get("id_token")
    if not id_token:
        raise GoogleIdentityError("token response carries no id_token")
    return str(id_token)


def pkce_key(nonce: str) -> str:
    return f"oauth:pkce:{nonce}"


async def remember_pkce(redis: Any, *, nonce: str, verifier: str) -> None:
    await redis.setex(pkce_key(nonce), PKCE_TTL_SECONDS, verifier)


async def consume_pkce(redis: Any, *, nonce: str) -> str | None:
    """Lee **y borra** el verificador. Aquí vive el «un state vale una sola vez».

    Es atómico a propósito: con un ``get`` y un ``delete`` sueltos, dos
    callbacks simultáneos con el mismo state pasarían los dos.
    """
    key = pkce_key(nonce)
    pipe = redis.pipeline()
    pipe.get(key)
    pipe.delete(key)
    stored, _deleted = await pipe.execute()
    if stored is None:
        return None
    return stored.decode("utf-8") if isinstance(stored, bytes) else str(stored)
