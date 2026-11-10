"""``/app/*`` — lo público de la app Auphere Customers (spec 031, research D2b).

Fuera de ``/console`` a propósito: ``test_console_scope`` exige un 401 sin token
en todo ``/console``, y estas rutas se llaman **antes** de tener sesión. La lista
cerrada vive en ``tests/isolation/test_app_public_routes.py``.

**La app tiene su propia entrada** (enmienda de R1 del 2026-10-20): nada pasa
por la consola de partners.

* ``POST /app/sign-in/password`` — correo y contraseña, con las reglas del login
  web (R1.2).
* ``GET /app/sign-in/google`` y ``/callback`` — el flujo web de Google, alojado
  aquí; vuelve a la app con un código de un uso atado a su reto PKCE (R1.3).
* ``POST /app/sign-in/google`` — canjea ese código.
* ``POST /app/password-reset`` — el enlace para crear una contraseña (R1.7).
* ``POST /app/phones/refresh`` — renueva (R2.1).
* ``GET /app/config`` — la versión mínima, la URL de la consola y si hay Google
  (R13).

**Los límites.** La IP que la API cuenta es la que firma la BFF de la consola
(``core/client_ip``), y a ``/app`` se llega sin BFF: aquí los límites son por
correo (contraseña) y por código (canje), más el bloqueo de la cuenta tras
diez fallos. El límite por IP es del borde (``docs/app-movil.md``).
"""

from __future__ import annotations

import hashlib
import re
from datetime import timedelta
from typing import Literal
from urllib.parse import urlencode

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.console.auth import LOGIN_ATTEMPTS_PER_MINUTE
from nexus_api.api.console.password_reset import request_reset_link
from nexus_api.api.deps import get_redis
from nexus_api.config import get_settings
from nexus_api.core.client_auth import _customers_minimum, resolve_client_principal
from nexus_api.core.rate_limit import allow
from nexus_api.db.base import get_sessionmaker
from nexus_api.desktop_version import is_blocked
from nexus_api.services import client_phones, console_identity, google_oidc
from nexus_api.services.console_identity import KIND_CLIENT, PrincipalView
from nexus_api.services.identity_link import resolve_provider_identity
from nexus_api.services.oauth_state import (
    OAuthStateExpired,
    OAuthStateInvalid,
    sign_state,
    verify_state,
)
from nexus_api.services.one_time_code_limits import CodeRateLimited, CodeRateLimiter
from nexus_api.services.session_codes import (
    PURPOSE_PHONE,
    SessionCodeRejected,
    consume_phone_code,
    issue_session_code,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/app", tags=["customers-app"])

#: La única vuelta posible a la app. Fija: no se lee de la petición.
APP_RETURN = "auphere-customers://auth/callback"
GOOGLE_CALLBACK_PATH = "/app/sign-in/google/callback"
#: Lo que dura la ida y vuelta por Google (el verificador de Redis dura igual).
GOOGLE_STATE_TTL = timedelta(seconds=google_oidc.PKCE_TTL_SECONDS)
_CHALLENGE = re.compile(r"^[A-Za-z0-9_-]{43}$")
_RETRY_AFTER_SECONDS = 60


class DeviceIn(BaseModel):
    """Lo que la app dice de sí misma al entrar, sea cual sea la puerta."""

    platform: Literal["ios", "android"]
    display_name: str = Field(min_length=1, max_length=120)
    install_id: str = Field(min_length=8, max_length=64)
    app_version: str = Field(min_length=1, max_length=32)
    locale: str = Field(default="es", max_length=8)


class PasswordSignInIn(DeviceIn):
    #: Como ``LoginIn`` de la consola: entrar es buscar una fila, no validar un
    #: correo. Un validador más estricto que el del alta deja cuentas fuera.
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=256)


class GoogleRedeemIn(DeviceIn):
    code: str = Field(min_length=1, max_length=32)
    code_verifier: str = Field(min_length=43, max_length=128)


