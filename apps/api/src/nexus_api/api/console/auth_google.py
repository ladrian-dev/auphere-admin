"""``/console/auth/google/*`` — entrar con Google (spec 006, Requisito 5).

Dos llamadas, como el contrato: ``start`` devuelve a dónde mandar el navegador,
``callback`` recibe la vuelta. Las dos van detrás del token de servicio del
BFF, igual que el resto de ``/console/*`` — el navegador habla con el BFF y el
BFF con esto.

**Las tres cosas que sostienen la seguridad de este recorrido:**

1. **`email_verified`**, que comprueba ``google_oidc`` y aquí se traduce a un
   403. Sin esa bandera, cualquiera registra una cuenta de Google con el correo
   de otra persona y llega hasta aquí con una identidad ajena.
2. **El `state` firmado**, para que la vuelta sea la de la ida y no la de
   cualquiera que alcance el callback.
3. **El uso único**, que lo da consumir el `code_verifier` de Redis de forma
   atómica: la firma sola no puede impedir que el mismo `state` se presente dos
   veces.

**La sesión que sale de aquí es la misma clase que la del login con
contraseña** y pasa por la misma revalidación de pertenencia en cada llamada.
Entrar por otra puerta no da otro tipo de acceso.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.config import get_settings
from nexus_api.core.client_ip import client_ip_for_storage
from nexus_api.core.console_auth import ConsoleService, require_console_service
from nexus_api.repositories.signup import SignupRequestRepository
from nexus_api.services import console_identity, google_oidc
from nexus_api.services.identity_link import resolve_provider_identity
from nexus_api.services.oauth_state import (
    OAuthStateExpired,
    OAuthStateInvalid,
    sign_state,
    verify_state,
)

from .schemas_auth_google import (
    GoogleAvailableOut,
    GoogleCallbackIn,
    GoogleCallbackOut,
    GoogleStartIn,
    GoogleStartOut,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth/google")

PROVIDER = "google"


def _configured() -> bool:
    """Los tres, o ninguno. Con dos de tres el canje fallaría con un error del
    proveedor que no se parece en nada a la causa."""
    s = get_settings()
    return bool(s.google_client_id and s.google_client_secret and s.google_redirect_uri)


def _config() -> tuple[str, str, str, str]:
    """Los cuatro valores, o 503. Recordatorio: la configuración es todo o
    nada — la guarda de arranque impide desplegar con Google a medias."""
    s = get_settings()
    if not _configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="google_not_configured"
        )
    return (
        s.google_client_id,
        s.google_client_secret,
        s.google_redirect_uri,
        s.connector_consent_secret,
    )


def _rejected(reason: str) -> HTTPException:
    """Un cuerpo único para todos los fallos del `state` y del código.

    Distinguir «caducado» de «manipulado» de «ya usado» sólo informa a quien
    está probando, que es exactamente a quien no hay que informar.
    """
    log.warning("console_auth.google_rejected", reason=reason)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_request")


@router.get("/available", response_model=GoogleAvailableOut)
async def available(
    _svc: ConsoleService = Depends(require_console_service()),
) -> GoogleAvailableOut:
    """¿Hay Google? **Esto no crea nada, y ese es todo su motivo de existir.**

    La consola lo pregunta para decidir si pinta el botón. Antes lo preguntaba
    con ``/start``, que acuña un par PKCE y lo guarda diez minutos: cada visita
    a ``/login`` —una página pública— dejaba una clave que nadie consumiría.

    **200 con ``false`` y no 503**: que no haya Google es una respuesta, no un
    fallo. El alta con contraseña sigue funcionando sin él (CE-006), y la
    consola necesita distinguir «no hay» de «no se pudo preguntar».
    """
    return GoogleAvailableOut(available=_configured())


@router.post("/start", response_model=GoogleStartOut)
async def start(
    body: GoogleStartIn,
    _svc: ConsoleService = Depends(require_console_service()),
    redis: Redis = Depends(get_redis),
) -> GoogleStartOut:
    client_id, _secret, redirect_uri, state_secret = _config()
    verifier, challenge = google_oidc.pkce_pair()
    state, payload = sign_state(claims={"i": body.intent}, secret=state_secret)
    # El verificador se queda aquí. **No viaja al navegador**: si viajara,
    # quien intercepte el redirect tendría las dos mitades de PKCE.
    await google_oidc.remember_pkce(redis, nonce=payload.nonce, verifier=verifier)
    return GoogleStartOut(
        authorization_url=google_oidc.authorization_url(
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=challenge,
        )
    )


@router.post("/callback", response_model=GoogleCallbackOut)
async def callback(
    body: GoogleCallbackIn,
    request: Request,
    _svc: ConsoleService = Depends(require_console_service()),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> GoogleCallbackOut:
    client_id, client_secret, redirect_uri, state_secret = _config()

    try:
        payload = verify_state(state=body.state, secret=state_secret)
    except (OAuthStateInvalid, OAuthStateExpired) as exc:
        raise _rejected(type(exc).__name__) from exc

    # Consumir es lo que hace que un `state` valga una sola vez.
    verifier = await google_oidc.consume_pkce(redis, nonce=payload.nonce)
    if verifier is None:
        raise _rejected("state_already_used")

    try:
        id_token = await google_oidc.exchange_code(
            code=body.code,
            code_verifier=verifier,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
        )
        identity = google_oidc.verify_id_token(id_token, client_id=client_id)
    except google_oidc.EmailNotVerified as exc:
        # 403 y no 400: el token está bien, lo que falta es que el proveedor
        # respalde ese correo. **No se crea nada.**
        log.warning("console_auth.google_email_unverified")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="email_not_verified"
        ) from exc
    except google_oidc.GoogleIdentityError as exc:
        raise _rejected("id_token_rejected") from exc

    async with session.begin():
        outcome = await resolve_provider_identity(
            session, provider=PROVIDER, subject=identity.subject, email=identity.email
        )
        if outcome.account is not None:
            token, expires_at = await console_identity.start_session(
                session,
                outcome.account,
                ip=client_ip_for_storage(request),
                user_agent=request.headers.get("user-agent"),
            )
            return GoogleCallbackOut(
                outcome="session", session_token=token, expires_at=expires_at.isoformat()
            )

        # No hay cuenta: esto es un alta, y el alta tiene sus reglas.
        if not get_settings().signup_enabled:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="signup_disabled"
            )
        _row, plaintext = await SignupRequestRepository(session).create(
            email=identity.email,
            ttl_hours=get_settings().signup_token_ttl_hours,
            provider=PROVIDER,
            ip=client_ip_for_storage(request),
        )
        # **No se manda correo**: Google ya verificó la dirección, que es para
        # lo único que servía el enlace. La solicitud existe para llevar el
        # estado hasta el paso de nombrar la empresa.
        return GoogleCallbackOut(outcome="signup_pending", signup_token=plaintext)