class PasswordResetIn(BaseModel):
    #: Formato mínimo y el mismo 422 para cualquiera; no ``EmailStr``, que
    #: rechaza los dominios de prueba con los que se siembran los entornos.
    email: str = Field(min_length=3, max_length=255, pattern=r"^[^@\s]+@[^@\s]+$")


class TokensOut(BaseModel):
    phone_id: str
    access_token: str
    expires_in: int
    refresh_token: str


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=128)
    app_version: str | None = Field(default=None, max_length=32)


def _code(status_code: int, code: str, **extra: str) -> JSONResponse:
    """Los errores de ``/app/*`` van en la raíz (``{"code": …}``)."""
    return JSONResponse(status_code=status_code, content={"code": code, **extra})


def _invalid_grant() -> JSONResponse:
    return _code(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_grant")


def _limited(exc: CodeRateLimited) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"code": "rate_limited"},
        headers={"Retry-After": str(exc.retry_after_seconds)},
    )


def _code_key(code: str) -> str:
    """El cubo de intentos de un código, **por código** y no por IP.

    A ``/app`` se llega sin la BFF: no hay IP de fiar y todos los teléfonos
    caerían en el mismo cubo, de modo que unos pocos intentos basura de
    cualquiera bloquearían la entrada de todo el mundo. Por código, cinco
    verificadores malos agotan ese código y nada más; adivinar el código no
    sirve sin el verificador PKCE, que nunca viaja.
    """
    return f"app:sign-in:{hashlib.sha256(code.strip().upper().encode()).hexdigest()[:32]}"


def _too_old(platform: str, version: str) -> JSONResponse | None:
    """R13: una versión por debajo de la mínima no entra, antes que nada."""
    minimum = _customers_minimum(platform)
    if not is_blocked(version, minimum):
        return None
    assert minimum is not None
    return _code(status.HTTP_403_FORBIDDEN, "app_update_required", minimum_version=minimum.version)


def _refusal(view: PrincipalView) -> str | None:
    """Por qué esta cuenta no entra en la app, o ``None`` si entra.

    Una persona de partner no es de la app (R1.5); una de cliente sin
    membresía activa o sin acceso, tampoco (R1.6). Una cuenta sin ninguna de
    las dos no tiene acceso a nada.
    """
    if view.membership is not None:
        return "not_a_client"
    if view.kind != KIND_CLIENT or not view.ok:
        return "no_access"
    return None


async def _open_phone(
    session: AsyncSession, *, account_id: str, body: DeviceIn, method: str
) -> TokensOut | JSONResponse:
    """La puerta ya dijo quién es. Si su acceso sigue en pie, el teléfono entra.

    Se comprueba otra vez aquí, con la misma ``resolve_client_principal`` de
    cada petición: entre que Google o la contraseña dicen «es ella» y que se
    crea el teléfono, Auphere puede haber apagado el acceso.
    """
    async with session.begin():
        membership = await client_phones.active_membership(session, account_id)
    if membership is None:
        return _code(status.HTTP_403_FORBIDDEN, "no_access")
    principal = await resolve_client_principal(
        session, partner_id=membership.partner_id, user_id=membership.user_id, jti="sign-in"
    )
    if principal is None:
        return _code(status.HTTP_403_FORBIDDEN, "no_access")
    async with session.begin():
        tokens = await client_phones.enroll(
            session,
            membership=membership,
            platform=body.platform,
            display_name=body.display_name,
            install_id=body.install_id,
            app_version=body.app_version,
            locale=body.locale[:2].lower(),
            method=method,
        )
    return TokensOut(
        phone_id=str(tokens.phone_id),
        access_token=tokens.access_token,
        expires_in=tokens.expires_in,
        refresh_token=tokens.refresh_token,
    )


# ── con contraseña ─────────────────────────────────────────────────────


async def _login_allowed(redis: Redis, *, email: str) -> bool:
    """El cubo por correo, con las cifras del login web y su clave propia. El
    correo se guarda hasheado: una clave de Redis no es sitio para un dato
    personal."""
    email_key = hashlib.sha256(email.encode("utf-8")).hexdigest()[:32]
    return await allow(
        redis,
        key=f"rl:app:login:email:{email_key}",
        per_minute=LOGIN_ATTEMPTS_PER_MINUTE,
        surface="app_login",
    )


@router.post(
    "/sign-in/password",
    response_model=TokensOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"description": "invalid_credentials (también: cuenta bloqueada)"},
        403: {"description": "not_a_client · no_access · app_update_required"},
        429: {"description": "rate_limited, con Retry-After"},
    },
)
async def sign_in_with_password(
    body: PasswordSignInIn, redis: Redis = Depends(get_redis)
) -> TokensOut | JSONResponse:
    if (old := _too_old(body.platform, body.app_version)) is not None:
        return old
    email = console_identity.normalize_email(body.email)
    if not await _login_allowed(redis, email=email):
        log.warning("app_sign_in.rate_limited")
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"code": "rate_limited"},
            headers={"Retry-After": str(_RETRY_AFTER_SECONDS)},
        )

    async with get_sessionmaker()() as session:
        # Dos transacciones, como el login web: el intento fallido suma al
        # contador de la cuenta y ese incremento tiene que confirmarse aunque
        # la respuesta sea un 401.
        async with session.begin():
            account = await console_identity.authenticate(
                session, email=email, password=body.password
            )
        if account is None:
            return _code(status.HTTP_401_UNAUTHORIZED, "invalid_credentials")
        async with session.begin():
            view = await console_identity.load_principal_view(session, account)
        if (refusal := _refusal(view)) is not None:
            log.info("app_sign_in.refused", reason=refusal, account_id=str(account.id))
            return _code(status.HTTP_403_FORBIDDEN, refusal)
        return await _open_phone(session, account_id=str(account.id), body=body, method="password")


# ── con Google ─────────────────────────────────────────────────────────


def _google_configured() -> bool:
    s = get_settings()
    return bool(s.google_client_id and s.google_client_secret)


def _google_redirect_uri() -> str:
    return f"{get_settings().public_api_base_url.rstrip('/')}{GOOGLE_CALLBACK_PATH}"


def _to_app(**params: str) -> RedirectResponse:
    """La vuelta a la app. El destino es fijo; solo cambian los parámetros."""
    clean = {k: v for k, v in params.items() if v}
    return RedirectResponse(f"{APP_RETURN}?{urlencode(clean)}", status_code=status.HTTP_302_FOUND)


@router.get("/sign-in/google", response_class=RedirectResponse, status_code=302)
async def sign_in_with_google(
    state: str = Query(min_length=16, max_length=128),
    # Sin límites de longitud aquí: un reto mal formado (hex, por ejemplo) es
    # un 400 propio con su código, no el 422 genérico de la validación.
    code_challenge: str = Query(max_length=256),
    redis: Redis = Depends(get_redis),
) -> Response:
    """La ida: a Google, eligiendo cuenta. El ``state`` y el reto de la app
    viajan dentro de nuestro ``state`` firmado; el reto con Google es otro, y
    su verificador no sale de Redis."""
    if not _CHALLENGE.match(code_challenge):
        return _code(status.HTTP_400_BAD_REQUEST, "invalid_request")
    if not _google_configured():
        return _to_app(error="google_unavailable", state=state)
    s = get_settings()
    verifier, challenge = google_oidc.pkce_pair()
    signed, payload = sign_state(
        claims={"i": "app", "s": state, "c": code_challenge},
        secret=s.connector_consent_secret,
        ttl=GOOGLE_STATE_TTL,
    )
    await google_oidc.remember_pkce(redis, nonce=payload.nonce, verifier=verifier)
    url = google_oidc.authorization_url(
        client_id=s.google_client_id,
        redirect_uri=_google_redirect_uri(),
        state=signed,
        code_challenge=challenge,
    )
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)


class _Refused(Exception):
    """Sale del bloque de la transacción para que se deshaga: un rechazo no
    deja vínculos ni códigos a medias."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@router.get("/sign-in/google/callback", response_class=RedirectResponse, status_code=302)
async def google_callback(
    state: str | None = Query(default=None, max_length=4096),
    code: str | None = Query(default=None, max_length=2048),
    error: str | None = Query(default=None, max_length=128),
    redis: Redis = Depends(get_redis),
) -> RedirectResponse:
    """La vuelta de Google. **Siempre** termina en la app: con un código, o con
    el motivo para que pinte su mensaje (contrato ``phone-auth.md``)."""
    s = get_settings()
    if not state:
        return _to_app(error="failed")
    try:
        payload = verify_state(state=state, secret=s.connector_consent_secret)
    except (OAuthStateInvalid, OAuthStateExpired):
        log.warning("app_sign_in.google_state_rejected")
        return _to_app(error="failed")
    app_state = payload.claims.get("s", "")
    app_challenge = payload.claims.get("c", "")
    # Un `state` de la consola (otro `i`) no vale aquí, aunque lo firmemos igual.
    if payload.claims.get("i") != "app" or not _CHALLENGE.match(app_challenge):
        return _to_app(error="failed")
    if error is not None:
        return _to_app(error="cancelled" if error == "access_denied" else "failed", state=app_state)
    if not code or not _google_configured():
        return _to_app(error="failed", state=app_state)

    # Consumirlo es lo que hace que esta vuelta valga una sola vez.
    verifier = await google_oidc.consume_pkce(redis, nonce=payload.nonce)
    if verifier is None:
        return _to_app(error="failed", state=app_state)
    try:
        id_token = await google_oidc.exchange_code(
            code=code,
            code_verifier=verifier,
            client_id=s.google_client_id,
            client_secret=s.google_client_secret,
            redirect_uri=_google_redirect_uri(),
        )
        identity = google_oidc.verify_id_token(id_token, client_id=s.google_client_id)
    except google_oidc.EmailNotVerified:
        return _to_app(error="email_not_verified", state=app_state)
    except Exception:  # el canje con Google o el token: lo mismo para la app
        log.warning("app_sign_in.google_exchange_failed", exc_info=True)
        return _to_app(error="failed", state=app_state)

    try:
        async with get_sessionmaker()() as session, session.begin():
            outcome = await resolve_provider_identity(
                session, provider="google", subject=identity.subject, email=identity.email
            )
            if outcome.account is None:
                raise _Refused("google_account_mismatch")
            view = await console_identity.load_principal_view(session, outcome.account)
            if (refusal := _refusal(view)) == "not_a_client":
                raise _Refused(refusal)
            # La regla de la app: el correo de Google es el que Auphere dio de
            # alta para la persona en el cliente. Aunque el `sub` ya estuviera
            # vinculado y el correo de Google haya cambiado.
            member = view.client_membership
            if member is not None and console_identity.normalize_email(
                member.email
            ) != console_identity.normalize_email(identity.email):
                raise _Refused("google_account_mismatch")
            if refusal is not None:
                raise _Refused(refusal)
            issued = await issue_session_code(
                session,
                principal_id=outcome.account.id,
                code_challenge=app_challenge,
                purpose=PURPOSE_PHONE,
            )
    except _Refused as refused:
        log.info("app_sign_in.google_refused", reason=refused.code)
        return _to_app(error=refused.code, state=app_state)
    return _to_app(code=issued, state=app_state)


@router.post(
    "/sign-in/google",
    response_model=TokensOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        403: {"description": "no_access · app_update_required"},
        422: {"description": "invalid_grant"},
        429: {"description": "rate_limited"},
    },
)
async def redeem_google_code(
    body: GoogleRedeemIn, redis: Redis = Depends(get_redis)
) -> TokensOut | JSONResponse:
    if (old := _too_old(body.platform, body.app_version)) is not None:
        return old
    limiter = CodeRateLimiter(redis=redis)
    async with get_sessionmaker()() as session:
        try:
            async with session.begin():
                principal_id = await consume_phone_code(
                    session,
                    code=body.code,
                    code_verifier=body.code_verifier,
                    limiter=limiter,
                    attempt_key=_code_key(body.code),
                )
        except CodeRateLimited as exc:
            return _limited(exc)
        except SessionCodeRejected:
            return _invalid_grant()
        return await _open_phone(session, account_id=str(principal_id), body=body, method="google")


# ── olvido de contraseña ───────────────────────────────────────────────


class PasswordResetOut(BaseModel):
    """Siempre el mismo cuerpo (R1.7)."""

    status: Literal["sent_if_known"] = "sent_if_known"


@router.post(
    "/password-reset", response_model=PasswordResetOut, status_code=status.HTTP_202_ACCEPTED
)
async def password_reset(
    body: PasswordResetIn, background: BackgroundTasks, redis: Redis = Depends(get_redis)
) -> PasswordResetOut:
    async with get_sessionmaker()() as session:
        await request_reset_link(
            session, redis, background, email=console_identity.normalize_email(body.email)
        )
    return PasswordResetOut()


# ── renovar y configuración ────────────────────────────────────────────


@router.post("/phones/refresh", response_model=TokensOut)
async def refresh(body: RefreshIn) -> TokensOut | JSONResponse:
    """Renueva (R2.1). **Sin límite de intentos, a propósito:** la renovación
    es un secreto aleatorio de 256 bits, no hay nada que adivinar, y un límite
    por IP aquí sería uno solo para todos los teléfonos (ver ``_code_key``)."""
    tokens: client_phones.PhoneTokens | None = None
    closed: client_phones.PhoneClosed | None = None
    async with get_sessionmaker()() as session, session.begin():
        # Se capturan DENTRO del bloque a propósito: ``refresh`` puede cerrar el
        # teléfono (abandono, credencial reutilizada) antes de rechazar, y ese
        # cierre tiene que confirmarse. Una excepción que saliera del bloque lo
        # desharía con el rollback.
        try:
            tokens = await client_phones.refresh(
                session, refresh_token=body.refresh_token, app_version=body.app_version
            )
        except client_phones.PhoneClosed as exc:
            closed = exc
        except client_phones.RefreshRejected:
            pass
    if closed is not None:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"code": "phone_closed", "reason": closed.reason},
        )
    if tokens is None:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED, content={"code": "invalid_grant"}
        )
    return TokensOut(
        phone_id=str(tokens.phone_id),
        access_token=tokens.access_token,
        expires_in=tokens.expires_in,
        refresh_token=tokens.refresh_token,
    )


class SignInMethodsOut(BaseModel):
    google: bool


class AppConfigOut(BaseModel):
    min_version: dict[str, str | None]
    reason: str | None
    console_url: str
    #: La app solo enseña «Continuar con Google» si la API lo tiene configurado.
    sign_in: SignInMethodsOut


@router.get("/config", response_model=AppConfigOut)
async def app_config(response: Response) -> AppConfigOut:
    s = get_settings()
    response.headers["Cache-Control"] = "public, max-age=300"
    ios, android = _customers_minimum("ios"), _customers_minimum("android")
    declared = ios or android
    return AppConfigOut(
        min_version={
            "ios": ios.version if ios else None,
            "android": android.version if android else None,
        },
        reason=declared.reason if declared is not None else None,
        console_url=s.console_base_url.rstrip("/"),
        sign_in=SignInMethodsOut(google=_google_configured()),
    )


__all__ = ["router"]
